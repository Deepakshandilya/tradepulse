"""
DB Utility — thin helpers for SQLAlchemy session management.
"""

from __future__ import annotations
import logging
from app import db

log = logging.getLogger(__name__)


def safe_commit() -> bool:
    """
    Attempt to commit the current session.
    Rolls back automatically on failure.

    Returns:
        True if commit succeeded, False otherwise.
    """
    try:
        db.session.commit()
        return True
    except Exception as exc:
        db.session.rollback()
        log.error("DB commit failed — rolled back. Reason: %s", exc)
        return False


def safe_add_commit(obj) -> bool:
    """
    Add a single ORM instance and commit in one call.

    Args:
        obj: Any SQLAlchemy model instance.

    Returns:
        True if successful, False otherwise.
    """
    try:
        db.session.add(obj)
        db.session.commit()
        return True
    except Exception as exc:
        db.session.rollback()
        log.error("Failed to add/commit %r: %s", obj, exc)
        return False
