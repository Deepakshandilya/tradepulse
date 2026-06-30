"""
Feature 6 — Real-time WebSocket Trade Broadcasts
Tests:
  1. Connect to WebSocket and listen for 'commission_created' events
  2. Trigger a manual sync which inserts new trades and fires the event
  3. Verify the event payload has the correct fields

The pipeline being tested:
  MT5 history → DB insert → commission_engine → WebSocket emit → client receives

HOW TO USE:
  1. Make sure the server is running (python run.py)
  2. Run this script — it will connect via WebSocket and wait
  3. In a SEPARATE terminal, trigger a sync:
       python tests/test_feature3.py
     OR manually:
       curl -X POST http://localhost:5000/api/trades/sync/1
  4. Watch this script receive the real-time commission_created event
"""

import socketio
import time
import threading
import requests

BASE_HTTP = "http://localhost:5000/api"
ACCOUNT_ID = 1

sio = socketio.Client(logger=False, engineio_logger=False)

events_received = []

@sio.event
def connect():
    print("\n✅ [WS] Connected to TradePulse!")
    print("   Listening for: commission_created, market_data\n")

@sio.event
def commission_created(data):
    events_received.append(data)
    print(f"🎯 [WS EVENT] commission_created received!")
    print(f"   trade_id  : {data.get('trade_id')}")
    print(f"   ticket    : {data.get('ticket')}")
    print(f"   symbol    : {data.get('symbol')}")
    print(f"   volume    : {data.get('volume')} lots")
    print(f"   commission: ${data.get('amount_usd')}")
    print()

    # Validate payload has required fields
    required = ["trade_id", "ticket", "symbol", "volume", "amount_usd"]
    missing = [k for k in required if k not in data]
    if not missing:
        print("   ✅ Payload has all required fields")
    else:
        print(f"   ❌ Missing fields: {missing}")

@sio.event
def market_data(data):
    # Print first few ticks to confirm WS is alive, then go quiet
    if len([e for e in events_received if "bid" in str(e)]) < 3:
        print(f"📈 [TICK] {data.get('symbol')}  bid={data.get('bid')}  ask={data.get('ask')}")
    events_received.append({"type": "tick", **data})

@sio.event
def disconnect():
    print("\n❌ [WS] Disconnected")


def trigger_sync_after_delay(delay: int = 5):
    """Triggers a manual sync after `delay` seconds — in a background thread."""
    time.sleep(delay)
    print(f"\n🔄 [HTTP] Triggering manual sync now (to fire commission_created events)...")
    r = requests.post(f"{BASE_HTTP}/trades/sync/{ACCOUNT_ID}", timeout=30)
    d = r.json()
    print(f"   Sync result: inserted={d.get('inserted')} skipped={d.get('skipped')} filtered={d.get('filtered')}")
    if d.get("inserted", 0) == 0:
        print("   ℹ️  No NEW trades inserted — commission_created won't fire for existing trades.")
        print("   ℹ️  Place a new trade in MT5 first, then re-run this test.")
    else:
        print(f"   {d['inserted']} new trade(s) inserted — watch for commission_created events above!")


if __name__ == "__main__":
    print("=" * 55)
    print("FEATURE 6 — Real-time WebSocket Trade Broadcasts")
    print("=" * 55)
    print("\n⏳ Connecting to WebSocket...")

    sio.connect("http://localhost:5000")

    # Subscribe to live prices to confirm WS is alive
    sio.emit("subscribe", {"symbols": ["EURUSD"]})

    # Automatically trigger a sync after 5 seconds in background
    t = threading.Thread(target=trigger_sync_after_delay, args=(5,))
    t.daemon = True
    t.start()

    print("\nWaiting 30 seconds for events...")
    print("(Place a new trade in MT5 before running for best results)\n")

    try:
        time.sleep(30)
    except KeyboardInterrupt:
        pass

    print("\n" + "=" * 55)
    print("SUMMARY")
    print("=" * 55)
    commission_events = [e for e in events_received if "trade_id" in e]
    tick_events       = [e for e in events_received if e.get("type") == "tick"]

    print(f"commission_created events received : {len(commission_events)}")
    print(f"market_data (tick) events received : {len(tick_events)}")

    if commission_events:
        print("✅ Feature 6 PASSED — WebSocket trade broadcasts working")
    else:
        print("⚠️  No commission_created events in this run")
        print("   This is expected if no NEW trades were inserted (all already in DB)")
        print("   Place a trade in MT5, run test_feature3.py first to clear duplicates,")
        print("   then re-run this test.")

    sio.disconnect()
