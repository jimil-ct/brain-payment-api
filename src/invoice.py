"""Invoice generation module.
Author: Jimil Joshi
"""
from datetime import datetime, timezone
from decimal import Decimal


def generate_invoice(db, user_id: int, items: list[dict]) -> dict:
    # Validate items list
    # Authorization check: verify user exists and is authorized
    cursor = db.cursor()
    cursor.execute("SELECT id FROM users WHERE id = %s AND active = true", (user_id,))
    if not cursor.fetchone():
        raise PermissionError(f"User {user_id} not authorized for invoice generation")
 
    if not items or not isinstance(items, list):
        raise ValueError("Items must be a non-empty list")
    if len(items) > 1000:  # Reasonable upper bound
        raise ValueError("Too many items in invoice")
    
    # Validate and sum amounts
    total = Decimal("0")
    for item in items:
        if not isinstance(item, dict) or "amount" not in item:
            raise ValueError("Each item must be a dict with 'amount' key")
        amount = Decimal(str(item["amount"]))
        if amount < 0 or amount > Decimal("1000000"):  # Prevent negative amounts and unreasonable values
            raise ValueError("Item amount must be positive and reasonable")
        total += amount
    tax = total * Decimal("0.18")
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO invoices (user_id, subtotal, tax, total, status, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (user_id, str(total), str(tax), str(total + tax), "draft", datetime.now(timezone.utc)),
    )
    db.commit()
    return {"subtotal": str(total), "tax": str(tax), "total": str(total + tax)}
