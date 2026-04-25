import asyncio
import aiohttp
import time
import logging
import config

logger = logging.getLogger("ADS_Engine")

class AlertLevel:
    DEBUG = 0
    INFO = 1
    TRADE = 2
    WARNING = 3
    CRITICAL = 4

class Notifier:
    def __init__(self):
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.enabled = config.TELEGRAM_ENABLED
        self._last_sent = {}
        self._session = None
        # Rate limit intervals in seconds
        self._min_intervals = {
            AlertLevel.INFO: 60,
            AlertLevel.TRADE: 0,
            AlertLevel.WARNING: 30,
            AlertLevel.CRITICAL: 0
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def close(self):
        """Cleanup session on shutdown."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("Notifier: Session closed.")

    async def send(self, msg: str, level: int = AlertLevel.INFO):
        """Sends a notification to Telegram with rate limiting."""
        if not self.enabled:
            return

        now = time.time()
        # Throttle logic
        if level in self._min_intervals:
            last_time = self._last_sent.get(level, 0)
            if now - last_time < self._min_intervals[level]:
                return

        try:
            prefix = {
                AlertLevel.INFO: "ℹ️ [INFO]",
                AlertLevel.TRADE: "🎯 [TRADE]",
                AlertLevel.WARNING: "⚠️ [WARNING]",
                AlertLevel.CRITICAL: "🚨 [CRITICAL]"
            }.get(level, "")
            
            full_msg = f"{prefix} {msg}"
            
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": full_msg,
                "parse_mode": "Markdown"
            }
            
            session = await self._get_session()
            async with session.post(url, json=payload, timeout=10) as response:
                if response.status == 200:
                    self._last_sent[level] = now
                else:
                    resp_text = await response.text()
                    logger.error(f"Telegram Notifier Failed: {resp_text}")
        except Exception as e:
            logger.error(f"Notifier Error: {e}")
