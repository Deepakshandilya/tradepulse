"""
SocketIO Event Handlers

Client → Server events:
  connect            — logged on connection
  disconnect         — logged on disconnect
  subscribe          — client subscribes to live data for a list of symbols
  unsubscribe        — client unsubscribes from specific symbols

The `subscribed_symbols` set is shared with `live_data/market_data.py`
so the broadcaster knows what to stream.
"""

import logging
from flask_socketio import emit
from app import socketio
from live_data.market_data import subscribed_symbols

log = logging.getLogger(__name__)


@socketio.on("connect")
def handle_connect():
    log.info("WebSocket client connected.")
    emit("connected", {"message": "Connected to TradePulse live feed."})


@socketio.on("disconnect")
def handle_disconnect():
    log.info("WebSocket client disconnected.")


@socketio.on("subscribe")
def handle_subscribe(data: dict):
    """
    Subscribe to live market data for specified symbols.

    Expected payload:
        { "symbols": ["EURUSD", "GBPUSD", "XAUUSD"] }

    Server response (ack):
        { "subscribed": ["EURUSD", "GBPUSD", "XAUUSD"] }
    """
    symbols = data.get("symbols", [])
    if not isinstance(symbols, list):
        emit("error", {"message": "'symbols' must be a list of strings."})
        return

    added = []
    for symbol in symbols:
        symbol = str(symbol).strip().upper()
        if symbol:
            subscribed_symbols.add(symbol)
            added.append(symbol)

    log.info("Client subscribed to: %s", added)
    emit("subscribed", {"subscribed": added, "all_active": list(subscribed_symbols)})


@socketio.on("unsubscribe")
def handle_unsubscribe(data: dict):
    """
    Unsubscribe from live data for specified symbols.

    Expected payload:
        { "symbols": ["EURUSD"] }
    """
    symbols = data.get("symbols", [])
    removed = []
    for symbol in symbols:
        symbol = str(symbol).strip().upper()
        if symbol in subscribed_symbols:
            subscribed_symbols.discard(symbol)
            removed.append(symbol)

    log.info("Client unsubscribed from: %s", removed)
    emit("unsubscribed", {"removed": removed, "all_active": list(subscribed_symbols)})
