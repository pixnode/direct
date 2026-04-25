import asyncio
import json
import websockets
import time
import logging
from collections import deque
import config

logger = logging.getLogger("ADS_Engine")

class BinanceFeed:
    """
    Feed for Binance BTCUSDT Spot trades using raw WebSockets.
    Calculates Order Flow Imbalance (OFI).
    """
    WS_URL = "wss://stream.binance.com:9443/ws/btcusdt@aggTrade"
    
    def __init__(self):
        self.ofi_window_seconds = config.BINANCE_OFI_WINDOW
        self.trades = deque()
        self.ofi_value = 0.0
        self.current_price = 0.0
        self.is_connected = False
        self.last_msg_time = 0.0

    async def connect(self):
        attempt = 0
        while True:
            try:
                if not config.BINANCE_FEED_ENABLED:
                    await asyncio.sleep(60)
                    continue

                backoff = min(0.5 * (2 ** attempt), config.MAX_RECONNECT_DELAY)
                if attempt > 0:
                    logger.warning(f"Binance: Reconnecting in {backoff:.1f}s (Attempt {attempt})")
                    await asyncio.sleep(backoff)

                async with websockets.connect(
                    self.WS_URL,
                    ping_interval=config.WS_PING_INTERVAL,
                    ping_timeout=config.WS_PING_TIMEOUT,
                    close_timeout=5
                ) as ws:
                    self.is_connected = True
                    attempt = 0
                    logger.info("Binance Spot Feed Connected")
                    
                    async for message in ws:
                        await self._process_message(message)
            except Exception as e:
                self.is_connected = False
                attempt += 1
                logger.error(f"Binance Connection Error: {e}")
                await asyncio.sleep(1)

    async def _process_message(self, message):
        self.last_msg_time = asyncio.get_event_loop().time()
        try:
            data = json.loads(message)
            # Binance aggTrade format:
            # {
            #   "T": 1234567890, (ms)
            #   "p": "95000.00",
            #   "q": "0.001",
            #   "m": true (true = SELL, false = BUY)
            # }
            price = float(data["p"])
            quantity = float(data["q"])
            is_sell = data["m"]
            ts = int(data["T"]) / 1000.0 # to seconds
            
            self.current_price = price
            side = "S" if is_sell else "B"
            
            self.trades.append((ts, price, quantity, side))
            
            # Cleanup and Recalculate
            while self.trades and (ts - self.trades[0][0]) > self.ofi_window_seconds:
                self.trades.popleft()
            
            self._calculate_ofi()
        except Exception as e:
            logger.debug(f"Binance Message Error: {e}")

    def _calculate_ofi(self):
        if not self.trades:
            self.ofi_value = 0.0
            return

        buy_vol = sum(t[2] for t in self.trades if t[3] == "B")
        sell_vol = sum(t[2] for t in self.trades if t[3] == "S")
        total_vol = buy_vol + sell_vol
        
        if total_vol > 0:
            self.ofi_value = ((buy_vol - sell_vol) / total_vol) * 100.0
        else:
            self.ofi_value = 0.0

    def get_state(self):
        return {
            "price": self.current_price,
            "ofi": self.ofi_value,
            "connected": self.is_connected,
            "last_msg_time": self.last_msg_time
        }

    async def run(self):
        await self.connect()
