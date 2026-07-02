"""
Users Blueprint
Endpoints:
  POST  /api/users        — Create a user
  GET   /api/users        — List all users
  GET   /api/users/<id>   — Get a single user
  DELETE /api/users/<id>  — Delete a user
"""

from flask import Blueprint, request, jsonify
from app import db
from models.user import User

users_bp = Blueprint("users", __name__)


# ── POST /api/users ────────────────────────────────────────────────────────
@users_bp.route("/users", methods=["POST"])
def create_user():
    """
    Create a new CRM user.
    ---
    tags:
      - Users
    summary: Create a user
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - name
              - email
            properties:
              name:
                type: string
                example: John Doe
              email:
                type: string
                format: email
                example: john@example.com
    responses:
      201:
        description: User created successfully
        content:
          application/json:
            schema:
              type: object
              properties:
                message:
                  type: string
                user:
                  $ref: '#/components/schemas/User'
      400:
        description: Missing or invalid fields
      409:
        description: Email already exists
      500:
        description: Internal server error
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        name  = data.get("name",  "").strip()
        email = data.get("email", "").strip().lower()

        if not name:
            return jsonify({"error": "Field 'name' is required"}), 400
        if not email:
            return jsonify({"error": "Field 'email' is required"}), 400

        # Check duplicate
        if User.query.filter_by(email=email).first():
            return jsonify({"error": f"User with email '{email}' already exists"}), 409

        user = User(name=name, email=email)
        db.session.add(user)
        db.session.commit()

        return jsonify({"message": "User created", "user": user.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ── GET /api/users ─────────────────────────────────────────────────────────
@users_bp.route("/users", methods=["GET"])
def list_users():
    """
    List all users.
    ---
    tags:
      - Users
    summary: Get all users
    responses:
      200:
        description: A list of all users
        content:
          application/json:
            schema:
              type: object
              properties:
                users:
                  type: array
                  items:
                    $ref: '#/components/schemas/User'
                count:
                  type: integer
      500:
        description: Internal server error
    """
    try:
        users = User.query.order_by(User.created_at.desc()).all()
        return jsonify({"users": [u.to_dict() for u in users], "count": len(users)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET /api/users/<id> ────────────────────────────────────────────────────
@users_bp.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id: int):
    """
    Get a single user by ID.
    ---
    tags:
      - Users
    summary: Retrieve a user
    parameters:
      - in: path
        name: user_id
        required: true
        schema:
          type: integer
        description: The user ID
    responses:
      200:
        description: User found
        content:
          application/json:
            schema:
              type: object
              properties:
                user:
                  $ref: '#/components/schemas/User'
      404:
        description: User not found
    """
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": f"User {user_id} not found"}), 404
    return jsonify({"user": user.to_dict()}), 200


# ── DELETE /api/users/<id> ─────────────────────────────────────────────────
@users_bp.route("/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id: int):
    """
    Delete a user and all their linked accounts/trades (cascade).
    ---
    tags:
      - Users
    summary: Delete a user
    parameters:
      - in: path
        name: user_id
        required: true
        schema:
          type: integer
        description: The user ID to delete
    responses:
      200:
        description: User deleted successfully
      404:
        description: User not found
      500:
        description: Internal server error
    """
    try:
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"error": f"User {user_id} not found"}), 404
        db.session.delete(user)
        db.session.commit()
        return jsonify({"message": f"User {user_id} deleted"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
