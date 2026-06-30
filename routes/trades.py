"""
Trades Blueprint
Endpoints:
  POST  /api/trades/sync/<account_id>  — Manually trigger MT5 trade sync
  GET   /api/trades/<account_id>       — List trades for an account
"""

from flask import Blueprint, jsonify
from app import db, socketio
from models.broker_account import BrokerAccount
from models.trade import Trade
from services.mt5_service import MT5Service
from services.commission_engine import calculate_and_save

trades_bp = Blueprint("trades", __name__)

# ── MT5 deal types that are real trades (BUY=0, SELL=1) ───────────────────
# All other types (2=BALANCE, 3=CREDIT, 4=CHARGE, 5=CORRECTION, 6=BONUS,
# 7=COMMISSION, etc.) are internal broker operations — not actual trades.
REAL_TRADE_TYPES = {0, 1}


# ── POST /api/trades/sync/<account_id> ────────────────────────────────────
@trades_bp.route("/trades/sync/<int:account_id>", methods=["POST"])
def sync_trades(account_id: int):
    """
    Manually trigger a sync of MT5 trade history for a given account.
    New trades are inserted; duplicates (by ticket) are skipped.
    Non-trade MT5 operations (balance deposits, credits, etc.) are filtered out.
    Commissions are calculated for each newly inserted trade.
    ---
    tags:
      - Trades
    summary: Sync MT5 trades for an account
    parameters:
      - in: path
        name: account_id
        required: true
        schema:
          type: integer
        description: The broker account ID to sync
    responses:
      200:
        description: Sync complete
        content:
          application/json:
            schema:
              type: object
              properties:
                message:
                  type: string
                  example: Sync complete
                closed_deals_found:
                  type: integer
                open_positions_found:
                  type: integer
                inserted:
                  type: integer
                skipped:
                  type: integer
                filtered:
                  type: integer
                  description: Non-trade MT5 operations excluded (deposits, credits, etc.)
      404:
        description: Account not found
      500:
        description: Internal server error or MT5 connection failure
    """
    account = BrokerAccount.query.get(account_id)
    if not account:
        return jsonify({"error": f"Account {account_id} not found"}), 404

    mt5 = MT5Service()
    try:
        mt5.connect()
        deals     = mt5.fetch_history()         # closed deals
        positions = mt5.fetch_open_positions()  # currently open positions

        inserted   = 0
        skipped    = 0
        filtered   = 0   # non-trade MT5 ops (deposits, credits, etc.)
        new_trades = []

        # ── Process closed deals ───────────────────────────────────────────
        for deal in deals:
            # Skip balance deposits, credit adjustments, commissions, etc.
            # Only deal.type 0 (BUY) and 1 (SELL) are real Forex trades.
            if deal.type not in REAL_TRADE_TYPES:
                filtered += 1
                continue

            # Extra safety: skip any deal with no symbol or zero volume
            if not deal.symbol or deal.volume == 0:
                filtered += 1
                continue

            if Trade.query.filter_by(ticket=deal.ticket).first():
                skipped += 1
                continue

            trade_type = "BUY" if deal.type == 0 else "SELL"
            trade = Trade(
                account_id  = account_id,
                ticket      = deal.ticket,
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

        # ── Process open positions (ticket is position ID) ─────────────────
        for pos in positions:
            # Open positions only have type 0 (BUY) or 1 (SELL) — no filter needed,
            # but guard against edge cases.
            if pos.type not in REAL_TRADE_TYPES:
                filtered += 1
                continue

            if Trade.query.filter_by(ticket=pos.ticket).first():
                skipped += 1
                continue

            trade_type = "BUY" if pos.type == 0 else "SELL"
            trade = Trade(
                account_id  = account_id,
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

        return jsonify({
            "message":             "Sync complete",
            "closed_deals_found":  len(deals),
            "open_positions_found": len(positions),
            "inserted":            inserted,
            "skipped":             skipped,
            "filtered":            filtered,
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ── GET /api/trades/<account_id> ───────────────────────────────────────────
@trades_bp.route("/trades/<int:account_id>", methods=["GET"])
def list_trades(account_id: int):
    """
    List all trades synced for a given account.
    ---
    tags:
      - Trades
    summary: Get all trades for an account
    parameters:
      - in: path
        name: account_id
        required: true
        schema:
          type: integer
        description: The broker account ID
    responses:
      200:
        description: List of trades
        content:
          application/json:
            schema:
              type: object
              properties:
                account_id:
                  type: integer
                trades:
                  type: array
                  items:
                    $ref: '#/components/schemas/Trade'
                count:
                  type: integer
      404:
        description: Account not found
      500:
        description: Internal server error
    """
    try:
        account = BrokerAccount.query.get(account_id)
        if not account:
            return jsonify({"error": f"Account {account_id} not found"}), 404

        trades = (
            Trade.query
            .filter_by(account_id=account_id)
            .order_by(Trade.open_time.desc())
            .all()
        )
        return jsonify({
            "account_id": account_id,
            "trades":     [t.to_dict() for t in trades],
            "count":      len(trades),
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
