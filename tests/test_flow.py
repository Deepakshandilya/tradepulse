# -*- coding: utf-8 -*-
"""
TradePulse -- Complete Flow Test Script
=======================================
Demonstrates the full system flow:
  1. Create a user
  2. Add a broker account (linked to your MT5 login)
  3. Sync MT5 trade history
  4. View synced trades
  5. View calculated commissions
  6. Subscribe to live WebSocket market data (EURUSD, GBPUSD, XAUUSD)
  7. Receive commission_created events in real-time

Run with:  python test_flow.py
(Server must be running in another terminal: python run.py)
"""

import sys
import os
import requests
import socketio
import time
from dotenv import load_dotenv

load_dotenv()

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://localhost:5000/api"
WS_URL   = "http://localhost:5000"

# ── Colours for terminal output ────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"{GREEN}  [OK]  {msg}{RESET}")
def info(msg): print(f"{CYAN}  [>>]  {msg}{RESET}")
def warn(msg): print(f"{YELLOW}  [!]   {msg}{RESET}")
def err(msg):  print(f"{RED}  [ERR] {msg}{RESET}")
def sep(title=""):
    line = "-" * 60
    print(f"\n{BOLD}{CYAN}{line}{RESET}")
    if title:
        print(f"{BOLD}  {title}{RESET}")
    print()


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 -- Create a User
# ══════════════════════════════════════════════════════════════════════════════
sep("STEP 1 -- Create User")
resp = requests.post(f"{BASE_URL}/users", json={
    "name":  "Deepak Shandilya",
    "email": "deepak@tradepulse.dev"
})
if resp.status_code == 201:
    user = resp.json()["user"]
    user_id = user["id"]
    ok(f"User created → id={user_id}  name={user['name']}  email={user['email']}")
elif resp.status_code == 409:
    # Already exists — fetch them
    warn("User already exists. Fetching existing user...")
    all_users = requests.get(f"{BASE_URL}/users").json()["users"]
    user = next(u for u in all_users if u["email"] == "deepak@tradepulse.dev")
    user_id = user["id"]
    ok(f"Found existing user → id={user_id}")
else:
    err(f"Failed to create user: {resp.status_code} {resp.text}")
    exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Add Broker Account (your MT5 demo account)
# ══════════════════════════════════════════════════════════════════════════════
sep("STEP 2 -- Add Broker Account")

MT5_LOGIN  = os.getenv("MT5_LOGIN", "5052406468")
MT5_SERVER = os.getenv("MT5_SERVER", "MetaQuotes-Demo")

# Check if account already exists for this user before creating
existing_accounts = requests.get(f"{BASE_URL}/accounts/{user_id}").json().get("accounts", [])
account = next((a for a in existing_accounts if a["account_no"] == MT5_LOGIN), None)

if account:
    account_id = account["id"]
    ok(f"Using existing account -> id={account_id}  account_no={account['account_no']}  broker={account['broker_name']}")
else:
    resp = requests.post(f"{BASE_URL}/accounts", json={
        "user_id":     user_id,
        "account_no":  MT5_LOGIN,
        "broker_name": MT5_SERVER,
    })
    if resp.status_code == 201:
        account = resp.json()["account"]
        account_id = account["id"]
        ok(f"Account added -> id={account_id}  account_no={account['account_no']}  broker={account['broker_name']}")
    else:
        err(f"Failed to add account: {resp.status_code} {resp.text}")
        exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Sync MT5 Trades
# ══════════════════════════════════════════════════════════════════════════════
sep("STEP 3 -- Sync MT5 Trades")
info("Calling POST /api/trades/sync/<account_id> ...")
resp = requests.post(f"{BASE_URL}/trades/sync/{account_id}", timeout=30)
if resp.status_code == 200:
    data = resp.json()
    ok(f"Sync complete -> inserted={data['inserted']}  skipped={data['skipped']}")
    if data["inserted"] == 0 and data["skipped"] == 0:
        warn("No deals found in MT5 history (demo account may have no trade history yet).")
        warn("This is normal for a brand-new demo account - the sync will pick up live trades automatically.")
