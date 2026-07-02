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
from app import create_app, db
from utils.encryption import decrypt_password

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

    # Initialize Flask app to access DB
    flask_app = create_app(start_workers=False)
    
    with flask_app.app_context():
        from models.broker_account import BrokerAccount
        # Use session.get() instead of query.get() to avoid legacy warnings if preferred, or just stick to query.get
        master_account = db.session.get(BrokerAccount, master_account_id)
        if not master_account:
            log.error(f"Master account {master_account_id} not found in DB.")
            return
            
        login = master_account.login
        password = decrypt_password(master_account.password_encrypted)
        server = master_account.server

    if not login or not password or not server:
        log.error("Master account is missing explicit credentials (login, password, server).")
        return

    log.info(f"Connecting to Master Terminal: {terminal_path} for account {login}")
    if not mt5.initialize(
        path=terminal_path,
        login=login,
        password=password,
        server=server,
        timeout=10000
    ):
        log.error(f"initialize() failed: {mt5.last_error()}")
        return

    info = mt5.account_info()
    if info is None or info.login != login:
        log.error(f"Wrong account logged in! Expected {login}, got {info.login if info else None}")
        return

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
                        "sl":                getattr(p, 'sl', 0.0),
                        "tp":                getattr(p, 'tp', 0.0),
                    }
                    # Redis Streams XADD
                    r.xadd("trade_stream", {"action": msg["action"], "payload": json.dumps(msg)})
                    log.info(f">> OPEN  {trade_type:4s} {p.symbol:10s} vol={p.volume} ticket={ticket} sl={msg['sl']} tp={msg['tp']}")

            # ── Detect MODIFIED positions (SL/TP changes or Partial Close) ──
            common_tickets = set(current_positions.keys()).intersection(set(known_positions.keys()))
            for ticket in common_tickets:
                curr_p = current_positions[ticket]
                old_p = known_positions[ticket]

                # Check for volume reduction (Partial Close)
                if curr_p.volume < old_p.volume:
                    closed_volume = round(old_p.volume - curr_p.volume, 2)
                    msg = {
                        "action":            "PARTIAL_CLOSE",
                        "master_account_id": master_account_id,
                        "ticket":            ticket,
                        "symbol":            curr_p.symbol,
                        "close_volume":      closed_volume
                    }
                    r.xadd("trade_stream", {"action": msg["action"], "payload": json.dumps(msg)})
                    log.info(f"<< PARTIAL CLOSE {curr_p.symbol:10s} ticket={ticket} vol_closed={closed_volume}")

                # Check for SL/TP modifications
                curr_sl = getattr(curr_p, 'sl', 0.0)
                curr_tp = getattr(curr_p, 'tp', 0.0)
                old_sl = getattr(old_p, 'sl', 0.0)
                old_tp = getattr(old_p, 'tp', 0.0)

                if curr_sl != old_sl or curr_tp != old_tp:
                    msg = {
                        "action":            "MODIFY",
                        "master_account_id": master_account_id,
                        "ticket":            ticket,
                        "symbol":            curr_p.symbol,
                        "sl":                curr_sl,
                        "tp":                curr_tp
                    }
                    r.xadd("trade_stream", {"action": msg["action"], "payload": json.dumps(msg)})
                    log.info(f"~~ MODIFY {curr_p.symbol:10s} ticket={ticket} new_sl={curr_sl} new_tp={curr_tp}")

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
                # Redis Streams XADD
                r.xadd("trade_stream", {"action": msg["action"], "payload": json.dumps(msg)})
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
