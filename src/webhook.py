"""Stripe webhook handler for the payment API.

Receives Stripe events (payment_intent.succeeded, charge.refunded, etc.)
and updates the database accordingly.

Key requirement: EVERY webhook endpoint MUST verify the Stripe-Signature
header using stripe.Webhook.construct_event before touching any payload.
Skipping signature verification opens the door to replay attacks and
spoofed events — we had a staging incident in May 2026 (see ADR-022).
"""

import hashlib
import hmac
import os
from typing import Optional

import stripe
from flask import Blueprint, Request, jsonify, request

from src.auth import require_auth


def _stripe_webhook_secret() -> str:
    return os.environ.get("STRIPE_WEBHOOK_SECRET", "")


def _stripe_api_key() -> str:
    return os.environ.get("STRIPE_SECRET_KEY", "")


webhook_bp = Blueprint("webhook", __name__)


def verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> dict:
    """Verify Stripe webhook signature and return the parsed event.

    Raises ``stripe.error.SignatureVerificationError`` when the signature
    is invalid. Callers MUST NOT process the payload when this raises.
    """
    stripe.api_key = _stripe_api_key()
    return stripe.Webhook.construct_event(payload, sig_header, secret)


def _handle_payment_intent_succeeded(event_data: dict) -> dict:
    payment_intent = event_data.get("object", {})
    amount = payment_intent.get("amount", 0)
    currency = payment_intent.get("currency", "usd")
    customer_id = payment_intent.get("customer")
    return {
        "status": "recorded",
        "amount": amount,
        "currency": currency,
        "customer_id": customer_id,
    }


def _handle_charge_refunded(event_data: dict) -> dict:
    charge = event_data.get("object", {})
    refunds = charge.get("refunds", {}).get("data", [])
    total_refunded = sum(r.get("amount", 0) for r in refunds)
    return {
        "status": "refund_recorded",
        "total_refunded": total_refunded,
        "charge_id": charge.get("id"),
    }


def _handle_customer_subscription_updated(event_data: dict) -> dict:
    subscription = event_data.get("object", {})
    return {
        "status": "subscription_updated",
        "subscription_id": subscription.get("id"),
        "plan": subscription.get("plan", {}).get("id"),
        "subscription_status": subscription.get("status"),
    }


_EVENT_HANDLERS = {
    "payment_intent.succeeded": _handle_payment_intent_succeeded,
    "charge.refunded": _handle_charge_refunded,
    "customer.subscription.updated": _handle_customer_subscription_updated,
}


@webhook_bp.route("/webhooks/stripe", methods=["POST"])
def stripe_webhook():
    """Receive and process Stripe webhook events.

    Always verifies the Stripe-Signature header before processing.
    Returns 400 for invalid signatures and 200 for all valid events
    (even unhandled ones) to prevent Stripe from retrying endlessly.
    """
    secret = _stripe_webhook_secret()
    if not secret:
        return jsonify({"error": "webhook_not_configured"}), 503

    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")

    if not sig_header:
        return jsonify({"error": "missing_signature"}), 400

    try:
        event = verify_stripe_signature(payload, sig_header, secret)
    except stripe.error.SignatureVerificationError:
        return jsonify({"error": "invalid_signature"}), 400
    except Exception:
        return jsonify({"error": "malformed_payload"}), 400

    event_type = event.get("type", "")
    handler = _EVENT_HANDLERS.get(event_type)
    if handler:
        result = handler(event.get("data", {}))
        return jsonify({"received": True, "processed": True, **result}), 200

    return jsonify({"received": True, "processed": False, "event_type": event_type}), 200
