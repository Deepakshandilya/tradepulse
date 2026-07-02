"""Trade model — a closed deal synced from MT5."""

from datetime import datetime, timezone
from app import db


class Trade(db.Model):
    __tablename__ = "trades"

    id          = db.Column(db.Integer, primary_key=True, autoincrement=True)
    account_id  = db.Column(db.Integer, db.ForeignKey("broker_accounts.id"), nullable=False)

    # MT5 unique identifier — used for deduplication
    ticket      = db.Column(db.BigInteger, unique=True, nullable=False, index=True)
    
    # Trade Copier Link
    master_ticket_id = db.Column(db.BigInteger, index=True, nullable=True)

    symbol      = db.Column(db.String(20),  nullable=False)   # e.g. EURUSD
    trade_type  = db.Column(db.String(10),  nullable=False)   # BUY / SELL
    volume      = db.Column(db.Float,       nullable=False)   # lots
    open_price  = db.Column(db.Float)
    close_price = db.Column(db.Float, nullable=True)
    sl          = db.Column(db.Float, nullable=True)
    tp          = db.Column(db.Float, nullable=True)
    profit      = db.Column(db.Float,       default=0.0)
    open_time   = db.Column(db.DateTime,    nullable=False)
    close_time  = db.Column(db.DateTime,    nullable=True)
    
    status      = db.Column(db.String(20),  default="OPEN") # PENDING, OPEN, CLOSED, ERROR

    # One-to-one back-reference from Commission
    commission  = db.relationship(
        "Commission", backref="trade", uselist=False, cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "account_id":  self.account_id,
            "ticket":      self.ticket,
            "symbol":      self.symbol,
            "trade_type":  self.trade_type,
            "volume":      self.volume,
            "open_price":  self.open_price,
            "close_price": self.close_price,
            "profit":      self.profit,
            "open_time":   self.open_time.isoformat()  if self.open_time  else None,
            "close_time":  self.close_time.isoformat() if self.close_time else None,
        }

    def __repr__(self) -> str:
        return f"<Trade #{self.ticket} {self.symbol} {self.trade_type} {self.volume}L>"
