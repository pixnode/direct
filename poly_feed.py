import asyncio
import json
import logging
import websockets
import config

logger = logging.getLogger("ADS_Engine")

class PolyFeed:
    def __init__(self):
        self.url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        self.token_id_up = None
        self.token_id_down = None
        self.strike_price = 0.0
        
        self.up_ask = 0.0
        self.down_ask = 0.0
        self.up_ask_updated_at = 0.0
        self.down_ask_updated_at = 0.0
        
        self.ws = None
        self.is_connected = False
        self.last_msg_time = 0.0

    def _safe_float(self, val, default=0.0) -> float:
        """Robust float parsing from various data types."""
        try:
            if val is None: return default
            f = float(val)
            return f if f > 0 else default
        except (TypeError, ValueError):
            return default

    async def update_subscription(self, token_up, token_down, strike):
        """Atomic-ish update of tokens and strike with immediate price reset."""
        # Update IDs
        self.token_id_up, self.token_id_down, self.strike_price = token_up, token_down, strike
        
        # Reset prices to prevent stale orders
        self.up_ask = 0.0
        self.down_ask = 0.0
        self.up_ask_updated_at = 0.0
        self.down_ask_updated_at = 0.0
        
        if self.ws and self.is_connected:
            try:
                sub_msg = {
                    "assets_ids": [self.token_id_up, self.token_id_down],
                    "type": "market",
                    "custom_feature_enabled": True
                }
                await self.ws.send(json.dumps(sub_msg))
                logger.info(f"PolyFeed: Subscribed to {token_up[:8]}... and {token_down[:8]}...")
            except Exception as e:
                logger.error(f"Poly Sub Error: {e}")

    async def run(self):
        attempt = 0
        while True:
            try:
                backoff = min(0.5 * (2 ** attempt), config.MAX_RECONNECT_DELAY)
                if attempt > 0:
                    logger.warning(f"Polymarket: Reconnecting in {backoff:.1f}s (Attempt {attempt})")
                    await asyncio.sleep(backoff)

                async with websockets.connect(
                    self.url,
                    ping_interval=config.WS_PING_INTERVAL,
                    ping_timeout=config.WS_PING_TIMEOUT,
                    close_timeout=5
                ) as ws:
                    self.ws = ws
                    self.is_connected = True
                    attempt = 0
                    logger.info("Polymarket Feed Connected")
                    
                    if self.token_id_up:
                        await self.update_subscription(self.token_id_up, self.token_id_down, self.strike_price)
                        
                    async for message in ws:
                        await self._process_message(message)
            except Exception as e:
                self.is_connected = False
                attempt += 1
                logger.error(f"Polymarket Feed Connection Error: {e}")
                await asyncio.sleep(1)

    async def _process_message(self, message):
        self.last_msg_time = asyncio.get_event_loop().time()
        try:
            data = json.loads(message)
            items = data if isinstance(data, list) else [data]
            
            for item in items:
                event_type = item.get("event_type")
                now = asyncio.get_event_loop().time()
                
                if event_type == "book":
                    asset_id = item.get("asset_id")
                    asks = item.get("asks", [])
                    if asks:
                        price = self._safe_float(asks[0].get("price", 0))
                        if price > 0:
                            if asset_id == self.token_id_up:
                                self.up_ask = price
                                self.up_ask_updated_at = now
                            elif asset_id == self.token_id_down:
                                self.down_ask = price
                                self.down_ask_updated_at = now
                
                elif event_type == "price_change":
                    changes = item.get("price_changes", [])
                    for change in changes:
                        asset_id = change.get("asset_id")
                        price = self._safe_float(change.get("best_ask", 0))
                        if price > 0:
                            if asset_id == self.token_id_up:
                                self.up_ask = price
                                self.up_ask_updated_at = now
                            elif asset_id == self.token_id_down:
                                self.down_ask = price
                                self.down_ask_updated_at = now
        except Exception:
            pass

    def get_state(self):
        now = asyncio.get_event_loop().time()
        
        # Return 0.0 if data is stale
        fresh_up = self.up_ask if (now - self.up_ask_updated_at) < config.ASK_STALENESS_THRESHOLD else 0.0
        fresh_down = self.down_ask if (now - self.down_ask_updated_at) < config.ASK_STALENESS_THRESHOLD else 0.0
        
        return {
            "up_ask": fresh_up,
            "down_ask": fresh_down,
            "strike_price": self.strike_price,
            "connected": self.is_connected,
            "last_msg_time": self.last_msg_time
        }
