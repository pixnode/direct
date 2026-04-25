import logging
import time
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
import config

# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("Wallet_Diag")

def diagnose():
    print("\n--- ADS v1.0 Wallet & API Diagnostic ---")
    
    # 1. Check Credentials
    print(f"\n[1] Checking Credentials...")
    print(f"    - Host: {config.POLYMARKET_HOST}")
    print(f"    - Wallet: {config.POLYMARKET_PRIVATE_KEY[:6]}...{config.POLYMARKET_PRIVATE_KEY[-4:]}")
    print(f"    - API Key: {config.POLYMARKET_API_KEY[:6]}...")
    
    try:
        # 2. Initialize Client
        print(f"\n[2] Initializing ClobClient...")
        client = ClobClient(
            host=config.POLYMARKET_HOST, 
            key=config.POLYMARKET_PRIVATE_KEY, 
            chain_id=config.CHAIN_ID,
            funder=config.POLYMARKET_FUNDER_ADDRESS,
            signature_type=1
        )
        
        creds = ApiCreds(
            api_key=config.POLYMARKET_API_KEY, 
            api_secret=config.POLYMARKET_API_SECRET, 
            api_passphrase=config.POLYMARKET_API_PASSPHRASE
        )
        client.set_api_creds(creds)
        print("    [OK] Client Initialized")

        # 3. Check Balance
        print(f"\n[3] Fetching Balance & Allowance (USDC)...")
        from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        data = client.get_balance_allowance(params)
        
        balance = data.get("balance", "0")
        allowance = data.get("allowance", "0")
        
        print(f"    Available Balance: ${balance}")
        print(f"    Current Allowance: ${allowance}")
        
        if float(balance) <= 0:
            print("    [WARN] Balance is 0! Please deposit USDC to Polygon.")
        else:
            print("    [OK] Balance OK")

        # 4. Check Allowance
        print(f"\n[4] Checking Allowance...")
        if float(allowance) < 1.0:
            print("    [WARN] Allowance is low or 0.")
            print("    [ACTION] Please go to Polymarket.com -> Profile -> Wallet and click 'Approve' for USDC.")
        else:
            print("    [OK] Allowance is set.")

        print("\n--- Diagnostic Complete ---")
        if float(balance) > 0:
            print("\nSYSTEM READY: You can start the bot now.")
        else:
            print("\nSYSTEM NOT READY: Fix balance issues first.")

    except Exception as e:
        print(f"\n[ERROR] FATAL ERROR during diagnostic: {e}")

if __name__ == "__main__":
    diagnose()
