"""Tests for Stripe webhook handler."""

import hashlib
import hmac
import json
import os
import time
from typing import Optional

import pytest

from src.webhook import verify_stripe_signature, stripe_webhook


@pytest.fixture(autouse=True)
def webhook_env(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret_at_least_32_chars_long")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")


def _make_stripe_sig(payload: bytes, secret: str, timestamp: Optional[int] = None) -> str:
    """Build a valid Stripe-Signature header value."""
    import stripe  # lazy import so we can monkeypatch

    ts = timestamp or int(time.time())
    signed = f"{ts}.{payload.decode()}"
    sig = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _payment_intent_payload(amount: int = 2000, currency: str = "usd") -> dict:
    return {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_test_123",
                "amount": amount,
                "currency": currency,
                "customer": "cus_test_456",
            }
        },
    }


def test_verify_signature_accepts_valid_sig(monkeypatch):
    """Stripe SDK path — we monkeypatch construct_event so the test doesn't need real keys."""
    payload = b'{"type":"payment_intent.succeeded"}'
    event = {"type": "payment_intent.succeeded", "data": {"object": {}}}

    monkeypatch.setattr("src.webhook.stripe.Webhook.construct_event", lambda *a, **kw: event)
    result = verify_stripe_signature(payload, "t=123,v1=abc", "whsec_test")
    assert result["type"] == "payment_intent.succeeded"


def test_verify_signature_rejects_bad_sig(monkeypatch):
    import stripe

    def _raise(*a, **kw):
        raise stripe.error.SignatureVerificationError("bad sig", "t=1,v1=bad")

    monkeypatch.setattr("src.webhook.stripe.Webhook.construct_event", _raise)
    with pytest.raises(stripe.error.SignatureVerificationError):
        verify_stripe_signature(b"payload", "t=1,v1=bad", "secret")


def test_stripe_webhook_returns_400_for_missing_secret(monkeypatch, app):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "")
    with app.test_client() as client:
        resp = client.post(
            "/webhooks/stripe",
            data=b"{}",
            headers={"Stripe-Signature": "t=1,v1=abc", "Content-Type": "application/json"},
        )
    assert resp.status_code == 503


def test_stripe_webhook_returns_400_for_invalid_sig(monkeypatch, app):
    import stripe

    def _raise(*a, **kw):
        raise stripe.error.SignatureVerificationError("bad", "sig")

    monkeypatch.setattr("src.webhook.stripe.Webhook.construct_event", _raise)
    with app.test_client() as client:
        resp = client.post(
            "/webhooks/stripe",
            data=b'{"type":"payment_intent.succeeded"}',
            headers={"Stripe-Signature": "t=1,v1=bad", "Content-Type": "application/json"},
        )
    assert resp.status_code == 400


def test_stripe_webhook_processes_payment_intent(monkeypatch, app):
    payload = _payment_intent_payload(amount=5000, currency="gbp")
    payload_bytes = json.dumps(payload).encode()
    event = {**payload}
    monkeypatch.setattr("src.webhook.stripe.Webhook.construct_event", lambda *a, **kw: event)

    with app.test_client() as client:
        resp = client.post(
            "/webhooks/stripe",
            data=payload_bytes,
            headers={"Stripe-Signature": "t=1,v1=ok", "Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["received"] is True
    assert data["amount"] == 5000
    assert data["currency"] == "gbp"


def test_stripe_webhook_acks_unknown_events(monkeypatch, app):
    payload = json.dumps({"type": "some.unknown.event", "data": {"object": {}}}).encode()
    monkeypatch.setattr(
        "src.webhook.stripe.Webhook.construct_event",
        lambda *a, **kw: {"type": "some.unknown.event", "data": {"object": {}}},
    )
    with app.test_client() as client:
        resp = client.post(
            "/webhooks/stripe",
            data=payload,
            headers={"Stripe-Signature": "t=1,v1=ok", "Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    assert resp.get_json()["processed"] is False


# ---------------------------------------------------------------------------
# conftest-style fixture — add to conftest.py if one exists, or keep here
# ---------------------------------------------------------------------------

@pytest.fixture()
def app():
    """Minimal Flask app with the webhook blueprint registered."""
    from flask import Flask
    from src.webhook import webhook_bp

    application = Flask(__name__)
    application.register_blueprint(webhook_bp)
    application.config["TESTING"] = True
    return application
