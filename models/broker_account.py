"""BrokerAccount model — an MT5 trading account linked to a User."""

from datetime import datetime, timezone
from app import db


class BrokerAccount(db.Model):
    __tablename__ = "broker_accounts"

    id          = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    account_no  = db.Column(db.String(50), nullable=False)   # MT5 account number
    broker_name = db.Column(db.String(100), nullable=False)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship: an account has many trades
    trades = db.relationship(
        "Trade", backref="account", lazy=True, cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "user_id":     self.user_id,
            "account_no":  self.account_no,
            "broker_name": self.broker_name,
            "created_at":  self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<BrokerAccount {self.account_no} ({self.broker_name})>"
