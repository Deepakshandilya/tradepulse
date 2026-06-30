"""
Sync Worker — background periodic jobs powered by APScheduler.

Jobs:
  sync_all_accounts   — runs every 60 s, syncs MT5 trade history for all accounts
"""

from __future__ import annotations

import logging
from datetime import timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None

# MT5 deal.type values that represent real Forex trades (BUY=0, SELL=1).
# All other types (2=BALANCE, 3=CREDIT, 4=CHARGE, etc.) are broker-internal
# operations and must be excluded to avoid polluting the trades table.
REAL_TRADE_TYPES = {0, 1}


# ── Job implementations ────────────────────────────────────────────────────

def sync_all_accounts(app, socketio) -> None:
    """
    Sync MT5 trade history for every broker account in the database.
    Runs inside an app context so SQLAlchemy sessions work correctly.
    Skips duplicate trades (by ticket) and non-trade MT5 operations.
    Calculates commissions for newly inserted trades.
    Also syncs open positions (previously missing from the background worker).
    """
    with app.app_context():
        from models.broker_account import BrokerAccount
        from models.trade import Trade
        from services.mt5_service import MT5Service
        from services.commission_engine import calculate_and_save
        from app import db

        from config import Config
        env_account = str(Config.MT5_LOGIN)
        
        accounts = BrokerAccount.query.filter_by(account_no=env_account).all()
        if not accounts:
            log.debug("No broker account matches the .env MT5_LOGIN (%s) — nothing to sync.", env_account)
            return

        mt5 = MT5Service()
        try:
            mt5.ensure_connected()
        except ConnectionError as exc:
            log.error("MT5 connect failed in background sync: %s", exc)
            return

        try:
            for account in accounts:
                log.info("Syncing account #%d (%s)…", account.id, account.account_no)
                deals     = mt5.fetch_history()
                positions = mt5.fetch_open_positions()  # ← was missing from worker

                inserted   = 0
                skipped    = 0
                filtered   = 0
                new_trades = []

                # ── Closed deals ───────────────────────────────────────────
                # Deals come in two legs (ENTRY_IN and ENTRY_OUT) linked by position_id.
                # We use position_id as our unique ticket key and merge both legs
                # into a single row so close_price and close_time are populated.
                for deal in deals:
                    if deal.type not in REAL_TRADE_TYPES:
                        filtered += 1
                        continue

                    if not deal.symbol or deal.volume == 0:
                        filtered += 1
                        continue

                    pos_id = deal.position_id

                    if deal.entry == 1:   # DEAL_ENTRY_OUT — update existing row
                        existing = Trade.query.filter_by(ticket=pos_id).first()
                        if existing:
                            existing.close_price = deal.price
                            existing.close_time  = mt5.ts_to_datetime(deal.time)
                            existing.profit      = deal.profit
                            db.session.flush()
                            skipped += 1
                        else:
                            # Edge case: orphan exit deal — store standalone
                            trade_type = "BUY" if deal.type == 0 else "SELL"
                            from models.trade import Trade as TradeModel
                            trade = TradeModel(
                                account_id  = account.id,
                                ticket      = deal.ticket,
                                symbol      = deal.symbol,
                                trade_type  = trade_type,
                                volume      = deal.volume,
                                open_price  = None,
                                close_price = deal.price,
                                profit      = deal.profit,
                                open_time   = None,
                                close_time  = mt5.ts_to_datetime(deal.time),
                            )
                            db.session.add(trade)
                            db.session.flush()
                            new_trades.append(trade)
                            inserted += 1
                        continue

                    # DEAL_ENTRY_IN — insert new row keyed by position_id
                    if Trade.query.filter_by(ticket=pos_id).first():
                        skipped += 1
                        continue

                    trade_type = "BUY" if deal.type == 0 else "SELL"
                    from models.trade import Trade as TradeModel
                    trade = TradeModel(
                        account_id  = account.id,
                        ticket      = pos_id,
                        symbol      = deal.symbol,
                        trade_type  = trade_type,
                        volume      = deal.volume,
                        open_price  = deal.price,
                        close_price = None,
                        profit      = deal.profit,
                        open_time   = mt5.ts_to_datetime(deal.time),
                        close_time  = None,
                    )
                    db.session.add(trade)
                    db.session.flush()
                    new_trades.append(trade)
                    inserted += 1

                # ── Open positions ─────────────────────────────────────────
                for pos in positions:
                    if pos.type not in REAL_TRADE_TYPES:
                        filtered += 1
                        continue

                    if Trade.query.filter_by(ticket=pos.ticket).first():
                        skipped += 1
                        continue

                    trade_type = "BUY" if pos.type == 0 else "SELL"

                    from models.trade import Trade as TradeModel
                    trade = TradeModel(
                        account_id  = account.id,
                        ticket      = pos.ticket,
                        symbol      = pos.symbol,
                        trade_type  = trade_type,
                        volume      = pos.volume,
                        open_price  = pos.price_open,
                        close_price = None,
                        profit      = pos.profit,
                        open_time   = mt5.ts_to_datetime(pos.time),
                        close_time  = None,
                    )
                    db.session.add(trade)
                    db.session.flush()
                    new_trades.append(trade)
                    inserted += 1

                db.session.commit()

                for trade in new_trades:
                    calculate_and_save(trade, socketio)

                log.info(
                    "Account #%d sync done — inserted=%d  skipped=%d  filtered=%d",
                    account.id, inserted, skipped, filtered,
                )

        except Exception as exc:
            db.session.rollback()
            log.error("Sync error: %s", exc)


# ── Scheduler setup ────────────────────────────────────────────────────────

def _on_job_error(event) -> None:
    log.error("APScheduler job %s raised an exception: %s", event.job_id, event.exception)


def _on_job_executed(event) -> None:
    log.debug("APScheduler job %s executed successfully.", event.job_id)


def start_scheduler(app) -> None:
    """
    Initialise and start the APScheduler instance.
    Called once from the app factory.
    """
    global _scheduler

    if _scheduler and _scheduler.running:
        log.warning("Scheduler already running — skipping duplicate start.")
        return

    from app import socketio as _socketio
    from config import Config

    _scheduler = BackgroundScheduler(timezone="UTC")

    # ── Job: sync trades every 60 s ───────────────────────────────────────
    _scheduler.add_job(
        func=lambda: sync_all_accounts(app, _socketio),
        trigger="interval",
        seconds=Config.TRADE_SYNC_INTERVAL_SECONDS,
        id="sync_all_accounts",
        name="MT5 Trade Sync",
        replace_existing=True,
        misfire_grace_time=30,
    )

    _scheduler.add_listener(_on_job_error,    EVENT_JOB_ERROR)
    _scheduler.add_listener(_on_job_executed, EVENT_JOB_EXECUTED)

    _scheduler.start()
    log.info(
        "APScheduler started — trade sync every %ds.",
        Config.TRADE_SYNC_INTERVAL_SECONDS,
    )
