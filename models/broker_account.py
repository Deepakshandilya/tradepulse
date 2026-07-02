"""BrokerAccount model — an MT5 trading account linked to a User."""

from datetime import datetime, timezone
from app import db


class BrokerAccount(db.Model):
    __tablename__ = "broker_accounts"

    # Prevent the same MT5 account from being registered twice for the same user
    __table_args__ = (
        db.UniqueConstraint("user_id", "account_no", name="uq_user_account"),
    )

    id          = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    account_no  = db.Column(db.String(50), nullable=False)   # MT5 account number
    broker_name = db.Column(db.String(100), nullable=False)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Trade Copier Fields
    role              = db.Column(db.String(20), default="STANDALONE")  # MASTER, SLAVE, STANDALONE
    master_account_id = db.Column(db.Integer, db.ForeignKey("broker_accounts.id"), nullable=True)
    volume_multiplier = db.Column(db.Float, default=1.0)
    
    # MT5 Terminal Credentials & Connection
    login              = db.Column(db.BigInteger, nullable=True) # Making nullable=True initially for migration safety
    password_encrypted = db.Column(db.LargeBinary, nullable=True)
    server             = db.Column(db.String(100), nullable=True)
    terminal_path      = db.Column(db.String(255), nullable=True, unique=True)
    
    # Granular Risk Management
    copy_sl_tp   = db.Column(db.Boolean, default=True)
    max_drawdown = db.Column(db.Float, nullable=True)
    is_active    = db.Column(db.Boolean, default=True)


    # Relationship: an account has many trades
    trades = db.relationship(
        "Trade", backref="account", lazy=True, cascade="all, delete-orphan"
    )
    
    # Relationship: a master can have many slaves
    slaves = db.relationship(
        "BrokerAccount", 
        backref=db.backref("master", remote_side=[id]),
        lazy="select"
    )

    def to_dict(self) -> dict:
        return {
            "id":                self.id,
            "user_id":           self.user_id,
            "account_no":        self.account_no,
            "broker_name":       self.broker_name,
            "role":              self.role,
            "master_account_id": self.master_account_id,
            "volume_multiplier": self.volume_multiplier,
            "login":             self.login,
            "server":            self.server,
            "terminal_path":     self.terminal_path,
            "copy_sl_tp":        self.copy_sl_tp,
            "max_drawdown":      self.max_drawdown,
            "is_active":         self.is_active,
            "created_at":        self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<BrokerAccount {self.account_no} ({self.broker_name})>"
