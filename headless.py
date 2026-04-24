import asyncio
import logging
import sys
from hyperliquid_feed import HyperliquidFeed
from poly_feed import PolyFeed
from directional_engine import DirectionalEngine

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
    print("🚀 Starting ADS v1.0 in HEADLESS MODE...")
    
    # Initialize components
    hl_feed = HyperliquidFeed()
    poly_feed = PolyFeed()
    
    engine = DirectionalEngine(hl_feed, poly_feed)

    # Create tasks (Tanpa Dashboard)
    tasks = [
        asyncio.create_task(hl_feed.run()),
        asyncio.create_task(poly_feed.run()),
        asyncio.create_task(engine.run())
    ]

    try:
        print("✅ Engine is running. Monitoring via ads_execution.log")
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logging.error(f"System Error: {e}")
    finally:
        logging.info("Shutting down ADS Headless...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete.")
        sys.exit(0)
