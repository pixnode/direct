from eth_account import Account
import os
from dotenv import load_dotenv

load_dotenv(override=True)
pk = os.getenv("POLYMARKET_PRIVATE_KEY")

if pk:
    try:
        acc = Account.from_key(pk)
        print(f"Address derived from .env Private Key: {acc.address}")
    except Exception as e:
        print(f"Error: {e}")
else:
    print("POLYMARKET_PRIVATE_KEY not found in .env")
