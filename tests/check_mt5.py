"""
TradePulse -- MT5 Quick Diagnostic
Run this to check what MT5 can see without starting Flask.
Usage:  python check_mt5.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()
import os

LOGIN    = int(os.getenv("MT5_LOGIN", "0"))
PASSWORD = os.getenv("MT5_PASSWORD", "")
SERVER   = os.getenv("MT5_SERVER", "")

print(f"\n[>>] Connecting to MT5: login={LOGIN}  server={SERVER}")

try:
    import MetaTrader5 as mt5
except ImportError:
    print("[ERR] MetaTrader5 package not installed or numpy incompatible.")
    sys.exit(1)

# ── Connect ────────────────────────────────────────────────────────────────
ok = mt5.initialize(login=LOGIN, password=PASSWORD, server=SERVER)
if not ok:
    print(f"[ERR] MT5 connect failed: {mt5.last_error()}")
    sys.exit(1)

info = mt5.account_info()
print(f"[OK]  Connected!  Balance={info.balance}  Equity={info.equity}  Server={info.server}")

# ── Open Positions ─────────────────────────────────────────────────────────
print("\n--- OPEN POSITIONS (positions_get) ---")
positions = mt5.positions_get()
if positions:
    for p in positions:
        print(f"  ticket={p.ticket}  {p.symbol}  {'BUY' if p.type==0 else 'SELL'}  vol={p.volume}  profit={p.profit}")
else:
    print("  No open positions.")

# ── Closed Deal History ────────────────────────────────────────────────────
from datetime import datetime, timezone, timedelta
print("\n--- DEAL HISTORY (last 7 days) ---")
from_date = datetime.now(timezone.utc) - timedelta(days=7)
to_date   = datetime.now(timezone.utc)
deals = mt5.history_deals_get(from_date, to_date)
if deals:
    for d in deals:
        print(f"  ticket={d.ticket}  {d.symbol}  type={d.type}  vol={d.volume}  profit={d.profit}")
else:
    print(f"  No closed deals in last 7 days.  (MT5 error: {mt5.last_error()})")

# ── Live Ticks ─────────────────────────────────────────────────────────────
print("\n--- LIVE TICKS ---")
for symbol in ["EURUSD", "GBPUSD", "XAUUSD"]:
    mt5.symbol_select(symbol, True)
    tick = mt5.symbol_info_tick(symbol)
    if tick:
        print(f"  {symbol:<10} bid={tick.bid:.5f}  ask={tick.ask:.5f}")
    else:
        print(f"  {symbol:<10} NO TICK DATA (symbol may not be on this broker)")

mt5.shutdown()
print("\n[OK]  MT5 diagnostic complete.\n")
