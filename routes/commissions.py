"""
Commissions Blueprint
Endpoints:
  GET   /api/commissions/<account_id>  — List commissions for an account
  GET   /api/commissions/trade/<trade_id> — Get commission for a specific trade
"""

from flask import Blueprint, jsonify
from models.broker_account import BrokerAccount
from models.trade import Trade
from models.commission import Commission

commissions_bp = Blueprint("commissions", __name__)


# ── GET /api/commissions/<account_id> ─────────────────────────────────────
@commissions_bp.route("/commissions/<int:account_id>", methods=["GET"])
def list_commissions(account_id: int):
    """
    List all commissions for trades belonging to the given account.
    Joins Commission → Trade → BrokerAccount.
    ---
    tags:
      - Commissions
    summary: Get all commissions for an account
    parameters:
      - in: path
        name: account_id
        required: true
        schema:
          type: integer
        description: The broker account ID
    responses:
      200:
        description: List of commissions with totals
        content:
          application/json:
            schema:
              type: object
              properties:
                account_id:
                  type: integer
                commissions:
                  type: array
                  items:
                    $ref: '#/components/schemas/Commission'
                count:
                  type: integer
                total_usd:
                  type: number
                  format: float
                  example: 25.50
      404:
        description: Account not found
      500:
        description: Internal server error
    """
    try:
        account = db.session.get(BrokerAccount, account_id)
        if not account:
            return jsonify({"error": f"Account {account_id} not found"}), 404

        # Fetch commissions via joined query
        results = (
            Commission.query
            .join(Trade, Commission.trade_id == Trade.id)
            .filter(Trade.account_id == account_id)
            .order_by(Commission.created_at.desc())
            .all()
        )

        total = sum(c.amount for c in results)

        return jsonify({
            "account_id":  account_id,
            "commissions": [c.to_dict() for c in results],
            "count":       len(results),
            "total_usd":   round(total, 2),
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET /api/commissions/trade/<trade_id> ─────────────────────────────────
@commissions_bp.route("/commissions/trade/<int:trade_id>", methods=["GET"])
def get_commission_for_trade(trade_id: int):
    """
    Return the commission for a specific trade.
    ---
    tags:
      - Commissions
    summary: Get commission for a trade
    parameters:
      - in: path
        name: trade_id
        required: true
        schema:
          type: integer
        description: The trade ID
    responses:
      200:
        description: Commission record
        content:
          application/json:
            schema:
              type: object
              properties:
                commission:
                  $ref: '#/components/schemas/Commission'
      404:
        description: No commission found for this trade
    """
    commission = Commission.query.filter_by(trade_id=trade_id).first()
    if not commission:
        return jsonify({"error": f"No commission found for trade {trade_id}"}), 404
    return jsonify({"commission": commission.to_dict()}), 200
