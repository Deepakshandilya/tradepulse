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

    def __init__(self) -> None:
        from config import Config
        self._login    = Config.MT5_LOGIN
        self._password = Config.MT5_PASSWORD
        self._server   = Config.MT5_SERVER

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

        ok = mt5.initialize(
            login=self._login,
            password=self._password,
            server=self._server,
        )
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
        to_date   = datetime.now(timezone.utc)

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

    # ── Utilities ──────────────────────────────────────────────────────────

    @staticmethod
    def ts_to_datetime(timestamp: int) -> datetime:
        """Convert a Unix timestamp (MT5 time field) to a UTC datetime."""
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
