"""
MT5Service — wraps the MetaTrader5 Python package.

All MT5 interactions are centralised here so the rest of the codebase
never imports MetaTrader5 directly. This makes it easy to mock for testing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Any

log = logging.getLogger(__name__)

# Guard import: MetaTrader5 is Windows-only and requires the terminal running.
# On non-Windows CI environments this import will fail gracefully.
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore
    MT5_AVAILABLE = False
    log.warning("MetaTrader5 package not available — running in stub mode.")


class MT5Service:
    """
    Stateless helper for MetaTrader 5 operations.

    Usage pattern (always use connect / disconnect):
        svc = MT5Service()
        svc.connect()
        try:
            deals = svc.fetch_history()
        finally:
            svc.disconnect()
    """

    def __init__(self) -> None:
        from config import Config
        self._login    = Config.MT5_LOGIN
        self._password = Config.MT5_PASSWORD
        self._server   = Config.MT5_SERVER

    # ── Connection ─────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Initialise and login to the MT5 terminal."""
        if not MT5_AVAILABLE:
            log.warning("MT5 not available — skipping connect.")
            return

        ok = mt5.initialize(
            login=self._login,
            password=self._password,
            server=self._server,
        )
        if not ok:
            error = mt5.last_error()
            raise ConnectionError(f"MT5 initialisation failed: {error}")

        log.info("MT5 connected — account %s on %s", self._login, self._server)

    def disconnect(self) -> None:
        """Shut down the MT5 connection."""
        if MT5_AVAILABLE and mt5:
            mt5.shutdown()
            log.info("MT5 disconnected.")

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
        Useful for accounts with no closed trade history yet.

        Returns:
            List of MT5 position objects (or empty list).
        """
        if not MT5_AVAILABLE:
            return []

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
        """
        if not MT5_AVAILABLE:
            return None

        # Enable the symbol in Market Watch so ticks are available
        mt5.symbol_select(symbol, True)

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            log.debug("No tick data for symbol '%s' — may not exist on this broker.", symbol)
            return None

        return {
            "symbol": symbol,
            "bid":    tick.bid,
            "ask":    tick.ask,
            "time":   tick.time,
        }

    # ── Utilities ──────────────────────────────────────────────────────────

    @staticmethod
    def ts_to_datetime(timestamp: int) -> datetime:
        """Convert a Unix timestamp (MT5 time field) to a UTC datetime."""
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
