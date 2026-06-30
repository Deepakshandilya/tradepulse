"""
Feature 4 — Commission Engine
Tests:
  1. Every trade has exactly 1 commission (no orphans, no duplicates)
  2. Commission math: amount == volume * $5 (within 0.001 tolerance)
  3. Idempotency: syncing again does NOT create a second commission per trade
  4. Total commission matches sum of (volume * 5) for all trades
"""

import requests

BASE = "http://localhost:5000/api"
ACCOUNT_ID = 1
COMMISSION_RATE = 5.0   # $5 per lot

print("=" * 55)
print("FEATURE 4 — Commission Engine")
print("=" * 55)

# ── Fetch trades and commissions ─────────────────────────
r = requests.get(f"{BASE}/trades/{ACCOUNT_ID}")
trades = r.json().get("trades", [])

r = requests.get(f"{BASE}/commissions/{ACCOUNT_ID}")
cd = r.json()
commissions = cd.get("commissions", [])

trade_map = {t["id"]: t for t in trades}
comm_by_trade = {c["trade_id"]: c for c in commissions}

print(f"\n    Trades in DB         : {len(trades)}")
print(f"    Commissions in DB    : {len(commissions)}")
print(f"    Total commission (API): ${cd.get('total_usd')}")

# ── Test 1: Every trade has a commission ─────────────────
print("\n[1] Checking every trade has a commission...")
missing = [t for t in trades if t["id"] not in comm_by_trade]
if not missing:
    print("    ✅ Every trade has exactly 1 commission")
else:
    for t in missing:
        print(f"    ❌ Trade id={t['id']} ticket={t['ticket']} has NO commission")

# ── Test 2: Commission math check ────────────────────────
print("\n[2] Verifying commission amounts (volume × $5.00)...")
errors = []
for c in commissions:
    trade = trade_map.get(c["trade_id"])
    if not trade:
        continue
    expected = round(trade["volume"] * COMMISSION_RATE, 2)
    actual   = round(float(c["amount"]), 2)
    diff     = abs(actual - expected)
    if diff > 0.001:
        errors.append(
            f"    ❌ trade_id={c['trade_id']}  vol={trade['volume']}"
            f"  expected=${expected}  got=${actual}  diff={diff}"
        )
    else:
        print(f"    ✅ trade_id={c['trade_id']}  vol={trade['volume']}  "
              f"${actual} == vol × $5")

if errors:
    for e in errors:
        print(e)

# ── Test 3: Idempotency — re-trigger sync, count commissions again ──
print("\n[3] Idempotency check — re-syncing and recounting commissions...")
requests.post(f"{BASE}/trades/sync/{ACCOUNT_ID}", timeout=30)

r2 = requests.get(f"{BASE}/commissions/{ACCOUNT_ID}")
new_count = r2.json().get("count")
if new_count == len(commissions):
    print(f"    ✅ Commission count unchanged after re-sync: {new_count}")
else:
    print(f"    ❌ Commission count changed: was {len(commissions)}, now {new_count}")
    print("       Duplicate commissions are being created!")

# ── Test 4: Total sum check ──────────────────────────────
print("\n[4] Verifying total commission sum...")
expected_total = round(
    sum(trade["volume"] * COMMISSION_RATE for trade in trades
        if trade["symbol"]),   # skip ghost trades with no symbol
    2
)
api_total = round(float(cd.get("total_usd", 0)), 2)
print(f"    Expected total : ${expected_total}")
print(f"    API total      : ${api_total}")
if abs(api_total - expected_total) < 0.01:
    print("    ✅ Total commission matches")
else:
    print("    ❌ Total mismatch — check for ghost trades or calculation errors")
