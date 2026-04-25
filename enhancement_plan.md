# Implementation Plan - ADS v1.0 Enhancement Phase

Following the system refactor, this plan outlines the next steps to enhance the bot's strategy, monitoring, and data collection capabilities.

## User Review Required

> [!IMPORTANT]
> - **Telegram Integration**: You will need to provide a `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in your `.env` file for alerts to work.
> - **New Dependencies**: We may need to add `python-binance` or use raw WebSockets for the Binance feed.

## Proposed Changes

### 1. `performance_logger.py` [NEW]
- Create a dedicated class to log every trade attempt and its outcome into `trades.csv`.
- Fields: `timestamp`, `epoch`, `signal_type`, `bias`, `gap`, `cvd`, `velocity`, `price`, `status`, `latency`.

### 2. `notifier.py` [NEW]
- Implement a simple async Telegram client to send heartbeat summaries and trade notifications.
- Integrated into `DirectionalEngine`.

### 3. `binance_feed.py` [NEW]
- Implement a WebSocket feed for Binance BTCUSDT spot trades.
- Calculate Binance OFI (CVD) to serve as a co-signal to Hyperliquid Perp.
- Momentum is higher conviction if Perp and Spot agree.

### 4. `directional_engine.py` [MODIFY]
- Integrate `PerformanceLogger` and `Notifier`.
- **Adaptive Thresholds**: Normalize the `GAP` against recent volatility (ATR-like calculation or simple standard deviation).
- **Multi-Source Logic**: Add a check for Binance OFI alignment if the feed is enabled.

### 5. `config.py` [MODIFY]
- Add new configuration parameters for Telegram and Binance.
- Add `GAP_VOL_NORMALIZATION: bool = True`.

## Verification Plan

### Automated Tests
- Run the bot in simulation mode (if possible) or monitor logs to ensure CSV entries are created correctly.
- Trigger dummy alerts to verify Telegram connectivity.

### Manual Verification
- Observe the consistency between Binance and Hyperliquid signals in the logs.
- Verify that the CSV file can be opened and parsed by standard tools (Excel/Pandas).
