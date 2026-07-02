"""
TradePulse — Application Factory
Creates and wires together all Flask extensions, blueprints, and services.
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from flasgger import Swagger

# ── Shared extension instances (imported by other modules) ─────────────────
db = SQLAlchemy()
socketio = SocketIO()

SWAGGER_CONFIG = {
    "openapi": "3.0.0",
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs",
}

SWAGGER_TEMPLATE = {
    "openapi": "3.0.0",
    "info": {
        "title": "TradePulse API",
        "description": (
            "REST API for TradePulse — a MetaTrader5 trade sync, "
            "commission calculation, and live market data platform."
        ),
        "version": "1.0.0",
        "contact": {
            "name": "TradePulse Support",
        },
    },
    "servers": [
        {"url": "/", "description": "Local server"}
    ],
    "components": {
        "schemas": {
            "User": {
                "type": "object",
                "properties": {
                    "id":         {"type": "integer",  "example": 1},
                    "name":       {"type": "string",   "example": "John Doe"},
                    "email":      {"type": "string",   "example": "john@example.com"},
                    "created_at": {"type": "string",   "format": "date-time"},
                },
            },
            "BrokerAccount": {
                "type": "object",
                "properties": {
                    "id":           {"type": "integer", "example": 1},
                    "user_id":      {"type": "integer", "example": 1},
                    "account_no":        {"type": "string",  "example": "5052406468"},
                    "broker_name":       {"type": "string",  "example": "MetaQuotes-Demo"},
                    "role":              {"type": "string",  "example": "STANDALONE"},
                    "master_account_id": {"type": "integer", "example": 1, "nullable": True},
                    "volume_multiplier": {"type": "number",  "example": 1.0},
                    "login":             {"type": "integer", "example": 5052406468, "nullable": True},
                    "server":            {"type": "string",  "example": "MetaQuotes-Demo", "nullable": True},
                    "terminal_path":     {"type": "string",  "example": "C:\\Program Files\\MT5\\terminal64.exe", "nullable": True},
                    "copy_sl_tp":        {"type": "boolean", "example": True},
                    "max_drawdown":      {"type": "number",  "example": 10.0, "nullable": True},
                    "is_active":         {"type": "boolean", "example": True},
                    "created_at":        {"type": "string",  "format": "date-time"},
                },
            },
            "Trade": {
                "type": "object",
                "properties": {
                    "id":           {"type": "integer", "example": 1},
                    "account_id":   {"type": "integer", "example": 1},
                    "ticket":       {"type": "integer", "example": 123456789},
                    "master_ticket_id": {"type": "integer", "example": 987654321, "nullable": True},
                    "symbol":       {"type": "string",  "example": "EURUSD"},
                    "trade_type":   {"type": "string",  "example": "BUY", "enum": ["BUY", "SELL"]},
                    "volume":       {"type": "number",  "example": 0.5},
                    "open_price":   {"type": "number",  "example": 1.08450, "nullable": True},
                    "close_price":  {"type": "number",  "example": 1.08520, "nullable": True},
                    "sl":           {"type": "number",  "example": 1.08000, "nullable": True},
                    "tp":           {"type": "number",  "example": 1.09000, "nullable": True},
                    "profit":       {"type": "number",  "example": 35.0},
                    "open_time":    {"type": "string",  "format": "date-time", "nullable": True},
                    "close_time":   {"type": "string",  "format": "date-time", "nullable": True},
                    "status":       {"type": "string",  "example": "CLOSED", "enum": ["PENDING", "OPEN", "CLOSING", "CLOSED", "ERROR"]},
                },
            },
            "Commission": {
                "type": "object",
                "properties": {
                    "id":         {"type": "integer", "example": 1},
                    "trade_id":   {"type": "integer", "example": 1},
                    "amount":     {"type": "number",  "example": 2.50},
                    "created_at": {"type": "string",  "format": "date-time"},
                },
            },
        }
    },
}


def create_app(config_class=None, start_workers: bool = True):
    """
    Application factory.

    Args:
        config_class:  Optional config class override (useful for testing).
        start_workers: If False, skips starting APScheduler and the market data
                       broadcast. Set to False in copier workers so they can
                       access the DB without triggering background jobs.
    """
    from config import Config
    config_class = config_class or Config

    app = Flask(__name__)
    app.config.from_object(config_class)

    # ── Initialise extensions ──────────────────────────────────────────────
    db.init_app(app)
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode="eventlet",
        logger=False,
        engineio_logger=False,
    )

    # ── Initialise Swagger / OpenAPI docs ──────────────────────────────────
    Swagger(app, config=SWAGGER_CONFIG, template=SWAGGER_TEMPLATE)

    # ── Register blueprints ────────────────────────────────────────────────
    from routes.users import users_bp
    from routes.accounts import accounts_bp
    from routes.trades import trades_bp
    from routes.commissions import commissions_bp

    app.register_blueprint(users_bp,       url_prefix="/api")
    app.register_blueprint(accounts_bp,    url_prefix="/api")
    app.register_blueprint(trades_bp,      url_prefix="/api")
    app.register_blueprint(commissions_bp, url_prefix="/api")

    @app.route("/")
    def index():
        return {
            "status": "TradePulse Server is running 🚀",
            "docs":   "http://localhost:5000/apidocs",
            "spec":   "http://localhost:5000/apispec.json",
        }

    # ── Register SocketIO event handlers ──────────────────────────────────
    from sockets import events  # noqa: F401 — side-effect import

    # ── Create DB tables (first run) ───────────────────────────────────────
    with app.app_context():
        db.create_all()

    if start_workers:
        # ── Start background scheduler ─────────────────────────────────────────
        from workers.sync_worker import start_scheduler
        start_scheduler(app)

        # ── Start live market data broadcast ──────────────────────────────────
        from live_data.market_data import start_market_broadcast
        start_market_broadcast(socketio)

    return app
