import asyncio
import aiohttp
import time
import logging

logger = logging.getLogger("ADS_Engine")

class MarketDiscovery:
    def __init__(self):
        self.gamma_api_url = "https://gamma-api.polymarket.com/events"
        self._session = None

    async def _get_session(self):
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=10, connect=5)
            )
        return self._session

    async def close(self):
        """Cleanup session on shutdown."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("MarketDiscovery: Session closed.")

    def get_current_epoch(self):
        # Current 5-minute epoch start time
        now = int(time.time())
        return now - (now % 300)

    def get_next_epoch(self):
        return self.get_current_epoch() + 300

    async def discover_tokens(self, epoch):
        slug = f"btc-updown-5m-{epoch}"
        # Use /markets endpoint which returns a list of market objects
        url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
        
        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        market = data[0]
                        condition_id = market.get("conditionId")
                            
                        # clobTokenIds is often a stringified JSON list in /markets response
                        clob_tokens_raw = market.get("clobTokenIds", "[]")
                        import json
                        try:
                            tokens = json.loads(clob_tokens_raw)
                        except:
                            # Fallback to standard tokens field if available
                            tokens_list = market.get("tokens", [])
                            tokens = [t.get("token_id") for t in tokens_list] if tokens_list else []

                        if len(tokens) >= 2:
                            token_up = tokens[0]
                            token_down = tokens[1]
                            
                            strike = self._parse_strike(market)

                            return {
                                "slug": slug,
                                "condition_id": condition_id,
                                "token_up": token_up,
                                "token_down": token_down,
                                "strike": strike,
                                "start_time": market.get("eventStartTime") or market.get("startTime")
                            }
        except Exception as e:
            logger.error(f"Discovery Error for {slug}: {e}")
        return None

    def _parse_strike(self, market: dict) -> float:
        """Parse strike price with fallback chain and range validation."""
        BTC_MIN, BTC_MAX = 1000.0, 1000000.0
        
        def validate(p):
            return p if BTC_MIN < p < BTC_MAX else 0.0

        # Try groupItemTitle
        try:
            group_item = market.get("groupItemTitle", "")
            if group_item and group_item != "0":
                parts = group_item.split()
                strike_str = parts[-1].replace("$", "").replace(",", "")
                p = validate(float(strike_str))
                if p > 0: return p
        except:
            pass

        # Try question regex
        try:
            question = market.get("question", "")
            import re
            match = re.search(r'\$([\d,]+\.?\d*)', question)
            if match:
                p = validate(float(match.group(1).replace(",", "")))
                if p > 0: return p
        except:
            pass

        logger.warning(f"MarketDiscovery: Could not parse strike for {market.get('slug', 'unknown')}")
        return 0.0
