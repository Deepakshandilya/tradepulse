"""User model — represents a CRM client."""

from datetime import datetime, timezone
from app import db


class User(db.Model):
    __tablename__ = "users"

    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name       = db.Column(db.String(100), nullable=False)
    email      = db.Column(db.String(150), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship: a user can have many broker accounts
    accounts = db.relationship(
        "BrokerAccount", backref="user", lazy=True, cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "name":       self.name,
            "email":      self.email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<User {self.email}>"
