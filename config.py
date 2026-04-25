import os
import sys
from dotenv import load_dotenv

# Strict load — error if not found
if not load_dotenv(override=True):
    print("FATAL: .env file not found. Cannot start.", file=sys.stderr)
    sys.exit(1)

def _require(key: str, cast=str):
    val = os.getenv(key)
    if not val:
        print(f"FATAL: Required env var '{key}' is missing or empty.", file=sys.stderr)
        sys.exit(1)
    try:
        return cast(val)
    except (ValueError, TypeError) as e:
        print(f"FATAL: Cannot parse '{key}': {e}", file=sys.stderr)
        sys.exit(1)

def _optional(key: str, default, cast=str):
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return cast(val)
    except (ValueError, TypeError):
        return default

# Execution Credentials — REQUIRED
POLYMARKET_PRIVATE_KEY    = _require("POLYMARKET_PRIVATE_KEY")
POLYMARKET_API_KEY        = _require("POLYMARKET_API_KEY")
POLYMARKET_API_SECRET     = _require("POLYMARKET_API_SECRET")
POLYMARKET_API_PASSPHRASE = _require("POLYMARKET_API_PASSPHRASE")
POLYMARKET_HOST           = _optional("POLYMARKET_HOST", "https://clob.polymarket.com")
CHAIN_ID                  = _optional("CHAIN_ID", 137, int)

# Strategy Thresholds
GAP_THRESHOLD_DEFAULT     = _optional("GAP_THRESHOLD_DEFAULT", 45.0, float)
CVD_THRESHOLD_PCT         = _optional("CVD_THRESHOLD_PCT", 15.0, float)   # SYNC with .env (was 25.0)
VELOCITY_MIN_DELTA        = _optional("VELOCITY_MIN_DELTA", 3.0, float)   # SYNC with .env (was 15.0)
VELOCITY_WINDOW_SECONDS   = _optional("VELOCITY_WINDOW_SECONDS", 2.0, float)

# Sniper Parameters (Dual Window)
CONFIRMATION_WINDOW_START = _optional("CONFIRMATION_WINDOW_START", 45, int)  # SYNC with .env (was 120)
OVERRIDE_WINDOW_START     = _optional("OVERRIDE_WINDOW_START", 90, int)      # SYNC with .env (was 25)
SNIPER_ZONE_END           = _optional("SNIPER_ZONE_END", 15, int)
OVERRIDE_GAP_THRESHOLD    = _optional("OVERRIDE_GAP_THRESHOLD", 90.0, float)

# Execution Parameters
DIRECTIONAL_MAX_ODDS      = _optional("DIRECTIONAL_MAX_ODDS", 0.78, float)
BASE_SHARES               = _optional("BASE_SHARES", 1.0, float)
HEARTBEAT_INTERVAL        = _optional("HEARTBEAT_INTERVAL", 1.0, float)

# New Parameters
VETO_MULTIPLIER           = _optional("VETO_MULTIPLIER", 2.0, float)
ASK_STALENESS_THRESHOLD   = _optional("ASK_STALENESS_THRESHOLD", 10.0, float)
WS_PING_INTERVAL          = _optional("WS_PING_INTERVAL", 20.0, float)
WS_PING_TIMEOUT           = _optional("WS_PING_TIMEOUT", 10.0, float)
MAX_RECONNECT_DELAY       = _optional("MAX_RECONNECT_DELAY", 30.0, float)
ORDER_EXPIRY_BUFFER       = _optional("ORDER_EXPIRY_BUFFER", 10, int)
MAX_ORDER_RETRIES         = _optional("MAX_ORDER_RETRIES", 2, int)

# --- Enhancement Phase Parameters ---

# Telegram
TELEGRAM_BOT_TOKEN        = _optional("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID          = _optional("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED          = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# Binance Feed
BINANCE_FEED_ENABLED      = _optional("BINANCE_FEED_ENABLED", "False", str).lower() == "true"
BINANCE_OFI_WINDOW        = _optional("BINANCE_OFI_WINDOW", 60.0, float)

# Adaptive Threshold
GAP_VOL_NORMALIZATION     = _optional("GAP_VOL_NORMALIZATION", "True", str).lower() == "true"
GAP_VOL_MULTIPLIER        = _optional("GAP_VOL_MULTIPLIER", 1.5, float)
VOL_ESTIMATOR_WINDOW      = _optional("VOL_ESTIMATOR_WINDOW", 20, int)

# Sanity Check Assertions
assert 0 < GAP_THRESHOLD_DEFAULT < 10000, "GAP_THRESHOLD out of range"
assert 0 < CVD_THRESHOLD_PCT < 100, "CVD_THRESHOLD must be 0-100%"
assert 0 < DIRECTIONAL_MAX_ODDS <= 1.0, "MAX_ODDS must be 0-1"
assert SNIPER_ZONE_END < CONFIRMATION_WINDOW_START < OVERRIDE_WINDOW_START, "Window config invalid"

