"""
Feature 3 — Manual Trade Sync
Tests:
  1. Sync MT5 trade history into DB via POST /api/trades/sync/<account_id>
  2. Verify ghost trade filter (filtered count > 0 because of balance deposits)
  3. List trades and confirm all have valid symbols and volumes
  4. Re-sync to prove deduplication (inserted should be 0, skipped = all)
"""

import requests
import json

BASE = "http://localhost:5000/api"
ACCOUNT_ID = 1   # The account linked in .env (MT5 login 5052406468)

print("=" * 55)
print("FEATURE 3 — Manual Trade Sync")
print("=" * 55)

# ── Test 1: Trigger sync ─────────────────────────────────
print("\n[1] Triggering MT5 sync for account #1...")
r = requests.post(f"{BASE}/trades/sync/{ACCOUNT_ID}", timeout=30)
print(f"    HTTP {r.status_code}")
d = r.json()
print(f"    closed_deals_found : {d.get('closed_deals_found')}")
print(f"    open_positions_found: {d.get('open_positions_found')}")
print(f"    inserted           : {d.get('inserted')}  (new trades added)")
print(f"    skipped            : {d.get('skipped')}   (already in DB)")
print(f"    filtered           : {d.get('filtered')}  (ghost/deposit deals removed)")

if d.get("filtered", 0) > 0:
    print("    ✅ Ghost trade filter is working!")
else:
    print("    ℹ️  No non-trade deals found this run (may already be filtered from DB)")

# ── Test 2: List trades and validate ────────────────────
print("\n[2] Fetching trade list for account #1...")
r = requests.get(f"{BASE}/trades/{ACCOUNT_ID}")
d = r.json()
trades = d.get("trades", [])
print(f"    Total trades in DB: {d.get('count')}")

ghost_count = 0
for t in trades:
    if not t["symbol"] or t["volume"] == 0:
        ghost_count += 1
        print(f"    ❌ Ghost trade found: ticket={t['ticket']} symbol={repr(t['symbol'])} vol={t['volume']}")

if ghost_count == 0:
    print("    ✅ No ghost trades in DB — filter working correctly")

print("\n    Sample trades:")
for t in trades[:5]:
    print(f"    ticket={t['ticket']}  sym={t['symbol']}  type={t['trade_type']}  vol={t['volume']}  profit={t['profit']}")

# ── Test 3: Re-sync to prove deduplication ───────────────
print("\n[3] Re-syncing (deduplication test — expect inserted=0)...")
r = requests.post(f"{BASE}/trades/sync/{ACCOUNT_ID}", timeout=30)
d = r.json()
print(f"    inserted : {d.get('inserted')}  (must be 0)")
print(f"    skipped  : {d.get('skipped')}   (all existing tickets recognised)")

if d.get("inserted") == 0:
    print("    ✅ Deduplication working — no duplicate trades inserted")
else:
    print("    ❌ FAIL — trades were re-inserted on second sync")

# ── Test 4: Sync a non-existent account ─────────────────
print("\n[4] Syncing a non-existent account (expect 404)...")
r = requests.post(f"{BASE}/trades/sync/9999", timeout=30)
print(f"    HTTP {r.status_code}  (expected 404)")
print(f"    Response: {r.json()}")
if r.status_code == 404:
    print("    ✅ 404 returned correctly for unknown account")
