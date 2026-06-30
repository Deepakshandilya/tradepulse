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

    # ── MetaTrader 5 ───────────────────────────────────────────────────────
    MT5_LOGIN: int = int(os.getenv("MT5_LOGIN", "0"))
    MT5_PASSWORD: str = os.getenv("MT5_PASSWORD", "")
    MT5_SERVER: str = os.getenv("MT5_SERVER", "")

    # ── Background Jobs ────────────────────────────────────────────────────
    TRADE_SYNC_INTERVAL_SECONDS: int = 60   # How often to auto-sync MT5 trades
    MARKET_DATA_INTERVAL_SECONDS: int = 1   # Live price broadcast interval

    # ── Commission ─────────────────────────────────────────────────────────
    COMMISSION_PER_LOT: float = 5.0         # USD charged per lot traded
