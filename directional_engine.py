import asyncio
import time
import logging
from config import (
    GAP_THRESHOLD_DEFAULT, CVD_THRESHOLD_PCT, VELOCITY_MIN_DELTA, 
    DIRECTIONAL_MAX_ODDS, BASE_SHARES, SNIPER_ZONE_START, 
    SNIPER_ZONE_END, OVERRIDE_GAP_THRESHOLD
)
from discovery import MarketDiscovery
from executor import Executor

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
        
        # UI state
        self.last_log = "Engine Initialized"
        self.inventory_position = "NONE"
        self.inventory_risk = 0.0

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
                    await self._async_log(f"NETWORK: New Epoch Detected: {epoch}")
                    self.current_epoch = epoch
                    self.token_up = None
                
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
                # Reload Peluru Logic
                current_window = int(now - (now % 300))
                if current_window != self.window_start:
                    self.window_start = current_window
                    self.order_sent = False
                    self.status = "IDLE"
                    await self._async_log(f"RELOAD: New Window Started @ {self.window_start}")

                # State Machine based on t_minus
                if self.t_minus > 60:
                    self.status = "IDLE"
                elif 30 < self.t_minus <= 60:
                    self.status = "WARMING_UP"
                elif SNIPER_ZONE_END <= self.t_minus <= SNIPER_ZONE_START:
                    self.status = "SNIPER_ZONE"
                elif self.t_minus < SNIPER_ZONE_END:
                    self.status = "CEASE_FIRE"

                hl_state = self.hl_feed.get_state()
                poly_state = self.poly_feed.get_state()
                
                hl_price = hl_state["price"]
                strike = poly_state["strike_price"]
                cvd = hl_state["cvd"]
                velocity = hl_state["velocity"]
                
                if now - last_heartbeat > 10:
                    # Determine gate status for logging
                    g_ok = "OK" if abs_gap > GAP_THRESHOLD_DEFAULT else "FAIL"
                    c_ok = "OK" if ((self.bias == "UP" and cvd > CVD_THRESHOLD_PCT) or (self.bias == "DOWN" and cvd < -CVD_THRESHOLD_PCT)) else "FAIL"
                    v_ok = "OK" if abs_velocity > VELOCITY_MIN_DELTA else "FAIL"
                    
                    hb_msg = (
                        f"HEARTBEAT | STAT:{self.status} | T-{self.t_minus}s | "
                        f"P:{hl_price:,.2f} | S:{current_strike:,.2f} | "
                        f"G:{abs_gap:.2f}({g_ok}) | C:{cvd:.1f}%({c_ok}) | "
                        f"V:{abs_velocity:.1f}({v_ok}) | BIAS:{self.bias}"
                    )
                    await self._async_log(hb_msg)
                    last_heartbeat = now

                # Sync Strike
                current_strike = strike
                if current_strike == 0 and hl_price > 0:
                    if self.reference_price == 0:
                        self.reference_price = hl_price
                        await self._async_log(f"REFERENCE SET: {self.reference_price}")
                    current_strike = self.reference_price

                # Directional Logic
                if current_strike > 0 and hl_price > 0:
                    self.gap = hl_price - current_strike
                    self.bias = "UP" if self.gap > 0 else "DOWN" if self.gap < 0 else "NONE"

                abs_gap = abs(self.gap)
                abs_velocity = abs(velocity)
                
                # Predator Decision Logic
                veto = False
                if self.bias == "UP" and cvd < -30:
                    veto = True
                elif self.bias == "DOWN" and cvd > 30:
                    veto = True

                # Override vs Normal
                trigger_reason = ""
                if abs_gap >= OVERRIDE_GAP_THRESHOLD:
                    self.gate_passed = True
                    trigger_reason = "Hyper-Sniper Override"
                else:
                    gap_pass = abs_gap > GAP_THRESHOLD_DEFAULT
                    cvd_pass = not veto and ((self.bias == "UP" and cvd > CVD_THRESHOLD_PCT) or (self.bias == "DOWN" and cvd < -CVD_THRESHOLD_PCT))
                    vel_pass = abs_velocity > VELOCITY_MIN_DELTA
                    self.gate_passed = gap_pass and cvd_pass and vel_pass
                    trigger_reason = "Triple Confirmation"

                # Execution Block
                if self.status == "SNIPER_ZONE" and self.gate_passed and not self.order_sent and self.token_up:
                    target_ask = poly_state["up_ask"] if self.bias == "UP" else poly_state["down_ask"]
                    
                    if 0 < target_ask <= DIRECTIONAL_MAX_ODDS:
                        # Atomic Lock
                        self.order_sent = True
                        
                        await self._async_log(f"🎯 TRIGGER: {trigger_reason} | {self.bias} Gap:{abs_gap:.2f} CVD:{cvd:.1f}")
                        
                        # Non-Blocking Call
                        asyncio.create_task(self.executor.execute(
                            bias=self.bias,
                            size=BASE_SHARES,
                            target_ask=target_ask,
                            token_up=self.token_up,
                            token_down=self.token_down
                        ))
                        
                        self.inventory_position = self.bias
                        self.inventory_risk += (BASE_SHARES * target_ask)

            except Exception as e:
                await self._async_log(f"LOOP ERROR: {e}")
            
            await asyncio.sleep(0.01)

    def get_state(self):
        return {
            "status": self.status,
            "slug": self.target_slug,
            "t_minus": self.t_minus,
            "gap": self.gap,
            "bias": self.bias,
            "gate_passed": self.gate_passed,
            "gap_pass": abs(self.gap) > GAP_THRESHOLD_DEFAULT,
            "cvd_pass": abs(self.hl_feed.get_state()["cvd"]) > CVD_THRESHOLD_PCT,
            "vel_pass": abs(self.hl_feed.get_state()["velocity"]) > VELOCITY_MIN_DELTA,
            "inventory_position": self.inventory_position,
            "inventory_risk": self.inventory_risk,
            "last_log": self.last_log
        }
