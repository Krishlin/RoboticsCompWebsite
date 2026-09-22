"""Stripe checkout and webhook.

None of this needs a real Stripe key. Signature verification is plain HMAC
over the request body, so a correctly signed payload can be built here with a
fake secret and checked for real — that test exercises the actual crypto, not
a mock of it. Only a genuine end-to-end charge needs live keys, and that is a
manual step with `stripe listen`.
"""

import hashlib
import hmac
import json
import time

import pytest

from app.db import db
from app.models import Order, OrderItem, StripeEvent
from app.store.catalog import CATALOG, CatalogError, cart_total_cents, price_cart

WEBHOOK_SECRET = "whsec_test_not_a_real_secret"


# --- catalog: the price-integrity boundary --------------------------------

def test_price_comes_from_catalog_not_the_request():
    priced = price_cart([("kit", 1)])
    assert priced[0]["unit_amount_cents"] == CATALOG["kit"]["amount_cents"] == 10_000


def test_unknown_sku_is_refused():
    with pytest.raises(CatalogError):
        price_cart([("free_robot", 1)])


def test_unpriced_sku_cannot_be_bought():
    """practice_field has no price yet; it must not become a $0 line."""
    assert CATALOG["practice_field"]["amount_cents"] is None
    with pytest.raises(CatalogError):
        price_cart([("practice_field", 1)])


@pytest.mark.parametrize("qty", [0, -1, "abc", 1.9, None, 9999])
def test_bad_quantities_are_refused(qty):
    with pytest.raises(CatalogError):
        price_cart([("kit", qty)])


def test_duplicate_sku_is_refused():
    with pytest.raises(CatalogError):
        price_cart([("kit", 1), ("kit", 1)])


def test_total_is_computed_in_integer_cents():
    total = cart_total_cents(price_cart([("registration", 1), ("kit", 2), ("microbit", 1)]))
    assert total == 2_000 + 20_000 + 2_000
    assert isinstance(total, int)


# --- checkout route -------------------------------------------------------

def _stub_stripe(monkeypatch, captured):
    import app.store.routes as routes

    class FakeSession:
        id = "cs_test_123"
        url = "https://checkout.stripe.com/c/pay/cs_test_123"

    def fake_create(**kwargs):
        captured.update(kwargs)
        return FakeSession()

    monkeypatch.setattr(routes.stripe.checkout.Session, "create", staticmethod(fake_create))
    return captured


def test_forged_amount_in_the_form_is_ignored(app_factory, monkeypatch):
    """The classic attack: a hidden price field. It must have no effect."""
    captured = {}
    app = app_factory(STRIPE_SECRET_KEY="sk_test_x", PUBLIC_BASE_URL="https://example.org")
    _stub_stripe(monkeypatch, captured)

    resp = app.test_client().post("/store/checkout", data={
        "email": "coach@example.org",
        "qty_kit": "1",
        "amount": "1", "price": "1", "unit_amount": "1",  # all ignored
    })
    assert resp.status_code == 303

    line = captured["line_items"][0]
    assert line["price_data"]["unit_amount"] == 10_000

    with app.app_context():
        order = Order.query.one()
        assert order.amount_expected_cents == 10_000
        assert order.status == "pending"   # not paid by merely starting checkout


def test_registration_only_cart_collects_no_address(app_factory, monkeypatch):
    captured = {}
    app = app_factory(STRIPE_SECRET_KEY="sk_test_x", PUBLIC_BASE_URL="https://example.org")
    _stub_stripe(monkeypatch, captured)
    app.test_client().post("/store/checkout", data={
        "email": "c@example.org", "qty_registration": "1"})
    assert "shipping_address_collection" not in captured


def test_physical_cart_collects_an_address(app_factory, monkeypatch):
    captured = {}
    app = app_factory(STRIPE_SECRET_KEY="sk_test_x", PUBLIC_BASE_URL="https://example.org")
    _stub_stripe(monkeypatch, captured)
    app.test_client().post("/store/checkout", data={
        "email": "c@example.org", "qty_kit": "1"})
    assert captured["shipping_address_collection"]["allowed_countries"] == ["US"]


def test_session_id_placeholder_survives_into_success_url(app_factory, monkeypatch):
    """An f-string would eat the braces and Stripe would never substitute."""
    captured = {}
    app = app_factory(STRIPE_SECRET_KEY="sk_test_x", PUBLIC_BASE_URL="https://example.org")
    _stub_stripe(monkeypatch, captured)
    app.test_client().post("/store/checkout", data={
        "email": "c@example.org", "qty_kit": "1"})
    assert captured["success_url"].endswith("{CHECKOUT_SESSION_ID}")
    assert captured["success_url"].startswith("https://example.org/")


def test_checkout_without_stripe_key_is_503_not_500(app_factory):
    app = app_factory(STRIPE_SECRET_KEY=None)
    resp = app.test_client().post("/store/checkout", data={
        "email": "c@example.org", "qty_kit": "1"})
    assert resp.status_code == 503


# --- webhook --------------------------------------------------------------

