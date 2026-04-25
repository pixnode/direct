import asyncio
import logging
import time

logger = logging.getLogger("ADS_Engine")

class OrderStatusPoller:
    def __init__(self, clob_client, thread_pool):
        self.client = clob_client
        self.thread_pool = thread_pool

    async def poll_order(self, order_id: str, epoch_end_time: int, interval: int = 10) -> str:
        """
        Polls for the status of an order until it reaches a terminal state 
        or the epoch ends (+ buffer).
        """
        if not order_id:
            return "unknown"

        # Timeout = remaining time in epoch + 30s buffer for settlement
        now_wall = time.time()
        timeout = max(30, (epoch_end_time - now_wall) + 30)

        loop = asyncio.get_event_loop()
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Offload sync API call to thread pool
                resp = await loop.run_in_executor(
                    self.thread_pool,
                    self.client.get_order,
                    order_id
                )
                
                # The response structure depends on the API version, 
                # but typically contains a 'status' field.
                # Common statuses: 'FILLED', 'CANCELED', 'EXPIRED', 'LIVE'
                status = resp.get("status", "unknown").upper()
                
                if status in ("FILLED", "CANCELED", "EXPIRED"):
                    logger.info(f"Poller: Order {order_id} reached terminal state: {status}")
                    return status
                
                # If still live, wait and poll again
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"Poller Error for order {order_id}: {e}")
                await asyncio.sleep(interval)

        logger.warning(f"Poller: Timeout reached for order {order_id}")
        return "timeout"
