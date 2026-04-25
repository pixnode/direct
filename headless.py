import asyncio
import logging
import sys
from hyperliquid_feed import HyperliquidFeed
from poly_feed import PolyFeed
from directional_engine import DirectionalEngine

async def supervised(name: str, coro_factory, restart_delay: float = 5.0):
    """Restarts a coroutine if it crashes, with delay and logging."""
    attempt = 0
    while True:
        attempt += 1
        try:
            logging.info(f"[{name}] Starting (attempt {attempt})")
            await coro_factory()
            logging.warning(f"[{name}] Exited cleanly — restarting in {restart_delay}s")
        except asyncio.CancelledError:
            logging.info(f"[{name}] Cancelled. Shutting down.")
            raise
        except Exception as e:
            logging.error(f"[{name}] CRASHED (attempt {attempt}): {type(e).__name__}: {e}. Restarting in {restart_delay}s")
        
        await asyncio.sleep(restart_delay)

# Konfigurasi Logging sederhana untuk console
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

async def main():
    print("Starting ADS v1.0 in HEADLESS MODE...")
    
    # Initialize components
    hl_feed = HyperliquidFeed()
    poly_feed = PolyFeed()
    
    engine = DirectionalEngine(hl_feed, poly_feed)

    # Create tasks (Supervised)
    tasks = [
        asyncio.create_task(supervised("HL_Feed", hl_feed.run)),
        asyncio.create_task(supervised("Poly_Feed", poly_feed.run)),
        asyncio.create_task(supervised("Engine", engine.run)),
        asyncio.create_task(supervised("Perf_Logger", engine.perf_logger.run))
    ]
    
    if engine.binance_feed:
        tasks.append(asyncio.create_task(supervised("Binance_Feed", engine.binance_feed.run)))

    try:
        print("Engine is running. Monitoring via ads_execution.log")
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logging.error(f"System Error: {e}")
    finally:
        logging.info("Shutting down ADS Headless...")
        
        # 1. Flush and clean up resources BEFORE cancelling tasks
        await engine.perf_logger.stop()
        await engine.notifier.close()
        await engine.discovery.close()
        await engine.executor.shutdown()
        
        # 2. Cancel all tasks
        for task in tasks:
            task.cancel()
        
        await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete.")
        sys.exit(0)