def _signed(payload: dict, secret: str = WEBHOOK_SECRET):
    """Build a genuinely Stripe-signed request body."""
    body = json.dumps(payload).encode()
    ts = int(time.time())
    signed_payload = f"{ts}.".encode() + body
    sig = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return body, f"t={ts},v1={sig}"


def _completed_event(order_public_id, event_id="evt_1", amount=10_000):
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_test_123",
            "payment_status": "paid",
            "amount_total": amount,
            "payment_intent": "pi_test_1",
            "metadata": {"order_public_id": order_public_id},
            "client_reference_id": order_public_id,
        }},
    }


@pytest.fixture
def paid_app(app_factory):
    app = app_factory(STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET)
    with app.app_context():
        order = Order(public_id="SUM-TEST01", email="c@example.org",
                      status="pending", amount_expected_cents=10_000)
        order.items = [OrderItem(sku="kit", label="Official kit",
                                 unit_amount_cents=10_000, quantity=1)]
        db.session.add(order)
        db.session.commit()
    return app


def test_webhook_rejects_a_forged_signature(paid_app):
    """The single most important test here: a forgery must not fulfil."""
    body, _ = _signed(_completed_event("SUM-TEST01"))
    resp = paid_app.test_client().post(
        "/store/webhook", data=body,
        headers={"Stripe-Signature": "t=1,v1=" + "0" * 64,
                 "Content-Type": "application/json"})
    assert resp.status_code == 400
    with paid_app.app_context():
        assert Order.query.one().status == "pending"


def test_webhook_rejects_a_missing_signature(paid_app):
    body, _ = _signed(_completed_event("SUM-TEST01"))
    resp = paid_app.test_client().post("/store/webhook", data=body,
                                       headers={"Content-Type": "application/json"})
    assert resp.status_code == 400
    with paid_app.app_context():
        assert Order.query.one().status == "pending"


def test_webhook_accepts_a_valid_signature_and_fulfils(paid_app):
    body, sig = _signed(_completed_event("SUM-TEST01"))
    resp = paid_app.test_client().post(
        "/store/webhook", data=body,
        headers={"Stripe-Signature": sig, "Content-Type": "application/json"})
    assert resp.status_code == 200
    with paid_app.app_context():
        order = Order.query.one()
        assert order.status == "paid"
        assert order.amount_total_cents == 10_000
        assert order.stripe_payment_intent_id == "pi_test_1"


def test_webhook_is_idempotent(paid_app):
    """Stripe retries as a matter of course. Twice must fulfil once."""
    body, sig = _signed(_completed_event("SUM-TEST01"))
    headers = {"Stripe-Signature": sig, "Content-Type": "application/json"}
    c = paid_app.test_client()
    assert c.post("/store/webhook", data=body, headers=headers).status_code == 200
    assert c.post("/store/webhook", data=body, headers=headers).status_code == 200
    with paid_app.app_context():
        assert StripeEvent.query.count() == 1
        assert Order.query.one().status == "paid"


def test_unpaid_session_does_not_fulfil(paid_app):
    event = _completed_event("SUM-TEST01")
    event["data"]["object"]["payment_status"] = "unpaid"
    body, sig = _signed(event)
    paid_app.test_client().post("/store/webhook", data=body, headers={
        "Stripe-Signature": sig, "Content-Type": "application/json"})
    with paid_app.app_context():
        assert Order.query.one().status == "pending"


def test_unknown_event_type_returns_200(paid_app):
    """Erroring on events we ignore makes Stripe disable the endpoint."""
    body, sig = _signed({"id": "evt_x", "type": "customer.created",
                         "data": {"object": {}}})
    resp = paid_app.test_client().post("/store/webhook", data=body, headers={
        "Stripe-Signature": sig, "Content-Type": "application/json"})
    assert resp.status_code == 200


def test_success_page_never_marks_an_order_paid(paid_app):
    """It is reachable by typing the URL, so it must assert nothing."""
    paid_app.test_client().get("/store/success?session_id=cs_test_123")
    with paid_app.app_context():
        assert Order.query.one().status == "pending"


def test_webhook_is_csrf_exempt(app_factory):
    """With CSRF on — as it is in production — Stripe must still get through.

    Stripe cannot send a CSRF token, so a webhook that is protected is a
    webhook that always 400s: every order paid for and none fulfilled. Every
    other webhook test runs with CSRF off, so without this one the exemption
    is never actually exercised.
    """
    app = app_factory(STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET, WTF_CSRF_ENABLED=True)
    with app.app_context():
        order = Order(public_id="SUM-CSRF01", email="c@example.org",
                      status="pending", amount_expected_cents=10_000)
        order.items = [OrderItem(sku="kit", label="Official kit",
                                 unit_amount_cents=10_000, quantity=1)]
        db.session.add(order)
        db.session.commit()

    body, sig = _signed(_completed_event("SUM-CSRF01", event_id="evt_csrf"))
    resp = app.test_client().post("/store/webhook", data=body, headers={
        "Stripe-Signature": sig, "Content-Type": "application/json"})
    assert resp.status_code == 200, "webhook is being blocked by CSRF protection"
    with app.app_context():
        assert Order.query.filter_by(public_id="SUM-CSRF01").one().status == "paid"
