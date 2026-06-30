"""
Copier Master Worker — TradePulse

Connects to the Master MT5 terminal.
Polls every 500ms for:
  - New positions  -> publishes OPEN signal to Redis
  - Closed positions -> publishes CLOSE signal to Redis
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time
import json
import logging
import redis
from config import Config

# ── Colored Logging ────────────────────────────────────────────────────────────
class CopierFormatter(logging.Formatter):
    CYAN    = "\033[36m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    RED     = "\033[31m"
    MAGENTA = "\033[35m"
    RESET   = "\033[0m"
    DIM     = "\033[2m"

    LEVEL_COLORS = {
        logging.DEBUG:    "\033[2m",
        logging.INFO:     "\033[32m",
        logging.WARNING:  "\033[33m",
        logging.ERROR:    "\033[31m",
        logging.CRITICAL: "\033[35m",
    }

    def format(self, record):
        color    = self.LEVEL_COLORS.get(record.levelno, self.RESET)
        time_str = f"{self.DIM}{self.formatTime(record, '%H:%M:%S')}{self.RESET}"
        tag      = f"{self.MAGENTA}[MASTER]{self.RESET}"
        name     = f"{self.CYAN}{record.name}{self.RESET}"
        msg      = f"{color}{record.getMessage()}{self.RESET}"
        return f"{time_str} {tag} {name}: {msg}"

_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(CopierFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler])
log = logging.getLogger("copier_master")

# ── MT5 Import ────────────────────────────────────────────────────────────────
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False


def run_master(terminal_path: str, master_account_id: int):
    if not MT5_AVAILABLE:
        log.error("MT5 package not available. Exiting.")
        return

    log.info(f"Connecting to Master Terminal: {terminal_path}")
    if not mt5.initialize(path=terminal_path):
        log.error(f"initialize() failed: {mt5.last_error()}")
        return

    info = mt5.account_info()
    if info:
        log.info(f"Connected to Master account: {info.login} on {info.server}")

    try:
        r = redis.from_url(Config.REDIS_URL)
        r.ping()
        log.info("Connected to Redis.")
    except Exception as e:
        log.error(f"Redis connection failed: {e}")
        return

    log.info(f"Monitoring Master account ID={master_account_id} — polling every 500ms")

    # Snapshot: ticket -> position namedtuple
    known_positions = {}

    # Initial snapshot — don't publish signals for already-open trades on startup
    positions = mt5.positions_get()
    if positions:
        for p in positions:
            known_positions[p.ticket] = p
    log.info(f"Initial snapshot: {len(known_positions)} open position(s) (will not be copied).")

    while True:
        try:
            positions = mt5.positions_get()
            current_positions = {}
            if positions:
                for p in positions:
                    current_positions[p.ticket] = p

            # ── Detect NEW positions (OPEN signal) ──────────────────────────
            new_tickets = set(current_positions.keys()) - set(known_positions.keys())
            for ticket in new_tickets:
                p = current_positions[ticket]
                if p.type in (0, 1):  # 0=BUY, 1=SELL only
                    trade_type = "BUY" if p.type == 0 else "SELL"
                    msg = {
                        "action":            "OPEN",
                        "master_account_id": master_account_id,
                        "ticket":            p.ticket,
                        "symbol":            p.symbol,
                        "trade_type":        trade_type,
                        "volume":            p.volume,
                        "price_open":        p.price_open,
                    }
                    r.publish("trade_signals", json.dumps(msg))
                    log.info(f">> OPEN  {trade_type:4s} {p.symbol:10s} vol={p.volume} ticket={ticket}")

            # ── Detect CLOSED positions (CLOSE signal) ──────────────────────
            closed_tickets = set(known_positions.keys()) - set(current_positions.keys())
            for ticket in closed_tickets:
                p = known_positions[ticket]
                msg = {
                    "action":            "CLOSE",
                    "master_account_id": master_account_id,
                    "ticket":            ticket,
                    "symbol":            p.symbol,
                }
                r.publish("trade_signals", json.dumps(msg))
                log.info(f"<< CLOSE {p.symbol:10s} ticket={ticket}")

            known_positions = current_positions
            time.sleep(0.5)

        except Exception as e:
            log.error(f"Error in master loop: {e}")
            time.sleep(1)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python copier_master.py <terminal_path> <master_account_id>")
        sys.exit(1)
    run_master(sys.argv[1], int(sys.argv[2]))
