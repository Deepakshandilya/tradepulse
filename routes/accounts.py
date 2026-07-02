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
from utils.encryption import encrypt_password

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
              role:
                type: string
                example: "MASTER"
              master_account_id:
                type: integer
                example: 1
              volume_multiplier:
                type: number
                example: 1.0
              login:
                type: string
                example: "5052406468"
              password:
                type: string
                example: "password123"
              server:
                type: string
                example: "MetaQuotes-Demo"
              terminal_path:
                type: string
                example: "C:/Program Files/MT5/terminal64.exe"
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
        
        # New trade copier fields
        role = str(data.get("role", "STANDALONE")).strip().upper()
        master_account_id = data.get("master_account_id")
        volume_multiplier = float(data.get("volume_multiplier", 1.0))
        
        # New explicit MT5 credentials
        login_val = data.get("login")
        password_val = data.get("password")
        server_val = data.get("server")
        terminal_path_val = data.get("terminal_path")

        if not user_id:
            return jsonify({"error": "Field 'user_id' is required"}), 400
        if not account_no:
            return jsonify({"error": "Field 'account_no' is required"}), 400
        if not broker_name:
            return jsonify({"error": "Field 'broker_name' is required"}), 400
            
        # Optional validation depending on if we strictly require them for all accounts now
        # If terminal_path is required by DB, we must enforce it here
        if role in ["MASTER", "SLAVE"]:
            if not login_val or not password_val or not server_val or not terminal_path_val:
                return jsonify({"error": "Fields 'login', 'password', 'server', and 'terminal_path' are required for MASTER/SLAVE roles."}), 400

        # Verify user exists
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"error": f"User {user_id} not found"}), 404

        # Check for duplicate: same account_no already registered for this user
        existing = BrokerAccount.query.filter_by(
            user_id=user_id, account_no=account_no
        ).first()
        if existing:
            return jsonify({
                "error": f"Account '{account_no}' is already linked to this user (id={existing.id})"
            }), 409

        account = BrokerAccount(
            user_id=user_id,
            account_no=account_no,
            broker_name=broker_name,
            role=role,
            master_account_id=master_account_id,
            volume_multiplier=volume_multiplier,
            login=login_val,
            password_encrypted=encrypt_password(password_val) if password_val else None,
            server=server_val,
            terminal_path=terminal_path_val
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
        user = db.session.get(User, user_id)
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
        account = db.session.get(BrokerAccount, account_id)
        if not account:
            return jsonify({"error": f"Account {account_id} not found"}), 404
        db.session.delete(account)
        db.session.commit()
        return jsonify({"message": f"Account {account_id} deleted"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
