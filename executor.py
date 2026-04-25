import logging
import asyncio
import time
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs
import config

logger = logging.getLogger("ADS_Engine")

class Executor:
    def __init__(self):
        try:
            # Initialize the Real ClobClient
            self.client = ClobClient(
                host=config.POLYMARKET_HOST, 
                key=config.POLYMARKET_PRIVATE_KEY, 
                chain_id=config.CHAIN_ID
            )
            
            # Apply API Credentials if available
            if config.POLYMARKET_API_KEY:
                self.client.set_api_creds(
                    config.POLYMARKET_API_KEY, 
                    config.POLYMARKET_API_SECRET, 
                    config.POLYMARKET_API_PASSPHRASE
                )
                logger.info("Executor: API Credentials applied successfully.")
            else:
                logger.error("FATAL: POLYMARKET_API_KEY kosong di .env")
                logger.error("Jalankan: python scripts/setup_credentials.py")
                self.is_ready = False
                return

            self.is_ready = True
            logger.info("Executor: Real ClobClient Initialized (LIVE MODE)")
        except Exception as e:
            self.is_ready = False
            logger.error(f"Executor Initialization Failed: {e}")

    async def execute(self, bias, size, target_ask, token_up, token_down):
        if not self.is_ready:
            if not config.POLYMARKET_API_KEY:
                logger.warning("WARNING: No API creds set")
            logger.error("Executor not ready. Skipping trade.")
            return False

        token_to_buy = token_up if bias == "UP" else token_down
        
        try:
            # Place a real LIMIT order on Polymarket
            # We use GTC (Good Till Cancelled) by default
            expiry = int(time.time()) + 280 # 4 menit 40 detik
            
            logger.info(f"Order Sending: Token={token_to_buy}, Price={target_ask}, Size={size}")
            
            order_args = OrderArgs(
                price=target_ask,
                size=size,
                side="BUY",
                token_id=token_to_buy,
                expiration=expiry
            )
            
            # Post the order to the CLOB
            resp = self.client.create_and_post_order(order_args)
            logger.info(f"Full Response: {resp}")
            
            if resp and resp.get("success"):
                logger.info(f"LIVE EXECUTED: BUY {bias} | Size: {size} | Token: {token_to_buy} @ {target_ask}")
                return True
            else:
                logger.error(f"LIVE EXECUTION REJECTED: {resp}")
                return False
                
        except Exception as e:
            logger.error(f"Live Execution Error: {e}")
            return False
