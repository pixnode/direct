import asyncio
import json
import websockets
import time
from collections import deque

class HyperliquidFeed:
    def __init__(self):
        self.ws_url = "wss://api.hyperliquid.xyz/ws"
        self.coin = "BTC"
        self.current_price = 0.0
        
        # Windows
        self.cvd_window_seconds = 300 # 5 minutes
        self.velocity_window_seconds = 2.0
        
        # Deques to store (timestamp, price, size, side)
        self.trades = deque()
        
        self.cvd_value = 0.0
        self.velocity_value = 0.0
        
        self.is_connected = False
        self.last_msg_time = 0.0

    async def connect(self):
        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    self.is_connected = True
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
                
                # Append to trades deque
                self.trades.append((ts, price, sz, side))
                
                # Cleanup old trades for CVD window
                self._cleanup_old_trades(ts)
                
                # Recalculate metrics
                self._calculate_metrics()

    def _cleanup_old_trades(self, current_ts):
        while self.trades and (current_ts - self.trades[0][0]) > max(self.cvd_window_seconds, self.velocity_window_seconds):
            self.trades.popleft()

    def _calculate_metrics(self):
        if not self.trades:
            return

        current_ts = self.trades[-1][0]
        
        # Calculate CVD
        cvd_buy = 0.0
        cvd_sell = 0.0
        
        # Calculate Velocity
        oldest_velocity_price = None
        newest_velocity_price = self.trades[-1][1]

        for trade in self.trades:
            ts, price, sz, side = trade
            
            # CVD Logic (last 5m)
            if (current_ts - ts) <= self.cvd_window_seconds:
                if side == "B":
                    cvd_buy += sz
                else:
                    cvd_sell += sz
                    
            # Velocity Logic (last 2s)
            if (current_ts - ts) <= self.velocity_window_seconds:
                if oldest_velocity_price is None:
                    oldest_velocity_price = price

        total_vol = cvd_buy + cvd_sell
        if total_vol > 0:
            # Net CVD % = (Buy - Sell) / Total * 100
            self.cvd_value = ((cvd_buy - cvd_sell) / total_vol) * 100.0
        else:
            self.cvd_value = 0.0

        if oldest_velocity_price is not None:
             # Velocity = Change in price over the 2 second window
            self.velocity_value = newest_velocity_price - oldest_velocity_price

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
