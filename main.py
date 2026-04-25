import asyncio
import logging
import sys
from hyperliquid_feed import HyperliquidFeed
from poly_feed import PolyFeed
from directional_engine import DirectionalEngine
from ui import Dashboard

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

async def main():
    # Initialize components
    hl_feed = HyperliquidFeed()
    poly_feed = PolyFeed()
    
    engine = DirectionalEngine(hl_feed, poly_feed)
    dashboard = Dashboard(engine, hl_feed, poly_feed)

    # Create tasks (Supervised)
    tasks = [
        asyncio.create_task(supervised("HL_Feed", hl_feed.run)),
        asyncio.create_task(supervised("Poly_Feed", poly_feed.run)),
        asyncio.create_task(supervised("Engine", engine.run)),
        asyncio.create_task(supervised("Perf_Logger", engine.perf_logger.run)),
        asyncio.create_task(dashboard.run())
    ]
    
    if engine.binance_feed:
        tasks.append(asyncio.create_task(supervised("Binance_Feed", engine.binance_feed.run)))

    try:
        # Wait for any task to finish (which shouldn't happen unless error)
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        # This is expected on shutdown
        pass
    except Exception as e:
        logging.error(f"System Error: {e}")
    finally:
        # Shutdown sequence
        logging.info("Shutting down ADS v1.0...")
        
        # 1. Flush and clean up resources BEFORE cancelling tasks
        await engine.perf_logger.stop()
        await engine.notifier.close()
        await engine.discovery.close()
        await engine.executor.shutdown()
        
        # 2. Cancel all tasks
        for task in tasks:
            task.cancel()
        
        await asyncio.gather(*tasks, return_exceptions=True)
        logging.info("All tasks stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Minimalist cleanup for terminal
        print("\n[bold red]SHUTDOWN SIGNAL RECEIVED[/]")
        sys.exit(0)
