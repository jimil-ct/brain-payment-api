"""Invoice generation module.
Author: Jimil Joshi
"""
from datetime import datetime, timezone
from decimal import Decimal


def generate_invoice(db, user_id: int, items: list[dict]) -> dict:
    total = sum(Decimal(str(item["amount"])) for item in items)
    tax = total * Decimal("0.18")
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO invoices (user_id, subtotal, tax, total, status, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (user_id, str(total), str(tax), str(total + tax), "draft", datetime.now(timezone.utc)),
    )
    db.commit()
    return {"subtotal": str(total), "tax": str(tax), "total": str(total + tax)}
