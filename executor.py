import logging
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, BalanceAllowanceParams, AssetType
import config

logger = logging.getLogger("ADS_Engine")

class Executor:
    def __init__(self):
        self._thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="clob_exec")
        self.is_ready = False
        try:
            # Initialize the Real ClobClient
            self.client = ClobClient(
                host=config.POLYMARKET_HOST, 
                key=config.POLYMARKET_PRIVATE_KEY, 
                chain_id=config.CHAIN_ID,
                funder=config.POLYMARKET_FUNDER_ADDRESS,
                signature_type=1
            )
            
            from py_clob_client.clob_types import ApiCreds
            
            # Apply API Credentials
            creds = ApiCreds(
                api_key=config.POLYMARKET_API_KEY, 
                api_secret=config.POLYMARKET_API_SECRET, 
                api_passphrase=config.POLYMARKET_API_PASSPHRASE
            )
            self.client.set_api_creds(creds)
            
            self.is_ready = True
            logger.info("Executor: Real ClobClient Initialized (LIVE MODE)")
        except Exception as e:
            logger.error(f"Executor Initialization Failed: {e}")

    def get_balance(self):
        """Fetches available USDC balance from CLOB API (no RPC needed)."""
        if not self.is_ready: return 0.0
        try:
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            resp = self.client.get_balance_allowance(params)
            # Response is a dict containing 'balance' and 'allowance' strings
            return float(resp.get('balance', 0.0))
        except Exception as e:
            logger.error(f"Executor: Failed to fetch balance: {e}")
            return 0.0

    async def execute(self, bias, size, target_ask, token_up, token_down, epoch_end_time):
        """
        Executes a trade on Polymarket CLOB in a non-blocking manner.
        Includes retry logic for network errors.
        """
        if not self.is_ready:
            logger.error("Executor not ready. Skipping trade.")
            return False, None

        token_to_buy = token_up if bias == "UP" else token_down
        
        # Format values with strict precision (Polymarket standard)
        # Price: max 2-4 decimals, Size: max 6 decimals
        clean_price = round(float(target_ask), 4)
        clean_size = round(float(size), 6)
        
        # Balance Awareness Check
        balance = self.get_balance()
        cost = clean_price * clean_size
        if balance < cost:
            logger.error(f"ABORT EXECUTION: Insufficient Balance! Need ${cost:.2f}, Have ${balance:.2f}")
            return False, None

        # Expiry: Use 0 for GTC as per recent successful trials
        expiry = 0
        
        try:
            logger.info(f"Order Attempt: {bias} | Token={token_to_buy} | Price={clean_price} | Size={clean_size} | Expiry={expiry}")
            
            order_args = OrderArgs(
                price=clean_price,
                size=clean_size,
                side="BUY",
                token_id=token_to_buy,
                expiration=expiry
            )
            
            loop = asyncio.get_event_loop()
            
            for attempt in range(config.MAX_ORDER_RETRIES + 1):
                try:
                    # Post the order to the CLOB (Offloaded to thread pool)
                    resp = await loop.run_in_executor(
                        self._thread_pool,
                        self.client.create_and_post_order,
                        order_args
                    )
                    
                    if resp and resp.get("success"):
                        order_id = resp.get("orderID")
                        logger.info(f"LIVE EXECUTED: BUY {bias} | Size: {size} | Token: {token_to_buy} @ {target_ask} | ID: {order_id}")
                        return True, order_id
                    else:
                        # Rejection from exchange - do not retry
                        logger.error(f"LIVE EXECUTION REJECTED: {resp}")
                        return False, None
                        
                except Exception as e:
                    if attempt < config.MAX_ORDER_RETRIES:
                        delay = 0.1 * (attempt + 1)
                        logger.warning(f"Order Attempt {attempt+1} failed ({type(e).__name__}: {e}). Retrying in {delay}s...")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"Order Failed after {attempt+1} attempts: {e}")
                        return False, None
                
        except Exception as e:
            logger.error(f"Critical Execution Error: {e}")
            return False, None

    async def shutdown(self):
        """Clean shutdown of thread pool."""
        logger.info("Executor: Shutting down thread pool...")
        self._thread_pool.shutdown(wait=False)
