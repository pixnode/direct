import asyncio
import json
import logging
import websockets

logger = logging.getLogger("ADS_Engine")

class PolyFeed:
    def __init__(self):
        self.url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        self.token_id_up = None
        self.token_id_down = None
        self.strike_price = 0.0
        
        self.up_ask = 0.0
        self.down_ask = 0.0
        self.ws = None
        self.is_connected = False
        self.last_msg_time = 0.0

    async def update_subscription(self, token_up, token_down, strike):
        self.token_id_up = token_up
        self.token_id_down = token_down
        self.strike_price = strike
        
        if self.ws and self.is_connected:
            try:
                sub_msg = {
                    "assets_ids": [self.token_id_up, self.token_id_down],
                    "type": "market",
                    "custom_feature_enabled": True
                }
                await self.ws.send(json.dumps(sub_msg))
            except Exception as e:
                logger.error(f"Poly Sub Error: {e}")

    async def run(self):
        while True:
            try:
                async with websockets.connect(self.url) as ws:
                    self.ws = ws
                    self.is_connected = True
                    logger.info("Polymarket Feed Connected")
                    
                    if self.token_id_up:
                        await self.update_subscription(self.token_id_up, self.token_id_down, self.strike_price)
                        
                    async for message in ws:
                        await self._process_message(message)
            except Exception as e:
                self.is_connected = False
                logger.error(f"Polymarket Feed Disconnected: {e}")
                await asyncio.sleep(5)

    async def _process_message(self, message):
        self.last_msg_time = asyncio.get_event_loop().time()
        try:
            data = json.loads(message)
            items = data if isinstance(data, list) else [data]
            
            for item in items:
                event_type = item.get("event_type")
                
                if event_type == "book":
                    asset_id = item.get("asset_id")
                    asks = item.get("asks", [])
                    if asks:
                        price = float(asks[0].get("price", 0))
                        if asset_id == self.token_id_up:
                            self.up_ask = price
                        elif asset_id == self.token_id_down:
                            self.down_ask = price
                
                elif event_type == "price_change":
                    changes = item.get("price_changes", [])
                    for change in changes:
                        asset_id = change.get("asset_id")
                        price = float(change.get("best_ask", 0))
                        if asset_id == self.token_id_up:
                            self.up_ask = price
                        elif asset_id == self.token_id_down:
                            self.down_ask = price
        except Exception:
            pass

    def get_state(self):
        return {
            "up_ask": self.up_ask,
            "down_ask": self.down_ask,
            "strike_price": self.strike_price,
            "connected": self.is_connected,
            "last_msg_time": self.last_msg_time
        }
