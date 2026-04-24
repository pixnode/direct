# ADS v1.0: Hybrid Sniper (Predator)

ADS (Asynchronous Directional Sniper) v1.0 is a high-performance, ultra-lean trading engine designed for directional market execution on Polymarket. This version integrates the "Hyper-Sniper" (Predator) logic for aggressive 5-minute window execution.

## Key Features
- **Temporal State Machine**: Operates in four distinct phases: `IDLE`, `WARMING_UP`, `SNIPER_ZONE`, and `CEASE_FIRE`.
- **Predator Logic**: 
    - **Directional Veto**: Shields against false signals by checking CVD alignment.
    - **Hyper-Sniper Override**: Forces execution when price gaps exceed critical thresholds, bypassing standard confirmation gates.
- **Atomic Execution**: Zero-slippage limit orders with asynchronous non-blocking I/O.
- **Real-time Dashboard**: Beautiful terminal UI powered by `rich`.

## Installation

### Prerequisites
- Python 3.8 or higher
- A Polymarket private key with funds on Polygon (MATIC)

### Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/pixnode/direct.git
   cd direct
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   Create a `.env` file in the root directory (refer to `.env.example` or use the format below):
   ```env
   POLYMARKET_PRIVATE_KEY=your_private_key
   POLYMARKET_HOST=https://clob.polymarket.com
   CHAIN_ID=137

   # Sniper Thresholds
   SNIPER_ZONE_START=30
   SNIPER_ZONE_END=15
   OVERRIDE_GAP_THRESHOLD=15.0

   # Execution
   BASE_SHARES=1.0
   DIRECTIONAL_MAX_ODDS=0.78
   ```

## Running the Application

### Start the Sniper Bot
To launch the trading engine with the real-time UI dashboard:
```bash
python main.py
```

## UI Dashboard Guide
The dashboard is split into three main panels:
1. **Header**: Shows current target window (slug), T-Minus countdown, and Engine Status.
2. **Market Panel**: Displays live HL spot price, Polymarket strike, and Triple Confirmation gate status (GAP, CVD, Velocity).
3. **Inventory Panel**: Shows current position, risk in USD, and target odds limits.
4. **Logs**: Real-time execution logs and heartbeat monitoring.

## Safety Protocols
- **Anti-Membabi Buta**: Prevents order spamming using atomic locks (`order_sent`).
- **Cease Fire**: Automatically locks all execution when T-Minus < 15s to avoid latency risks.
- **Zero-Slippage**: Always attempts to buy at the exact ASK price using limit orders.

---
**Disclaimer**: This bot is for educational purposes. Trading involves risk. Use at your own discretion.

# Matikan yang lama jika ada
pm2 stop ads
# Jalankan mode headless
pm2 start headless.py --name ads --interpreter python3

git pull origin main
source venv/bin/activate
pip install -r requirements.txt
pm2 start headless.py --name ads-sniper --interpreter python3
tail -f ads_execution.log
