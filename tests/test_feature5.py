"""
Feature 5 — Background Auto-Sync Worker (APScheduler)
Tests:
  1. Verify the scheduler is running by checking the server is alive
  2. Record current trade count in DB
  3. Prompt user to place a trade in MT5
  4. Wait 70 seconds (one full sync cycle + buffer)
  5. Check if new trade appeared automatically in DB (no manual sync triggered)

HOW TO USE:
  1. Run this script
  2. When prompted, go to MT5 and place a small trade (any pair, 0.01 lots)
  3. Wait — the script will automatically check after 70 seconds
"""

import requests
import time

BASE = "http://localhost:5000/api"
ACCOUNT_ID = 1
WAIT_SECONDS = 70   # sync runs every 60s; we wait 70 to be safe

print("=" * 55)
print("FEATURE 5 — Background Auto-Sync Worker")
print("=" * 55)

# ── Step 1: Get current trade count ─────────────────────
r = requests.get(f"{BASE}/trades/{ACCOUNT_ID}")
initial_trades = r.json().get("trades", [])
initial_count  = len(initial_trades)
initial_tickets = {t["ticket"] for t in initial_trades}

print(f"\n[1] Current trades in DB: {initial_count}")

# ── Step 2: Prompt user ──────────────────────────────────
print("\n[2] ACTION REQUIRED:")
print("    Open MetaTrader 5 and place a REAL trade right now.")
print("    Suggested: any pair, 0.01 lots (minimum size)")
print("    Do NOT use the /sync API — let the background worker pick it up.")
print()
input("    Press ENTER when you have placed the trade in MT5...")

print(f"\n[3] Waiting {WAIT_SECONDS} seconds for background worker to run...")
print("    (APScheduler runs every 60s — watch your server terminal for the sync log)")

# countdown
for remaining in range(WAIT_SECONDS, 0, -5):
    print(f"    {remaining}s remaining...", end="\r")
    time.sleep(5)

print("\n    Time's up — checking DB now...")

# ── Step 3: Check for new trades ─────────────────────────
r = requests.get(f"{BASE}/trades/{ACCOUNT_ID}")
new_trades = r.json().get("trades", [])
new_count  = len(new_trades)
new_tickets = {t["ticket"] for t in new_trades}

added_tickets = new_tickets - initial_tickets
added_count   = new_count - initial_count

print(f"\n[4] Results:")
print(f"    Trades before : {initial_count}")
print(f"    Trades after  : {new_count}")
print(f"    New trades    : {added_count}")

if added_count > 0:
    print(f"\n    ✅ Background sync is working!")
    print(f"    New tickets found:")
    for t in new_trades:
        if t["ticket"] in added_tickets:
            print(f"      ticket={t['ticket']}  sym={t['symbol']}  "
                  f"type={t['trade_type']}  vol={t['volume']}")
else:
    print("\n    ❌ No new trades appeared automatically.")
    print("    Possible reasons:")
    print("      - Trade was placed BEFORE the last sync cycle ran")
    print("      - Sync worker had an error (check server terminal logs)")
    print("      - The placed trade is still open and needs a closed deal")
    print("    Try: python tests/test_feature3.py to manually sync and check")
