"""Commission model — fee calculated per trade ($5/lot)."""

from datetime import datetime, timezone
from app import db


class Commission(db.Model):
    __tablename__ = "commissions"

    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    trade_id   = db.Column(db.Integer, db.ForeignKey("trades.id"), nullable=False, unique=True)
    amount     = db.Column(db.Float,   nullable=False)   # volume × $5
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "trade_id":   self.trade_id,
            "amount":     self.amount,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<Commission trade_id={self.trade_id} amount=${self.amount}>"
