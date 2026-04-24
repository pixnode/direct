import os
from dotenv import load_dotenv

load_dotenv()

# Execution Credentials
POLYMARKET_PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "")
POLYMARKET_HOST = os.getenv("POLYMARKET_HOST", "https://clob.polymarket.com")
CHAIN_ID = int(os.getenv("CHAIN_ID", "137"))

# Strategy Thresholds
GAP_THRESHOLD_DEFAULT = float(os.getenv("GAP_THRESHOLD_DEFAULT", "25.0"))
CVD_THRESHOLD_PCT = float(os.getenv("CVD_THRESHOLD_PCT", "45.0"))
VELOCITY_MIN_DELTA = float(os.getenv("VELOCITY_MIN_DELTA", "25.0"))
VELOCITY_WINDOW_SECONDS = float(os.getenv("VELOCITY_WINDOW_SECONDS", "2.0"))

# Sniper Parameters
SNIPER_ZONE_START = int(os.getenv("SNIPER_ZONE_START", "30"))
SNIPER_ZONE_END = int(os.getenv("SNIPER_ZONE_END", "15"))
OVERRIDE_GAP_THRESHOLD = float(os.getenv("OVERRIDE_GAP_THRESHOLD", "15.0"))

# Execution Parameters
DIRECTIONAL_MAX_ODDS = float(os.getenv("DIRECTIONAL_MAX_ODDS", "0.78"))
BASE_SHARES = float(os.getenv("BASE_SHARES", "1.0"))
HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL", "1.0"))

