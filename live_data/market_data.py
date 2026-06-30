"""
Market Data Broadcaster

Runs a SocketIO background thread that broadcasts live bid/ask prices
for all subscribed symbols every second.

The `subscribed_symbols` set is the shared state between:
  - sockets/events.py   (subscribe / unsubscribe handlers write to it)
  - this module         (the broadcaster reads from it)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask_socketio import SocketIO

log = logging.getLogger(__name__)

# Shared mutable set of active symbol subscriptions.
# Thread-safe for simple add/discard operations under GIL.
subscribed_symbols: set[str] = set()

_broadcast_started = False   # Guard against starting the loop twice


def _broadcast_loop(socketio: "SocketIO") -> None:
    """
    Infinite loop (runs as a SocketIO background task):
    - Connects to MT5 once at startup.
    - Every second, fetches a live tick for each subscribed symbol.
    - Emits a 'market_data' event to all connected clients.
    """
    from services.mt5_service import MT5Service
    mt5 = MT5Service()

    # Connect once — shared global connection for the entire process lifetime
    try:
        mt5.connect()
        log.info("MT5 connected for market data broadcast.")
    except Exception as exc:
        log.warning("MT5 initial connect failed in broadcast loop: %s — will retry each tick.", exc)

    log.info("Market data broadcast loop started.")

    while True:
        for symbol in list(subscribed_symbols):
            try:
                # ensure_connected() auto-reconnects if MT5 dropped silently
                tick = mt5.get_tick(symbol)
                if tick:
                    socketio.emit("market_data", tick)
            except Exception as exc:
                log.warning("Error fetching tick for %s: %s", symbol, exc)

        socketio.sleep(1)   # Must be socketio.sleep — not time.sleep!


def start_market_broadcast(socketio: "SocketIO") -> None:
    """
    Start the market data broadcast background thread.
    Called once from the app factory. Subsequent calls are no-ops.
    """
    global _broadcast_started

    if _broadcast_started:
        log.debug("Market broadcast already running — skipping.")
        return

    socketio.start_background_task(_broadcast_loop, socketio)
    _broadcast_started = True
    log.info("Market data background task registered.")
