"""
Accounts Blueprint
Endpoints:
  POST  /api/accounts              — Add a broker account to a user
  GET   /api/accounts/<user_id>    — List accounts for a user
  DELETE /api/accounts/<id>        — Remove a broker account
"""

from flask import Blueprint, request, jsonify
from app import db
from models.user import User
from models.broker_account import BrokerAccount

accounts_bp = Blueprint("accounts", __name__)


# ── POST /api/accounts ─────────────────────────────────────────────────────
@accounts_bp.route("/accounts", methods=["POST"])
def add_account():
    """
    Add a new broker account for a user.
    ---
    tags:
      - Accounts
    summary: Create a broker account
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - user_id
              - account_no
              - broker_name
            properties:
              user_id:
                type: integer
                example: 1
              account_no:
                type: string
                example: "5052406468"
              broker_name:
                type: string
                example: MetaQuotes-Demo
    responses:
      201:
        description: Account added successfully
        content:
          application/json:
            schema:
              type: object
              properties:
                message:
                  type: string
                account:
                  $ref: '#/components/schemas/BrokerAccount'
      400:
        description: Missing or invalid fields
      404:
        description: User not found
      500:
        description: Internal server error
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        user_id     = data.get("user_id")
        account_no  = str(data.get("account_no", "")).strip()
        broker_name = str(data.get("broker_name", "")).strip()

        if not user_id:
            return jsonify({"error": "Field 'user_id' is required"}), 400
        if not account_no:
            return jsonify({"error": "Field 'account_no' is required"}), 400
        if not broker_name:
            return jsonify({"error": "Field 'broker_name' is required"}), 400

        # Verify user exists
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": f"User {user_id} not found"}), 404

        account = BrokerAccount(
            user_id=user_id,
            account_no=account_no,
            broker_name=broker_name,
        )
        db.session.add(account)
        db.session.commit()

        return jsonify({"message": "Account added", "account": account.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ── GET /api/accounts/<user_id> ────────────────────────────────────────────
@accounts_bp.route("/accounts/<int:user_id>", methods=["GET"])
def list_accounts(user_id: int):
    """
    List all broker accounts for a given user.
    ---
    tags:
      - Accounts
    summary: Get accounts for a user
    parameters:
      - in: path
        name: user_id
        required: true
        schema:
          type: integer
        description: The user ID
    responses:
      200:
        description: List of broker accounts
        content:
          application/json:
            schema:
              type: object
              properties:
                user_id:
                  type: integer
                accounts:
                  type: array
                  items:
                    $ref: '#/components/schemas/BrokerAccount'
                count:
                  type: integer
      404:
        description: User not found
      500:
        description: Internal server error
    """
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": f"User {user_id} not found"}), 404

        accounts = BrokerAccount.query.filter_by(user_id=user_id).all()
        return jsonify({
            "user_id":  user_id,
            "accounts": [a.to_dict() for a in accounts],
            "count":    len(accounts),
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── DELETE /api/accounts/<id> ──────────────────────────────────────────────
@accounts_bp.route("/accounts/<int:account_id>", methods=["DELETE"])
def delete_account(account_id: int):
    """
    Remove a broker account and all its trades (cascade).
    ---
    tags:
      - Accounts
    summary: Delete a broker account
    parameters:
      - in: path
        name: account_id
        required: true
        schema:
          type: integer
        description: The broker account ID to delete
    responses:
      200:
        description: Account deleted successfully
      404:
        description: Account not found
      500:
        description: Internal server error
    """
    try:
        account = BrokerAccount.query.get(account_id)
        if not account:
            return jsonify({"error": f"Account {account_id} not found"}), 404
        db.session.delete(account)
        db.session.commit()
        return jsonify({"message": f"Account {account_id} deleted"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
