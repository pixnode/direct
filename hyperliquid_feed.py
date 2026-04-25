import asyncio
import json
import websockets
import time
import logging
from collections import deque
import config

logger = logging.getLogger("ADS_Engine")

class HyperliquidFeed:
    """
    Feed for Hyperliquid BTC Perpetual trades.
    Note: The 'cvd' metric calculated here is actually Order Flow Imbalance (OFI) 
    expressed as a percentage within the window, not a running Cumulative Volume Delta.
    """
    def __init__(self):
        self.ws_url = "wss://api.hyperliquid.xyz/ws"
        self.coin = "BTC"
        self.current_price = 0.0
        
        # Windows
        self.cvd_window_seconds = 60.0 # 1 minute
        self.velocity_window_seconds = 2.0
        
        # Deques to store (timestamp, price, size, side)
        self.cvd_trades = deque()
        self.vel_trades = deque()
        
        self.cvd_value = 0.0
        self.velocity_value = 0.0
        
        self.is_connected = False
        self.last_msg_time = 0.0

    async def connect(self):
        attempt = 0
        while True:
            try:
                backoff = min(0.5 * (2 ** attempt), config.MAX_RECONNECT_DELAY)
                if attempt > 0:
                    logger.warning(f"Hyperliquid: Reconnecting in {backoff:.1f}s (Attempt {attempt})")
                    await asyncio.sleep(backoff)

                async with websockets.connect(
                    self.ws_url,
                    ping_interval=config.WS_PING_INTERVAL,
                    ping_timeout=config.WS_PING_TIMEOUT,
                    close_timeout=5
                ) as ws:
                    self.is_connected = True
                    attempt = 0 # Reset on success
                    logger.info("Hyperliquid Feed Connected")
                    
                    # Subscribe to trades
                    subscribe_msg = {
                        "method": "subscribe",
                        "subscription": {"type": "trades", "coin": self.coin}
                    }
                    await ws.send(json.dumps(subscribe_msg))
                    
                    async for message in ws:
                        await self._process_message(message)
            except Exception as e:
                self.is_connected = False
                attempt += 1
                logger.error(f"Hyperliquid Connection Error: {e}")
                if attempt > 10: # Avoid infinite tight loop if something is fundamentally wrong
                    await asyncio.sleep(1)

    async def _process_message(self, message):
        self.last_msg_time = asyncio.get_event_loop().time()
        data = json.loads(message)
        if data.get("channel") == "trades":
            for trade in data["data"]:
                price = float(trade["px"])
                sz = float(trade["sz"])
                side = trade["side"] # "B" or "A" (buy or sell)
                ts = int(trade["time"]) / 1000.0 # to seconds
                
                self.current_price = price
                
                # Append to trades deques
                self.cvd_trades.append((ts, price, sz, side))
                self.vel_trades.append((ts, price, sz, side))
                
                # Cleanup old trades
                self._cleanup_old_trades(ts)
                
                # Recalculate metrics
                self._calculate_metrics()

    def _cleanup_old_trades(self, current_ts):
        while self.cvd_trades and (current_ts - self.cvd_trades[0][0]) > 60:
            self.cvd_trades.popleft()
        while self.vel_trades and (current_ts - self.vel_trades[0][0]) > 2:
            self.vel_trades.popleft()

    def _calculate_metrics(self):
        if not self.cvd_trades and not self.vel_trades:
            return

        # Calculate CVD
        cvd_buy = 0.0
        cvd_sell = 0.0
        for trade in self.cvd_trades:
            _, _, sz, side = trade
            if side == "B":
                cvd_buy += sz
            else:
                cvd_sell += sz

        total_vol = cvd_buy + cvd_sell
        if total_vol > 0:
            self.cvd_value = ((cvd_buy - cvd_sell) / total_vol) * 100.0
        else:
            self.cvd_value = 0.0

        # Calculate VWAP-based Velocity
        trades = list(self.vel_trades)
        if len(trades) >= 3:
            mid = len(trades) // 2
            early_trades = trades[:mid]
            late_trades = trades[mid:]
            
            def vwap(t_list):
                total_val = sum(p * s for _, p, s, _ in t_list)
                total_sz = sum(s for _, _, s, _ in t_list)
                return total_val / total_sz if total_sz > 0 else 0.0
            
            early_vwap = vwap(early_trades)
            late_vwap = vwap(late_trades)
            
            if early_vwap > 0:
                self.velocity_value = late_vwap - early_vwap
            else:
                self.velocity_value = 0.0
        else:
            self.velocity_value = 0.0

    async def run(self):
        await self.connect()

    def get_state(self):
        return {
            "price": self.current_price,
            "cvd": self.cvd_value,
            "velocity": self.velocity_value,
            "connected": self.is_connected,
            "last_msg_time": self.last_msg_time
        }
