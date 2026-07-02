"""
MT5Service — wraps the MetaTrader5 Python package.

All MT5 interactions are centralised here so the rest of the codebase
never imports MetaTrader5 directly. This makes it easy to mock for testing.

## Connection Model (IMPORTANT)
MT5 Python maintains a SINGLE global connection per process.
mt5.initialize() and mt5.shutdown() are process-wide global switches —
calling shutdown() anywhere kills MT5 for ALL threads.

Therefore MT5Service is implemented as a Singleton:
  - Connected ONCE when the app starts (called from live_data/market_data.py)
  - Shared across: broadcaster loop, sync worker, manual sync route
  - NEVER shut down mid-operation; only shut down when the server exits
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Any

log = logging.getLogger(__name__)

# Guard import: MetaTrader5 is Windows-only and requires the terminal running.
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore
    MT5_AVAILABLE = False
    log.warning("MetaTrader5 package not available — running in stub mode.")


class MT5Service:
    """
    Singleton-pattern wrapper for MetaTrader 5.

    Because MT5's Python API maintains ONE global connection per process,
    this class tracks a single _initialized flag. All callers share
    the same underlying connection.

    Correct usage:
        svc = MT5Service()
        svc.ensure_connected()   # no-op if already connected
        deals = svc.fetch_history()
        # Do NOT call svc.disconnect() inside request handlers or workers.
        # Only call disconnect() on server shutdown.
    """

    # ── Singleton connection state (class-level, shared across all instances) ─
    _initialized: bool = False

    def __init__(self, path: str = None, login: int = None, password: str = None, server: str = None) -> None:
        from config import Config
        self._path     = path
        self._login    = login if login is not None else Config.MT5_LOGIN
        self._password = password if password is not None else Config.MT5_PASSWORD
        self._server   = server if server is not None else Config.MT5_SERVER

    # ── Connection ─────────────────────────────────────────────────────────

    def connect(self) -> None:
        """
        Initialize the global MT5 connection.
        Idempotent — safe to call multiple times; only connects once.
        """
        if not MT5_AVAILABLE:
            log.warning("MT5 not available — skipping connect.")
            return

        if MT5Service._initialized:
            log.debug("MT5 already connected — skipping re-initialize.")
            return

        kwargs = {
            "login": self._login,
            "password": self._password,
            "server": self._server,
        }
        if self._path:
            kwargs["path"] = self._path
            
        ok = mt5.initialize(**kwargs)
        if not ok:
            error = mt5.last_error()
            raise ConnectionError(f"MT5 initialisation failed: {error}")

        MT5Service._initialized = True
        log.info("MT5 connected — account %s on %s", self._login, self._server)

    def ensure_connected(self) -> None:
        """
        Ensure the global MT5 connection is live.
        Attempts to reconnect if the connection has been lost.
        Use this instead of connect() in workers and routes.
        """
        if not MT5_AVAILABLE:
            return

        # Check if the terminal is still responsive
        if not MT5Service._initialized or mt5.terminal_info() is None:
            log.warning("MT5 connection lost — reconnecting...")
            MT5Service._initialized = False
            self.connect()

    def is_connected(self) -> bool:
        """Return True if MT5 is currently connected and responsive."""
        if not MT5_AVAILABLE:
            return False
        return MT5Service._initialized and mt5.terminal_info() is not None

    def disconnect(self) -> None:
        """
        Shut down the global MT5 connection.

        WARNING: This is a GLOBAL shutdown — affects all threads.
        Only call this on full server shutdown, NOT inside request handlers
        or background workers, or it will kill the live tick broadcaster.
        """
        if MT5_AVAILABLE and mt5 and MT5Service._initialized:
            mt5.shutdown()
            MT5Service._initialized = False
            log.info("MT5 disconnected (global shutdown).")

    # ── Trade History ──────────────────────────────────────────────────────

    def fetch_history(
        self,
        days_back: int = 365,
    ) -> List[Any]:
        """
        Fetch closed deals from MT5 history.

        Args:
            days_back: How many days back to look. Default = 1 year.

        Returns:
            List of MT5 deal objects (or empty list on error / stub mode).
        """
        if not MT5_AVAILABLE:
            log.warning("MT5 not available — returning empty history.")
            return []

        self.ensure_connected()

        from_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        # MT5 expects broker time. Since we are using UTC, we add 1 day to to_date
        # to ensure we don't accidentally cut off recent deals if the broker is ahead of UTC.
        to_date   = datetime.now(timezone.utc) + timedelta(days=1)

        deals = mt5.history_deals_get(from_date, to_date)
        if deals is None:
            log.error("MT5 history_deals_get returned None: %s", mt5.last_error())
            return []

        log.info("Fetched %d closed deals from MT5 history.", len(deals))
        return list(deals)

    def fetch_open_positions(self) -> List[Any]:
        """
        Fetch currently open positions from MT5.

        Returns:
            List of MT5 position objects (or empty list).
        """
        if not MT5_AVAILABLE:
            return []

        self.ensure_connected()

        positions = mt5.positions_get()
        if positions is None:
            return []

        log.info("Fetched %d open positions from MT5.", len(positions))
        return list(positions)

    # ── Live Market Data ───────────────────────────────────────────────────

    def get_tick(self, symbol: str) -> dict | None:
        """
        Return the latest bid/ask tick for a symbol.
        Calls symbol_select() first to ensure the symbol is active in Market Watch.
        Returns a dict with keys: symbol, bid, ask, time.
        Returns None if MT5 is unavailable or the symbol is invalid.

        Prices are rounded using the broker-defined `digits` field from
        mt5.symbol_info(), which gives the exact decimal precision for that
        specific symbol on that specific broker. Examples:
          - EURUSD  → digits=5  → 1.14003
          - USDJPY  → digits=3  → 162.352
          - XAUUSD  → digits=2  → 1923.45
          - US30    → digits=1  → 34521.5
          - BTCUSD  → digits=2  → 45000.12
        """
        if not MT5_AVAILABLE:
            return None

        self.ensure_connected()

        # Enable the symbol in Market Watch so ticks are available
        mt5.symbol_select(symbol, True)

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            log.debug("No tick data for symbol '%s' — may not exist on this broker.", symbol)
            return None

        # Read decimal precision directly from the broker — works for ALL
        # instrument types: FX, metals, indices, crypto, energies, etc.
        info = mt5.symbol_info(symbol)
        decimals = info.digits if info else 5   # fallback to 5dp if unavailable

        return {
            "symbol":   symbol,
            "bid":      round(tick.bid, decimals),
            "ask":      round(tick.ask, decimals),
            "time":     tick.time,
            "decimals": decimals,   # expose so clients know display precision
        }

    # ── Trade Execution ────────────────────────────────────────────────────

    def execute_trade(self, symbol: str, trade_type: str, volume: float, deviation: int = 20, sl: float = 0.0, tp: float = 0.0) -> int | None:
        """
        Execute a market order on the currently connected MT5 terminal.
        trade_type must be "BUY" or "SELL".
        Returns the ticket number of the new position, or None on failure.
        """
        if not MT5_AVAILABLE:
            log.error("MT5 not available — cannot execute trade.")
            return None

        self.ensure_connected()

        # Ensure symbol is visible in market watch
        mt5.symbol_select(symbol, True)
        
        info = mt5.symbol_info(symbol)
        if info is None:
            log.error(f"Symbol {symbol} not found.")
            return None

        if not info.visible:
            log.error(f"Symbol {symbol} is not visible.")
            return None

        # Determine price and order type
        if trade_type.upper() == "BUY":
            order_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(symbol).ask
        elif trade_type.upper() == "SELL":
            order_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(symbol).bid
        else:
            log.error(f"Invalid trade_type: {trade_type}")
            return None

        # Auto-detect the correct filling mode supported by this broker/symbol.
        # filling_mode is a bitmask: bit0=FOK(1), bit1=IOC(2), bit2=RETURN(4).
        # Not all brokers support IOC — demo servers often only support FOK or RETURN.
        filling_mode_map = {
            1: mt5.ORDER_FILLING_FOK,
            2: mt5.ORDER_FILLING_IOC,
            4: mt5.ORDER_FILLING_RETURN,
        }
        filling_type = mt5.ORDER_FILLING_FOK  # default fallback
        for bit, mode in filling_mode_map.items():
            if info.filling_mode & bit:
                filling_type = mode
                break
        log.debug(f"Using filling mode {filling_type} for {symbol} (broker filling_mode={info.filling_mode})")

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": price,
            "deviation": deviation,
            "magic": 123456,  # Magic number for copied trades
            "comment": "TradePulse Copier",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_type,
        }
        
        if sl > 0.0:
            request["sl"] = float(sl)
        if tp > 0.0:
            request["tp"] = float(tp)

        # Send order
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            log.error(f"Order send failed, retcode={result.retcode}: {result.comment}")
            return None
            
        log.info(f"Trade executed successfully: Ticket {result.order} | {trade_type} {volume} {symbol}")
        return result.order

    def close_position(self, ticket: int, deviation: int = 20, volume: float = None) -> bool:
        """
        Close an open position identified by its ticket number.
        If volume is provided, partially closes that volume. Otherwise closes entire position.
        Returns True on success, False on failure.
        """
        if not MT5_AVAILABLE:
            log.error("MT5 not available — cannot close position.")
            return False

        self.ensure_connected()

        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            log.warning(f"Position {ticket} not found — may already be closed.")
            return True

        pos = positions[0]
        symbol = pos.symbol
        mt5.symbol_select(symbol, True)

        info = mt5.symbol_info(symbol)
        if info is None:
            log.error(f"Symbol {symbol} not found for closing ticket {ticket}.")
            return False

        # Opposite order type to close
        if pos.type == mt5.POSITION_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(symbol).bid
        else:
            close_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(symbol).ask

        # Auto-detect filling mode
        filling_mode_map = {1: mt5.ORDER_FILLING_FOK, 2: mt5.ORDER_FILLING_IOC, 4: mt5.ORDER_FILLING_RETURN}
        filling_type = mt5.ORDER_FILLING_FOK
        for bit, mode in filling_mode_map.items():
            if info.filling_mode & bit:
                filling_type = mode
                break

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       symbol,
            "volume":       float(volume) if volume is not None else pos.volume,
            "type":         close_type,
            "position":     ticket,   # Required to close a specific position
            "price":        price,
            "deviation":    deviation,
            "magic":        123456,
            "comment":      "TradePulse Copier Close",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": filling_type,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            log.error(f"Close position failed, retcode={result.retcode}: {result.comment}")
            return False

        log.info(f"Position {ticket} closed successfully ({symbol} {pos.volume} lots).")
        return True

    def modify_position(self, ticket: int, sl: float, tp: float) -> bool:
        """
        Modify Stop Loss and Take Profit for an existing position.
        """
        if not MT5_AVAILABLE:
            log.error("MT5 not available — cannot modify position.")
            return False

        self.ensure_connected()

        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            log.warning(f"Position {ticket} not found — cannot modify.")
            return False

        pos = positions[0]
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": ticket,
            "sl": float(sl),
            "tp": float(tp),
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            log.error(f"Modify position failed, retcode={result.retcode}: {result.comment}")
            return False

        log.info(f"Position {ticket} modified successfully (SL={sl}, TP={tp}).")
        return True

    # ── Utilities ──────────────────────────────────────────────────────────

    @staticmethod
    def ts_to_datetime(timestamp: int) -> datetime:
        """Convert a Unix timestamp (MT5 time field) to a UTC datetime."""
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
