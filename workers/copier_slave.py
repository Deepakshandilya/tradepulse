"""
Copier Slave Worker — TradePulse

Connects to the Slave MT5 terminal.
Listens to Redis for OPEN and CLOSE signals and mirrors them.
Maintains a master_ticket -> slave_ticket mapping in memory.
After execution, writes trades directly to the TradePulse database
(using start_workers=False so APScheduler is NOT started here).
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
import logging
import redis
from datetime import datetime, timezone, timedelta

from config import Config
from services.mt5_service import MT5Service

# ── Colored Logging ─────────────────────────────────────────────────────────
class CopierFormatter(logging.Formatter):
    CYAN    = "\033[36m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    RED     = "\033[31m"
    BLUE    = "\033[34m"
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
        tag      = f"{self.BLUE}[SLAVE]{self.RESET}"
        name     = f"{self.CYAN}{record.name}{self.RESET}"
        msg      = f"{color}{record.getMessage()}{self.RESET}"
        return f"{time_str} {tag} {name}: {msg}"

_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(CopierFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler])
log = logging.getLogger("copier_slave")

# ── MT5 Import ────────────────────────────────────────────────────────────────
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False


# ── DB Helpers ────────────────────────────────────────────────────────────────

def _save_trade_to_db(app, slave_account_id: int, ticket: int, data: dict, copy_volume: float):
    """Write newly opened slave trade to DB immediately. Uses pre-built app."""
    try:
        from app import db, socketio as _socketio
        from models.trade import Trade
        from services.commission_engine import calculate_and_save

        with app.app_context():
            if Trade.query.filter_by(ticket=ticket).first():
                log.debug(f"Trade {ticket} already in DB — skipping.")
                return

            trade = Trade(
                account_id  = slave_account_id,   # <-- slave account, not master!
                ticket      = ticket,
                symbol      = data.get("symbol"),
                trade_type  = data.get("trade_type"),
                volume      = copy_volume,
                open_price  = data.get("price_open"),
                close_price = None,
                profit      = 0.0,
                open_time   = datetime.now(timezone.utc),
                close_time  = None,
            )
            db.session.add(trade)
            db.session.commit()
            calculate_and_save(trade, _socketio)
            log.info(f"Trade {ticket} saved to DB (account_id={slave_account_id}).")
    except Exception as e:
        log.error(f"Failed to save trade to DB: {e}")


def _update_close_in_db(app, slave_ticket: int):
    """Mark slave trade closed in DB with final close price + profit."""
    try:
        from app import db
        from models.trade import Trade

        with app.app_context():
            trade = Trade.query.filter_by(ticket=slave_ticket).first()
            if not trade:
                log.warning(f"Trade {slave_ticket} not found in DB — cannot update close.")
                return

            # Try to get close price + profit from MT5 deal history
            history = mt5.history_deals_get(
                datetime.now(timezone.utc) - timedelta(minutes=5),
                datetime.now(timezone.utc) + timedelta(minutes=1),
            )
            close_deal = None
            if history:
                for deal in history:
                    if deal.position_id == slave_ticket and deal.entry == 1:
                        close_deal = deal
                        break

            trade.close_time = datetime.now(timezone.utc)
            if close_deal:
                trade.close_price = close_deal.price
                trade.profit      = close_deal.profit

            db.session.commit()
            log.info(f"Trade {slave_ticket} closed in DB (profit={getattr(close_deal, 'profit', '?')}).")
    except Exception as e:
        log.error(f"Failed to update close in DB: {e}")


# ── Main Slave Runner ─────────────────────────────────────────────────────────

def run_slave(terminal_path: str, master_account_id: int, volume_multiplier: float):
    if not MT5_AVAILABLE:
        log.error("MT5 package not available. Exiting.")
        return

    log.info(f"Connecting to Slave Terminal: {terminal_path}")
    if not mt5.initialize(path=terminal_path):
        log.error(f"initialize() failed: {mt5.last_error()}")
        return

    info = mt5.account_info()
    if info:
        log.info(f"Connected to Slave account: {info.login} on {info.server}")

    svc = MT5Service()
    MT5Service._initialized = True

    # Build the Flask app ONCE — with start_workers=False so APScheduler
    # and market data broadcast are NOT started in this process.
    from app import create_app
    flask_app = create_app(start_workers=False)
    log.info("Flask app context ready (no scheduler started).")

    # In-memory map: master_ticket -> slave_ticket
    master_to_slave: dict[int, int] = {}

    # Look up slave account DB ID
    slave_account_id = None
    with flask_app.app_context():
        from models.broker_account import BrokerAccount
        slave = BrokerAccount.query.filter_by(
            master_account_id=master_account_id,
            role="SLAVE"
        ).first()
        if slave:
            slave_account_id = slave.id
            log.info(f"Slave DB account: ID={slave_account_id}  account_no={slave.account_no}")
        else:
            log.warning("No SLAVE account found in DB for master_account_id=%d — trades will NOT be saved.", master_account_id)

    try:
        r = redis.from_url(Config.REDIS_URL)
        r.ping()
        log.info("Connected to Redis.")
    except Exception as e:
        log.error(f"Redis connection failed: {e}")
        return

    pubsub = r.pubsub()
    pubsub.subscribe("trade_signals")
    log.info(f"Listening for signals from Master ID={master_account_id}  multiplier={volume_multiplier}x")

    for message in pubsub.listen():
        if message['type'] != 'message':
            continue

        data = json.loads(message['data'])

        if data.get("master_account_id") != master_account_id:
            continue

        action = data.get("action")

        # ── OPEN ────────────────────────────────────────────────────────────
        if action == "OPEN":
            master_ticket = data.get("ticket")
            copy_volume   = round(data.get("volume", 0.0) * volume_multiplier, 2)
            symbol        = data.get("symbol")
            trade_type    = data.get("trade_type")

            log.info(f">> OPEN  {trade_type:4s} {symbol:10s} vol={copy_volume} (master ticket={master_ticket})")

            slave_ticket = svc.execute_trade(symbol=symbol, trade_type=trade_type, volume=copy_volume)

            if slave_ticket:
                master_to_slave[master_ticket] = slave_ticket
                log.info(f"   Copied! master={master_ticket} -> slave={slave_ticket}")
                if slave_account_id:
                    _save_trade_to_db(flask_app, slave_account_id, slave_ticket, data, copy_volume)
            else:
                log.error(f"   Failed to copy trade (master ticket={master_ticket}).")

        # ── CLOSE ───────────────────────────────────────────────────────────
        elif action == "CLOSE":
            master_ticket = data.get("ticket")
            slave_ticket  = master_to_slave.get(master_ticket)

            if slave_ticket is None:
                log.warning(f"<< CLOSE master={master_ticket}: no slave mapping found (opened before this session?)")
                continue

            log.info(f"<< CLOSE {data.get('symbol'):10s} slave_ticket={slave_ticket}")

            success = svc.close_position(slave_ticket)
            if success:
                master_to_slave.pop(master_ticket, None)
                if slave_account_id:
                    _update_close_in_db(flask_app, slave_ticket)
            else:
                log.error(f"   Failed to close slave position {slave_ticket}.")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python copier_slave.py <terminal_path> <master_account_id> <volume_multiplier>")
        sys.exit(1)
    run_slave(sys.argv[1], int(sys.argv[2]), float(sys.argv[3]))
