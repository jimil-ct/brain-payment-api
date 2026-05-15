"""Subscription billing module.
Author: Jimil Joshi
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal


PLANS = {
    "starter": {"price": Decimal("29.00"), "interval": "monthly"},
    "pro": {"price": Decimal("99.00"), "interval": "monthly"},
    "enterprise": {"price": Decimal("299.00"), "interval": "monthly"},
}


def create_subscription(db, user_id: int, plan: str) -> dict:
    if plan not in PLANS:
        raise ValueError(f"Unknown plan: {plan}")
    plan_info = PLANS[plan]
    now = datetime.now(timezone.utc)
    next_billing = now + timedelta(days=30)
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO subscriptions (user_id, plan, price, status, current_period_start, current_period_end, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (user_id, plan, str(plan_info["price"]), "active", now, next_billing, now),
    )
    db.commit()
    return {"plan": plan, "status": "active", "next_billing": next_billing.isoformat()}


def cancel_subscription(db, subscription_id: int, immediate: bool = False) -> dict:
    cursor = db.cursor()
    status = "cancelled" if immediate else "pending_cancel"
    cursor.execute(
        "UPDATE subscriptions SET status = %s, cancelled_at = %s WHERE id = %s",
        (status, datetime.now(timezone.utc), subscription_id),
    )
    db.commit()
    return {"subscription_id": subscription_id, "status": status}