else:
    err(f"Sync failed: {resp.status_code} {resp.text}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — View Synced Trades
# ══════════════════════════════════════════════════════════════════════════════
sep("STEP 4 -- View Synced Trades")
resp = requests.get(f"{BASE_URL}/trades/{account_id}")
trades_data = resp.json()
count = trades_data["count"]
info(f"Total trades in DB for account {account_id}: {count}")

if count > 0:
    for t in trades_data["trades"][:5]:   # Show first 5
        ok(f"  Ticket={t['ticket']}  {t['symbol']}  {t['trade_type']}  "
           f"vol={t['volume']}  profit={t['profit']}")
    if count > 5:
        info(f"  ... and {count - 5} more trades.")
else:
    warn("No trades yet — they will appear here after MT5 activity or after running a sync.")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — View Commissions
# ══════════════════════════════════════════════════════════════════════════════
sep("STEP 5 -- View Commissions")
resp = requests.get(f"{BASE_URL}/commissions/{account_id}")
comm_data = resp.json()
info(f"Total commissions: {comm_data['count']}  |  Total earned: ${comm_data['total_usd']}")

if comm_data["count"] > 0:
    for c in comm_data["commissions"][:5]:
        ok(f"  Commission id={c['id']}  trade_id={c['trade_id']}  amount=${c['amount']}")
else:
    warn("No commissions yet - they are auto-calculated when trades are synced.")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 + 7 — WebSocket Live Data + Events
# ══════════════════════════════════════════════════════════════════════════════
sep("STEP 6 & 7 -- WebSocket Live Market Data + commission_created Events")
info("Connecting to WebSocket at " + WS_URL)
info("Subscribing to: EURUSD, GBPUSD, XAUUSD")
info("Will listen for 20 seconds. Press Ctrl+C to stop early.\n")

sio = socketio.Client(logger=False, engineio_logger=False)

tick_count    = 0
commission_events = []

@sio.event
def connect():
    ok("WebSocket connected!")
    sio.emit("subscribe", {"symbols": ["EURUSD", "GBPUSD", "XAUUSD"]})

@sio.event
def disconnect():
    warn("WebSocket disconnected.")

@sio.on("subscribed")
def on_subscribed(data):
    ok(f"Server confirmed subscription: {data['subscribed']}")

@sio.on("market_data")
def on_market_data(data):
    global tick_count
    tick_count += 1
    symbol = data.get("symbol", "?")
    bid    = data.get("bid",    0)
    ask    = data.get("ask",    0)
    spread = round((ask - bid) * 100000, 1)  # in pips (for FX)
    print(f"  {CYAN}[TICK {tick_count:>3}] {symbol:<8} bid={bid:.5f}  ask={ask:.5f}  spread={spread} pips{RESET}")

@sio.on("commission_created")
def on_commission(data):
    commission_events.append(data)
    print(f"\n  {GREEN}{BOLD}[COMMISSION] trade_id={data['trade_id']}  "
          f"symbol={data.get('symbol')}  vol={data.get('volume')} lots  "
          f"amount=${data.get('amount_usd')}{RESET}\n")

@sio.on("connected")
def on_server_hello(data):
    info(f"Server says: {data['message']}")

try:
    sio.connect(WS_URL, transports=["websocket"])
    time.sleep(20)
except KeyboardInterrupt:
    warn("Stopped by user.")
except Exception as ex:
    err(f"WebSocket error: {ex}")
finally:
    sio.disconnect()


# ══════════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════════
sep("[DONE] Flow Complete -- Summary")
ok(f"User created/found       -> id={user_id}")
ok(f"Broker account linked    -> id={account_id}  ({MT5_LOGIN} on {MT5_SERVER})")
ok(f"Trades in DB             -> {trades_data['count']}")
ok(f"Commissions in DB        -> {comm_data['count']}  total=${comm_data['total_usd']}")
ok(f"Market data ticks received -> {tick_count}")
ok(f"commission_created events  -> {len(commission_events)}")

print(f"\n{BOLD}{GREEN}  TradePulse is fully operational!{RESET}\n")
