"""
Commission Engine — calculates and persists commissions for trades.

Rule: Configurable rate per lot (default $5/lot via Config.COMMISSION_PER_LOT).
Design: idempotent — safe to call multiple times for the same trade.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app import db
from models.commission import Commission
from config import Config

if TYPE_CHECKING:
    from flask_socketio import SocketIO
    from models.trade import Trade

log = logging.getLogger(__name__)

# Read rate from central config — NOT hardcoded. Change in config.py or .env.
COMMISSION_PER_LOT: float = Config.COMMISSION_PER_LOT


def calculate_and_save(trade: "Trade", socketio: "SocketIO") -> Commission | None:
    """
    Calculate the commission for a trade and persist it.

    Idempotency guarantee:
        If a commission already exists for this trade_id, the function
        returns the existing record without creating a duplicate.

    After saving, emits a 'commission_created' WebSocket event.

    Args:
        trade:    The Trade ORM instance (must already be committed, i.e., have an id).
        socketio: The SocketIO instance used to emit the notification event.

    Returns:
        The Commission instance (new or existing), or None on error.
    """
    try:
        # ── Idempotency check ──────────────────────────────────────────────
        existing = Commission.query.filter_by(trade_id=trade.id).first()
        if existing:
            log.debug("Commission already exists for trade %d — skipping.", trade.id)
            return existing

        # ── Calculate ──────────────────────────────────────────────────────
        amount = round(trade.volume * COMMISSION_PER_LOT, 2)

        commission = Commission(trade_id=trade.id, amount=amount)
        db.session.add(commission)
        db.session.commit()

        log.info(
            "Commission created: trade_id=%d  volume=%.2f lots  amount=$%.2f",
            trade.id,
            trade.volume,
            amount,
        )

        # ── WebSocket notification ────────────────────────────────────────
        socketio.emit("commission_created", {
            "trade_id":   trade.id,
            "ticket":     trade.ticket,
            "symbol":     trade.symbol,
            "volume":     trade.volume,
            "amount_usd": amount,
        })

        return commission

    except Exception as exc:
        db.session.rollback()
        log.error("Failed to create commission for trade %d: %s", trade.id, exc)
        return None
