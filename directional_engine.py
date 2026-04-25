import asyncio
import time
import logging
from config import (
    GAP_THRESHOLD_DEFAULT, CVD_THRESHOLD_PCT, VELOCITY_MIN_DELTA, 
    DIRECTIONAL_MAX_ODDS, BASE_SHARES, SNIPER_ZONE_END, 
    CONFIRMATION_WINDOW_START, OVERRIDE_WINDOW_START,
    OVERRIDE_GAP_THRESHOLD, HEARTBEAT_INTERVAL, VETO_MULTIPLIER,
    GAP_VOL_NORMALIZATION, GAP_VOL_MULTIPLIER, VOL_ESTIMATOR_WINDOW,
    BINANCE_FEED_ENABLED
)
from discovery import MarketDiscovery
from executor import Executor
from performance_logger import PerformanceLogger
from order_status_poller import OrderStatusPoller
from notifier import Notifier, AlertLevel
from strategy_utils import VolatilityEstimator
from binance_feed import BinanceFeed

logger = logging.getLogger("ADS_Engine")
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler("ads_execution.log", encoding="utf-8")
formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

class DirectionalEngine:
    def __init__(self, hyperliquid_feed, poly_feed):
        self.hl_feed = hyperliquid_feed
        self.poly_feed = poly_feed
        self.discovery = MarketDiscovery()
        self.executor = Executor()
        
        self.order_sent = False
        self.gap = 0.0
        self.bias = "NONE"
        self.gate_passed = False
        self.status = "IDLE"
        self.window_start = 0
        
        # Epoch & Market State
        self.current_epoch = 0
        self.target_slug = "WAITING..."
        self.t_minus = 0
        self.token_up = None
        self.token_down = None
        self.reference_price = 0.0
        
        # Inventory & Risk tracking
        self.inventory_position = "NONE"
        self.inventory_risk = 0.0
        self.epoch_orders = []
        self.total_spent = 0.0
        self.current_epoch_spent = 0.0

        # Enhancements
        self.perf_logger = PerformanceLogger()
        self.poller = OrderStatusPoller(self.executor.client, self.executor._thread_pool)
        self.notifier = Notifier()
        self.vol_estimator = VolatilityEstimator(window=VOL_ESTIMATOR_WINDOW)
        self.binance_feed = BinanceFeed() if BINANCE_FEED_ENABLED else None
        self.effective_gap_threshold = GAP_THRESHOLD_DEFAULT
        
        self.last_log = "Engine Initialized"

    async def _async_log(self, msg):
        try:
            logger.info(msg)
            self.last_log = msg
        except Exception:
            pass

    async def _discovery_loop(self):
        await asyncio.sleep(1)
        while True:
            now = int(time.time())
            next_epoch = self.discovery.get_next_epoch()
            self.t_minus = next_epoch - now
            epoch = self.discovery.get_current_epoch()
            
            if epoch != self.current_epoch or not self.token_up:
                if epoch != self.current_epoch:
                    # Epoch Summary for Notifier
                    if self.current_epoch > 0:
                        summary = (
                            f"Epoch {self.current_epoch} Ended | "
                            f"Orders: {len(self.epoch_orders)} | "
                            f"Spent: ${self.current_epoch_spent:.2f} | "
                            f"Total Spent: ${self.total_spent:.2f}"
                        )
                        asyncio.create_task(self.notifier.send(summary, level=AlertLevel.INFO))

                    await self._async_log(f"NETWORK: New Epoch Detected: {epoch}")
                    self.current_epoch = epoch
                    self.token_up = None
                    
                    # Reset order state only when epoch truly changes
                    self.order_sent = False
                    self.status = "IDLE"
                    self.gate_passed = False
                    self.current_epoch_spent = 0.0
                    self.epoch_orders = []
                    await self._async_log("ORDER LOCK RELEASED: New epoch started")
                
                market_data = await self.discovery.discover_tokens(epoch)
                
                if market_data:
                    self.target_slug = market_data["slug"]
                    self.token_up = market_data["token_up"]
                    self.token_down = market_data["token_down"]
                    strike = market_data["strike"]
                    
                    await self._async_log(f"NETWORK: Market Loaded: {self.target_slug}")
                    
                    self.gate_passed = False
                    self.reference_price = 0.0
                    
                    await self.poly_feed.update_subscription(self.token_up, self.token_down, strike)
                else:
                    await asyncio.sleep(2)
            
            await asyncio.sleep(1)

    async def run(self):
        await self._async_log("Engine Started")
        asyncio.create_task(self._discovery_loop())
        
        last_heartbeat = time.time()
        
        while True:
            try:
                now = time.time()
                # State Machine based on t_minus (Fixed Granularity)
                if self.t_minus > OVERRIDE_WINDOW_START + 15:
                    self.status = "IDLE"
                elif OVERRIDE_WINDOW_START < self.t_minus <= OVERRIDE_WINDOW_START + 15:
                    self.status = "ARMING"
                elif CONFIRMATION_WINDOW_START < self.t_minus <= OVERRIDE_WINDOW_START:
                    self.status = "OVERRIDE_WATCH"
                elif SNIPER_ZONE_END < self.t_minus <= CONFIRMATION_WINDOW_START:
                    self.status = "SNIPER_READY"
                elif self.t_minus <= SNIPER_ZONE_END:
                    self.status = "CEASE_FIRE"

                hl_state = self.hl_feed.get_state()
                poly_state = self.poly_feed.get_state()
                
                hl_price = hl_state["price"]
                strike = poly_state["strike_price"]
                cvd = hl_state["cvd"]
                velocity = hl_state["velocity"]
                
                # Sync Strike
                current_strike = strike
                if current_strike == 0 and hl_price > 0:
                    if self.reference_price == 0:
                        self.reference_price = hl_price
                        await self._async_log(f"REFERENCE SET: {self.reference_price}")
                    current_strike = self.reference_price

                # 1. Update Price & Bias FIRST
                if current_strike > 0 and hl_price > 0:
                    self.gap = hl_price - current_strike
                    self.bias = "UP" if self.gap > 0 else "DOWN" if self.gap < 0 else "NONE"

                # 2. Update Volatility Estimator ONLY on price change
                if hl_price > 0 and hl_price != getattr(self, '_last_vol_price', 0):
                    self.vol_estimator.update(hl_price)
                    self._last_vol_price = hl_price
                
                # 3. NOW calculate effective threshold
                self.effective_gap_threshold = self._get_effective_gap_threshold()

                abs_gap = abs(self.gap)
                abs_velocity = abs(velocity)

                if now - last_heartbeat > HEARTBEAT_INTERVAL:
                    # Determine gate status for logging
                    g_ok = "OK" if abs_gap >= self.effective_gap_threshold else "FAIL"
                    c_ok = "OK" if ((self.bias == "UP" and cvd > CVD_THRESHOLD_PCT) or (self.bias == "DOWN" and cvd < -CVD_THRESHOLD_PCT)) else "FAIL"
                    v_ok = "OK" if abs_velocity > VELOCITY_MIN_DELTA else "FAIL"
                    
                    # Feed Health Checks (Last msg < 30s)
                    loop_now = asyncio.get_event_loop().time()
                    h_health = "OK" if (loop_now - hl_state.get("last_msg_time", 0)) < 30 else "DEAD"
                    p_health = "OK" if (loop_now - poly_state.get("last_msg_time", 0)) < 30 else "DEAD"

                    hb_msg = (
                        f"HEARTBEAT | STAT:{self.status} | T-{self.t_minus}s | "
                        f"P:{hl_price:,.2f} | S:{current_strike:,.2f} | "
                        f"G:{abs_gap:.2f}({g_ok}) | C:{cvd:.1f}%({c_ok}) | "
                        f"V:{abs_velocity:.1f}({v_ok}) | BIAS:{self.bias} | "
                        f"FEED(HL:{h_health} PL:{p_health})"
                    )
                    await self._async_log(hb_msg)
                    last_heartbeat = now


                # Predator Decision Logic (Veto Threshold from Config)
                veto_threshold = CVD_THRESHOLD_PCT * VETO_MULTIPLIER
                veto = False
                if self.bias == "UP" and cvd < -veto_threshold:
                    veto = True
                elif self.bias == "DOWN" and cvd > veto_threshold:
                    veto = True

                # Signal Evaluation
                is_override = abs_gap >= OVERRIDE_GAP_THRESHOLD
                
                gap_pass = abs_gap >= self.effective_gap_threshold
                cvd_pass = not veto and ((self.bias == "UP" and cvd >= CVD_THRESHOLD_PCT) or (self.bias == "DOWN" and cvd <= -CVD_THRESHOLD_PCT))
                vel_pass = abs_velocity >= VELOCITY_MIN_DELTA
                is_triple = gap_pass and cvd_pass and vel_pass

                # Dual Window Execution Block
                trigger_reason = ""
                can_execute = False
                
                if is_override:
                    if SNIPER_ZONE_END <= self.t_minus <= OVERRIDE_WINDOW_START:
                        can_execute = True
                        trigger_reason = f"Hyper-Sniper Override"
                    else:
                        if int(now) % 5 == 0:
                            logger.debug(f"Override Signal Ready but outside window T-{self.t_minus}s")
                
                elif is_triple:
                    if SNIPER_ZONE_END <= self.t_minus <= CONFIRMATION_WINDOW_START:
                        can_execute = True
                        trigger_reason = f"Triple Confirmation"
                    else:
                        if int(now) % 5 == 0:
                            logger.debug(f"Triple Signal Ready but outside window T-{self.t_minus}s")

                if not can_execute and not self.order_sent:
                    now_ts = time.time()
                    if not hasattr(self, '_last_waiting_log') or (now_ts - self._last_waiting_log > 10):
                        logger.info(f"Waiting for signal: gap={abs_gap:.1f}/{self.effective_gap_threshold:.1f} cvd={cvd:.1f}/{CVD_THRESHOLD_PCT} vel={abs_velocity:.1f}/{VELOCITY_MIN_DELTA}")
                        self._last_waiting_log = now_ts

                self.gate_passed = can_execute # For UI indication

                if can_execute and not self.order_sent and self.token_up:
                    target_ask = poly_state["up_ask"] if self.bias == "UP" else poly_state["down_ask"]
                    
                    # Panic Buy Mode: Override ignores MAX_ODDS
                    effective_max_odds = 0.99 if "Override" in trigger_reason else DIRECTIONAL_MAX_ODDS
                    
                    if 0 < target_ask <= effective_max_odds:
                        # Atomic Lock
                        self.order_sent = True
                        
                        await self._async_log(f"TARGET TRIGGER: {trigger_reason} | {self.bias} Gap:{abs_gap:.2f} CVD:{cvd:.1f} T-{self.t_minus}s")
                        
                        # Guarded Execution Call
                        asyncio.create_task(self._execute_with_guard(
                            bias=self.bias,
                            size=BASE_SHARES,
                            target_ask=target_ask,
                            token_up=self.token_up,
                            token_down=self.token_down,
                            epoch_end_time=self.discovery.get_next_epoch()
                        ))
                    else:
                        now_ts = time.time()
                        if not hasattr(self, '_last_skip_log') or (now_ts - self._last_skip_log > 5):
                            await self._async_log(f"SKIP: Signal OK but Price Invalid ({target_ask})")
                            self._last_skip_log = now_ts

            except Exception as e:
                await self._async_log(f"LOOP ERROR: {e}")
            
            await asyncio.sleep(0.01)

    async def _execute_with_guard(self, **kwargs):
        """Wrapper for executor calls with error handling, polling, and detailed logging."""
        start_ts = time.time()
        try:
            bias = kwargs.get('bias')
            target_ask = kwargs.get('target_ask')
            size = kwargs.get('size')
            token_up = kwargs.get('token_up')
            token_down = kwargs.get('token_down')
            
            # Prepare record for Phase 1 Data Collection
            # Some fields will be updated after execution/polling
            binance_ofi = 0.0
            if self.binance_feed:
                binance_ofi = self.binance_feed.get_state()["ofi"]

            record = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "epoch": self.current_epoch,
                "signal_type": "TRIPLE" if self.t_minus <= CONFIRMATION_WINDOW_START else "OVERRIDE",
                "bias": bias,
                "strike_price": self.poly_feed.strike_price,
                "gap": self.gap,
                "effective_threshold": self.effective_gap_threshold,
                "cvd": self.hl_feed.get_state()["cvd"],
                "velocity": self.hl_feed.get_state()["velocity"],
                "binance_ofi": binance_ofi,
                "up_ask": self.poly_feed.up_ask,
                "down_ask": self.poly_feed.down_ask,
                "size": size,
                "target_ask": target_ask,
                "fill_status": "SENT"
            }
            
            # Atomic Lock is already set to True by caller (run loop)
            success, order_id = await self.executor.execute(**kwargs)
            
            latency = (time.time() - start_ts) * 1000 # ms
            record["order_id"] = order_id
            record["latency"] = f"{latency:.2f}ms"
            
            if success and order_id:
                await self._async_log(f"EXECUTION SUCCESS: {bias} @ {target_ask} | ID: {order_id}")
                msg = f"EXECUTED: {bias} {size} shares @ {target_ask} (Gap: {abs(self.gap):.1f})"
                asyncio.create_task(self.notifier.send(msg, level=AlertLevel.TRADE))
                
                # Start non-blocking polling for fill status
                asyncio.create_task(self._poll_and_finalize(record, order_id, epoch_end_time=kwargs.get('epoch_end_time')))
            else:
                record["fill_status"] = "REJECTED"
                await self._async_log(f"EXECUTION REJECTED by exchange: {bias}")
                asyncio.create_task(self.notifier.send(f"REJECTED: {bias} {size} @ {target_ask}", level=AlertLevel.WARNING))
                await self.perf_logger.log(record)
        except Exception as e:
            await self._async_log(f"EXECUTION EXCEPTION: {type(e).__name__}: {e}")
            asyncio.create_task(self.notifier.send(f"EXCEPTION during execution: {e}", level=AlertLevel.CRITICAL))

    async def _poll_and_finalize(self, record, order_id, epoch_end_time):
        """Polls for order status and logs the final record."""
        try:
            final_status = await self.poller.poll_order(order_id, epoch_end_time=epoch_end_time)
            record["fill_status"] = final_status
            
            # Log to CSV
            await self.perf_logger.log(record)
        except Exception as e:
            logger.error(f"Finalize Error: {e}")

    def _get_effective_gap_threshold(self) -> float:
        """Returns the volatility-adjusted gap threshold, potentially gated by Binance OFI."""
        base_threshold = GAP_THRESHOLD_DEFAULT
        
        # Volatility Adjustment
        if GAP_VOL_NORMALIZATION:
            realized_vol = self.vol_estimator.get_realized_vol()
            if realized_vol > 0:
                base_threshold = max(GAP_THRESHOLD_DEFAULT, realized_vol * GAP_VOL_MULTIPLIER)
            
        # Binance OFI Conviction Logic
        if self.binance_feed and self.binance_feed.is_connected:
            bn_ofi = self.binance_feed.get_state()["ofi"]
            BINANCE_OFI_MIN = 5.0 # Noise filter
            
            # Feeds are aligned if both are positive (UP) or both negative (DOWN)
            feeds_aligned = (
                (self.bias == "UP" and bn_ofi > BINANCE_OFI_MIN) or
                (self.bias == "DOWN" and bn_ofi < -BINANCE_OFI_MIN)
            )
            
            is_neutral = abs(bn_ofi) < BINANCE_OFI_MIN
            
            if not feeds_aligned and not is_neutral:
                # Require 50% larger gap if spot market is actively fighting the perp trend
                return base_threshold * 1.5
                
        return base_threshold

    def get_state(self):
        return {
            "status": self.status,
            "slug": self.target_slug,
            "t_minus": self.t_minus,
            "gap": self.gap,
            "bias": self.bias,
            "gate_passed": self.gate_passed,
            "gap_pass": abs(self.gap) >= self.effective_gap_threshold,
            "cvd_pass": abs(self.hl_feed.get_state()["cvd"]) >= CVD_THRESHOLD_PCT,
            "vel_pass": abs(self.hl_feed.get_state()["velocity"]) >= VELOCITY_MIN_DELTA,
            "inventory_position": self.inventory_position,
            "inventory_risk": self.inventory_risk,
            "last_log": self.last_log,
            "effective_threshold": self.effective_gap_threshold,
            "binance_connected": self.binance_feed.is_connected if self.binance_feed else False
        }
