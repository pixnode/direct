import asyncio
import logging
import sys
from hyperliquid_feed import HyperliquidFeed
from poly_feed import PolyFeed
from directional_engine import DirectionalEngine
from ui import Dashboard

async def main():
    # Initialize components
    hl_feed = HyperliquidFeed()
    poly_feed = PolyFeed()
    
    engine = DirectionalEngine(hl_feed, poly_feed)
    dashboard = Dashboard(engine, hl_feed, poly_feed)

    # Create tasks
    tasks = [
        asyncio.create_task(hl_feed.run()),
        asyncio.create_task(poly_feed.run()),
        asyncio.create_task(engine.run()),
        asyncio.create_task(dashboard.run())
    ]

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
