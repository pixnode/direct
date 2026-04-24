import asyncio
import logging
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

    # Run tasks concurrently
    try:
        await asyncio.gather(
            hl_feed.run(),
            poly_feed.run(),
            engine.run(),
            dashboard.run()
        )
    except asyncio.CancelledError:
        logging.info("ADS Shutting down...")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete.")
