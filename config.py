import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Central configuration for TradePulse."""

    # ── Flask ──────────────────────────────────────────────────────────────
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    DEBUG: bool = os.getenv("FLASK_ENV", "development") == "development"

    # ── Database ───────────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI: str = os.getenv(
        "DB_URI", "mysql+pymysql://root:password@localhost/tradepulse"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ECHO: bool = False  # Set True to log SQL queries

    # ── Redis (Trade Copier) ───────────────────────────────────────────────
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # ── MetaTrader 5 ───────────────────────────────────────────────────────
    _login_str = os.getenv("MT5_LOGIN", "")
    MT5_LOGIN: int = int(_login_str) if _login_str.isdigit() else ""
    MT5_PASSWORD: str = os.getenv("MT5_PASSWORD", "")
    MT5_SERVER: str = os.getenv("MT5_SERVER", "")

    # ── Background Jobs ────────────────────────────────────────────────────
    TRADE_SYNC_INTERVAL_SECONDS: int = 60   # How often to auto-sync MT5 trades
    MARKET_DATA_INTERVAL_SECONDS: int = 1   # Live price broadcast interval

    # ── Commission ─────────────────────────────────────────────────────────
    COMMISSION_PER_LOT: float = 5.0         # USD charged per lot traded
