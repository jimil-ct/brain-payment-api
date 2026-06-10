"""Payment processing module.
Author: Jimil Joshi
"""
import os
import uuid
import hmac
import hashlib
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional


STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")


def create_payment_intent(db, user_id: int, amount: Decimal, currency: str = "usd") -> dict:
    # Validate user_id is a positive integer
    if not isinstance(user_id, int):
        raise ValueError("user_id must be an integer")
    if user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    idempotency_key = str(uuid.uuid4())
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO payments (user_id, amount, currency, status, idempotency_key, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (user_id, str(amount), currency, "pending", idempotency_key, datetime.now(timezone.utc)),
    )
    db.commit()
    return {"payment_id": idempotency_key, "status": "pending", "amount": str(amount)}


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    if not WEBHOOK_SECRET:
        raise ValueError("STRIPE_WEBHOOK_SECRET not configured")
    expected = hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def process_refund(db, payment_id: str, reason: str) -> dict:
    cursor = db.cursor()
    # First check current payment state
    cursor.execute(
        "SELECT status FROM payments WHERE idempotency_key = %s",
        (payment_id,)
    )
    result = cursor.fetchone()
    if not result:
        raise ValueError(f"Payment {payment_id} not found")
    current_status = result[0]
    if current_status not in ("paid", "successful"):
        raise ValueError(f"Cannot refund payment with status '{current_status}'")
    # Proceed with refund
    cursor.execute(
        "UPDATE payments SET status = %s, refund_reason = %s, updated_at = %s WHERE idempotency_key = %s",
        ("refunded", reason, datetime.now(timezone.utc), payment_id),
    )
    db.commit()
    return {"payment_id": payment_id, "status": "refunded"}
