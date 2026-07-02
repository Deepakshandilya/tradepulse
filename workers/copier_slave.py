"""
Copier Slave Worker — TradePulse

Connects to the Slave MT5 terminal using explicit credentials.
Listens to Redis Streams for OPEN and CLOSE signals and mirrors them.
Maintains state in the database mapping master_ticket_id to slave ticket.
Uses Consumer Groups and XACK for reliable message processing.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
import logging
import redis
import time
import threading
import queue
from datetime import datetime, timezone, timedelta

from config import Config
from services.mt5_service import MT5Service
from utils.encryption import decrypt_password

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


# ── Async DB Queue ────────────────────────────────────────────────────────────
db_queue = queue.Queue()

# ── DB Helpers ────────────────────────────────────────────────────────────────

def _save_trade_to_db(app, slave_account_id: int, ticket: int, data: dict, copy_volume: float):
    """Write newly opened slave trade to DB with master_ticket_id mapping."""
    try:
        from app import db, socketio as _socketio
        from models.trade import Trade
        from services.commission_engine import calculate_and_save

        with app.app_context():
            if Trade.query.filter_by(ticket=ticket).first():
                log.debug(f"Trade {ticket} already in DB — skipping.")
                return

            trade = Trade(
                account_id       = slave_account_id,
                ticket           = ticket,
                master_ticket_id = data.get("ticket"),
                symbol           = data.get("symbol"),
                trade_type       = data.get("trade_type"),
                volume           = copy_volume,
                open_price       = data.get("price_open"),
                sl               = data.get("sl"),
                tp               = data.get("tp"),
                close_price      = None,
                profit           = 0.0,
                open_time        = datetime.now(timezone.utc),
                close_time       = None,
                status           = "OPEN"
            )
            db.session.add(trade)
            db.session.commit()
            calculate_and_save(trade, _socketio)
            log.info(f"Trade {ticket} saved to DB (account_id={slave_account_id}, master_ticket={data.get('ticket')}).")
    except Exception as e:
        log.error(f"Failed to save trade to DB: {e}")
        raise e


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

            time.sleep(1.0) # Keeping original delay to allow MT5 deal history to sync
            
            history = mt5.history_deals_get(
                datetime.now(timezone.utc) - timedelta(days=1),
                datetime.now(timezone.utc) + timedelta(days=1),
            )
            close_deal = None
            if history:
                for deal in history:
                    if deal.position_id == slave_ticket and deal.entry == 1:
                        close_deal = deal
                        break

            trade.close_time = datetime.now(timezone.utc)
            trade.status = "CLOSED"
            if close_deal:
                trade.close_price = close_deal.price
                trade.profit      = close_deal.profit

            db.session.commit()
            log.info(f"Trade {slave_ticket} closed in DB (profit={getattr(close_deal, 'profit', '?')}).")
    except Exception as e:
        log.error(f"Failed to update close in DB: {e}")
        raise e

def _update_sltp_in_db(app, slave_ticket: int, sl: float, tp: float):
    try:
        from app import db
        from models.trade import Trade
        with app.app_context():
            trade = Trade.query.filter_by(ticket=slave_ticket).first()
            if trade:
                trade.sl = sl
                trade.tp = tp
                db.session.commit()
    except Exception as e:
        log.error(f"Failed to update SL/TP in DB: {e}")
        raise e

def _update_partial_close_in_db(app, slave_ticket: int, close_volume: float):
    # For a partial close, we just reduce the volume of the open trade in DB.
    try:
        from app import db
        from models.trade import Trade
        with app.app_context():
            trade = Trade.query.filter_by(ticket=slave_ticket).first()
            if trade:
                trade.volume = max(0.0, round(trade.volume - close_volume, 2))
                db.session.commit()
    except Exception as e:
        log.error(f"Failed to update partial close in DB: {e}")
        raise e

def db_worker_loop(app):
    """Background thread loop to process DB writes asynchronously."""
    # We create a separate redis connection for the thread to XACK
    r = redis.from_url(Config.REDIS_URL)
    while True:
        task = db_queue.get()
        if task is None:
            break
        
        try:
            action = task.get("action")
            if action == "OPEN":
                _save_trade_to_db(app, task["slave_account_id"], task["slave_ticket"], task["data"], task["copy_volume"])
            elif action == "CLOSE":
                _update_close_in_db(app, task["slave_ticket"])
            elif action == "MODIFY":
                _update_sltp_in_db(app, task["slave_ticket"], task["sl"], task["tp"])
            elif action == "PARTIAL_CLOSE":
                _update_partial_close_in_db(app, task["slave_ticket"], task["close_volume"])
            
            # XACK message after successful DB update
            r.xack(task["stream_name"], task["group_name"], task["message_id"])
        except Exception as e:
            log.error(f"Async DB worker failed for {task.get('action')}: {e}")
        finally:
            db_queue.task_done()



def _get_slave_ticket(app, slave_account_id: int, master_ticket_id: int) -> int | None:
    """Look up slave ticket from DB mapping."""
    with app.app_context():
        from models.trade import Trade
        trade = Trade.query.filter_by(
            account_id=slave_account_id, 
            master_ticket_id=master_ticket_id, 
            status="OPEN"
        ).first()
        if trade:
            return trade.ticket
    return None

# ── Main Slave Runner ─────────────────────────────────────────────────────────

def run_slave(terminal_path: str, master_account_id: int, volume_multiplier: float):
    if not MT5_AVAILABLE:
        log.error("MT5 package not available. Exiting.")
        return

    # Build the Flask app ONCE
    from app import create_app
    flask_app = create_app(start_workers=False)
    log.info("Flask app context ready (no scheduler started).")

    # Start Async DB Worker Thread
    threading.Thread(target=db_worker_loop, args=(flask_app,), daemon=True).start()
    log.info("Started Async DB Worker Thread.")

    # Look up slave account DB ID and credentials
    slave_account_id = None
    login = None
    password = None
    server = None

    with flask_app.app_context():
        from models.broker_account import BrokerAccount
        slave = BrokerAccount.query.filter_by(
            master_account_id=master_account_id,
            role="SLAVE"
        ).first()
        
        if slave:
            slave_account_id = slave.id
            login = slave.login
            password = decrypt_password(slave.password_encrypted)
            server = slave.server
            log.info(f"Slave DB account: ID={slave_account_id}  account_no={slave.account_no}")
        else:
            log.error("No SLAVE account found in DB for master_account_id=%d. Exiting.", master_account_id)
            return

    if not login or not password or not server:
        log.error("Slave account is missing explicit credentials (login, password, server).")
        return

    log.info(f"Connecting to Slave Terminal: {terminal_path} for account {login}")
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

    log.info(f"Connected to Slave account: {info.login} on {info.server}")

    svc = MT5Service(
        path=terminal_path,
        login=login,
        password=password,
        server=server
    )
    MT5Service._initialized = True

    try:
        r = redis.from_url(Config.REDIS_URL)
        r.ping()
        log.info("Connected to Redis.")
    except Exception as e:
        log.error(f"Redis connection failed: {e}")
        return

    # Setup Redis Streams Consumer Group
    STREAM_NAME = "trade_stream"
    GROUP_NAME = f"slave_group_{slave_account_id}"
    CONSUMER_NAME = f"consumer_{slave_account_id}"

    try:
        r.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
        log.info(f"Created consumer group {GROUP_NAME}.")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            log.debug(f"Consumer group {GROUP_NAME} already exists.")
        else:
            log.error(f"Error creating consumer group: {e}")
            return

    log.info(f"Listening for signals from Master ID={master_account_id}  multiplier={volume_multiplier}x")

    try:
        check_pending = True
        while True:
            if check_pending:
                # Read unacknowledged pending messages for this consumer
                messages = r.xreadgroup(GROUP_NAME, CONSUMER_NAME, {STREAM_NAME: "0"}, count=5)
                if not messages or not messages[0][1]:
                    check_pending = False
                    continue
            else:
                # Block for up to 1000ms for new messages
                messages = r.xreadgroup(GROUP_NAME, CONSUMER_NAME, {STREAM_NAME: ">"}, count=5, block=1000)
                
                if not messages:
                    continue

            for stream, msgs in messages:
                for message_id, msg_data in msgs:
                    try:
                        action = msg_data.get(b"action", b"").decode()
                        payload_str = msg_data.get(b"payload", b"{}").decode()
                        data = json.loads(payload_str)

                        if data.get("master_account_id") != master_account_id:
                            # Acknowledge and skip if not for this master
                            r.xack(STREAM_NAME, GROUP_NAME, message_id)
                            continue

                        # ── OPEN ────────────────────────────────────────────────────────────
                        if action == "OPEN":
                            master_ticket = data.get("ticket")
                            copy_volume   = round(data.get("volume", 0.0) * volume_multiplier, 2)
                            symbol        = data.get("symbol")
                            trade_type    = data.get("trade_type")
                            sl            = data.get("sl", 0.0)
                            tp            = data.get("tp", 0.0)

                            # Idempotency check: Did we already process this?
                            existing_ticket = _get_slave_ticket(flask_app, slave_account_id, master_ticket)
                            if existing_ticket:
                                log.warning(f"Trade already mapped in DB (master={master_ticket} -> slave={existing_ticket}). Skipping.")
                                r.xack(STREAM_NAME, GROUP_NAME, message_id)
                                continue

                            log.info(f">> OPEN  {trade_type:4s} {symbol:10s} vol={copy_volume} (master ticket={master_ticket})")

                            slave_ticket = svc.execute_trade(symbol=symbol, trade_type=trade_type, volume=copy_volume, sl=sl, tp=tp)

                            if slave_ticket:
                                log.info(f"   Copied! master={master_ticket} -> slave={slave_ticket}")
                                db_queue.put({
                                    "action": "OPEN",
                                    "slave_account_id": slave_account_id,
                                    "slave_ticket": slave_ticket,
                                    "data": data,
                                    "copy_volume": copy_volume,
                                    "stream_name": STREAM_NAME,
                                    "group_name": GROUP_NAME,
                                    "message_id": message_id
                                })
                            else:
                                log.error(f"   Failed to copy trade (master ticket={master_ticket}). Will retry.")

                        # ── CLOSE ───────────────────────────────────────────────────────────
                        elif action == "CLOSE":
                            master_ticket = data.get("ticket")
                            slave_ticket = _get_slave_ticket(flask_app, slave_account_id, master_ticket)

                            if slave_ticket is None:
                                log.warning(f"<< CLOSE master={master_ticket}: no slave mapping found in DB. Acknowledging as invalid/stale.")
                                r.xack(STREAM_NAME, GROUP_NAME, message_id)
                                continue

                            log.info(f"<< CLOSE {data.get('symbol'):10s} slave_ticket={slave_ticket}")

                            success = svc.close_position(slave_ticket)
                            if success:
                                db_queue.put({
                                    "action": "CLOSE",
                                    "slave_ticket": slave_ticket,
                                    "stream_name": STREAM_NAME,
                                    "group_name": GROUP_NAME,
                                    "message_id": message_id
                                })
                            else:
                                log.error(f"   Failed to close slave position {slave_ticket}. Will retry.")

                        # ── PARTIAL CLOSE ───────────────────────────────────────────────────
                        elif action == "PARTIAL_CLOSE":
                            master_ticket = data.get("ticket")
                            close_volume  = round(data.get("close_volume", 0.0) * volume_multiplier, 2)
                            slave_ticket = _get_slave_ticket(flask_app, slave_account_id, master_ticket)

                            if slave_ticket is None:
                                log.warning(f"<< PARTIAL CLOSE master={master_ticket}: no slave mapping found in DB.")
                                r.xack(STREAM_NAME, GROUP_NAME, message_id)
                                continue

                            log.info(f"<< PARTIAL CLOSE {data.get('symbol'):10s} slave_ticket={slave_ticket} vol={close_volume}")

                            success = svc.close_position(slave_ticket, volume=close_volume)
                            if success:
                                db_queue.put({
                                    "action": "PARTIAL_CLOSE",
                                    "slave_ticket": slave_ticket,
                                    "close_volume": close_volume,
                                    "stream_name": STREAM_NAME,
                                    "group_name": GROUP_NAME,
                                    "message_id": message_id
                                })
                            else:
                                log.error(f"   Failed to partially close position {slave_ticket}. Will retry.")

                        # ── MODIFY ──────────────────────────────────────────────────────────
                        elif action == "MODIFY":
                            master_ticket = data.get("ticket")
                            sl            = data.get("sl", 0.0)
                            tp            = data.get("tp", 0.0)
                            slave_ticket = _get_slave_ticket(flask_app, slave_account_id, master_ticket)

                            if slave_ticket is None:
                                log.warning(f"~~ MODIFY master={master_ticket}: no slave mapping found in DB.")
                                r.xack(STREAM_NAME, GROUP_NAME, message_id)
                                continue

                            log.info(f"~~ MODIFY {data.get('symbol'):10s} slave_ticket={slave_ticket} sl={sl} tp={tp}")

                            success = svc.modify_position(slave_ticket, sl=sl, tp=tp)
                            if success:
                                db_queue.put({
                                    "action": "MODIFY",
                                    "slave_ticket": slave_ticket,
                                    "sl": sl,
                                    "tp": tp,
                                    "stream_name": STREAM_NAME,
                                    "group_name": GROUP_NAME,
                                    "message_id": message_id
                                })
                            else:
                                log.error(f"   Failed to modify position {slave_ticket}. Will retry.")
                                
                    except Exception as e:
                        log.error(f"Error processing message {message_id}: {e}")
                        # Don't ack so it can be retried or moved to a dead letter queue later
                        
    except KeyboardInterrupt:
        log.info("Slave copier stopped by user.")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python copier_slave.py <terminal_path> <master_account_id> <volume_multiplier>")
        sys.exit(1)
    run_slave(sys.argv[1], int(sys.argv[2]), float(sys.argv[3]))
