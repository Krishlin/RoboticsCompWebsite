# owner: shared / lead
#
# Stripe Checkout, hosted. Card details never reach this application, its
# logs, or its database — the card form lives on Stripe's own domain, which
# is what keeps PCI scope at SAQ A. There is deliberately no card form here
# and there must never be one.
#
# Two rules run through everything below:
#
#   1. Prices come from catalog.py, never from the request.
#   2. An order becomes "paid" only when a signature-verified webhook says
#      so. The success_url is a URL a buyer can type, so it proves nothing.

import logging
import secrets

import stripe
from flask import (
    abort,
    current_app,
    redirect,
    render_template,
    request,
)
from sqlalchemy.exc import IntegrityError

from app import csrf
from app.db import db
from app.models import Order, OrderItem, StripeEvent, Team, utcnow
from app.store import store_bp
from app.store.catalog import (
    CatalogError,
    cart_total_cents,
    needs_shipping,
    price_cart,
    purchasable_items,
)

logger = logging.getLogger(__name__)

# Stripe substitutes this itself. It has to survive into the URL literally, so
# it is concatenated rather than interpolated — an f-string would treat the
# braces as a placeholder and raise.
SESSION_ID_PLACEHOLDER = "{CHECKOUT_SESSION_ID}"


def _stripe_key():
    key = current_app.config.get("STRIPE_SECRET_KEY")
    if not key:
        # A 503 rather than a 500: the code is fine, the deployment is not
        # configured, and those want different responses from an operator.
        logger.error("STRIPE_SECRET_KEY is not set - refusing to start a checkout")
        abort(503)
    return key


def _base_url():
    """Where Stripe should send the buyer back to.

    Config, never url_for(_external=True). On Vercel the request arrives at
    whichever deployment hostname served it, so an external url_for on a
    preview build would send a real buyer to a preview URL.
    """
    base = current_app.config.get("PUBLIC_BASE_URL")
    if not base:
        logger.error("PUBLIC_BASE_URL is not set - refusing to start a checkout")
        abort(503)
    return base.rstrip("/")


def _new_public_id() -> str:
    """Short, unguessable, and readable down a phone line."""
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no O/0, I/1, L
    return "SUM-" + "".join(secrets.choice(alphabet) for _ in range(6))


@store_bp.route("/")
def index():
    return render_template("store/index.html", items=purchasable_items())


@store_bp.route("/checkout", methods=["POST"])
def checkout():
    """Price a cart, record it, and hand the buyer to Stripe.

    Everything in request.form is untrusted. The only fields read are SKUs,
    quantities and an email address; any "amount" or "price" a caller invents
    is ignored, because price_cart looks the price up by SKU.
    """
    email = (request.form.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return render_template(
            "store/index.html", items=purchasable_items(),
            error="Enter the email address the receipt should go to.",
        ), 400

    # qty_<sku> fields, skipping anything left blank or at zero.
    raw_items = [
        (key[len("qty_"):], value)
        for key, value in request.form.items()
        if key.startswith("qty_") and str(value).strip() not in ("", "0")
    ]

    try:
        priced = price_cart(raw_items)
    except CatalogError as exc:
        return render_template(
            "store/index.html", items=purchasable_items(), error=str(exc),
        ), 400

    team_number = (request.form.get("team_number") or "").strip()
    team = Team.query.filter_by(team_number=team_number).first() if team_number.isdigit() else None

    order = Order(
        public_id=_new_public_id(),
        team_id=team.id if team else None,
        email=email,
        status="pending",
        amount_expected_cents=cart_total_cents(priced),
    )
    order.items = [OrderItem(**line) for line in priced]
    db.session.add(order)
    db.session.commit()

    stripe.api_key = _stripe_key()
    params = {
        "mode": "payment",
        "customer_email": email,
        "client_reference_id": order.public_id,
        "metadata": {"order_public_id": order.public_id},
        # Mirrored onto the PaymentIntent so a refund issued from the Stripe
        # dashboard still names the order it belongs to.
        "payment_intent_data": {"metadata": {"order_public_id": order.public_id}},
        "line_items": [
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": line["unit_amount_cents"],
                    "product_data": {"name": line["label"]},
                },
                "quantity": line["quantity"],
            }
            for line in priced
        ],
        "success_url": f"{_base_url()}/store/success?session_id=" + SESSION_ID_PLACEHOLDER,
        "cancel_url": f"{_base_url()}/store/cancel?order={order.public_id}",
    }

    # Only ask for an address when something physical is in the cart. A lone
    # $20 registration fee has nothing to post.
    if needs_shipping(priced):
        params["shipping_address_collection"] = {"allowed_countries": ["US"]}

    try:
        session = stripe.checkout.Session.create(
            **params,
            # Makes a double-clicked submit reuse the same Checkout Session
            # instead of opening a second one against the same order.
            idempotency_key=f"checkout-{order.public_id}",
        )
    except stripe.StripeError:
        logger.exception("Stripe refused to create a session for %s", order.public_id)
        return render_template(
            "store/index.html", items=purchasable_items(),
            error="We could not reach the payment provider. Nothing was charged.",
        ), 502

    order.stripe_checkout_session_id = session.id
    db.session.commit()
    return redirect(session.url, code=303)


@store_bp.route("/success")
def success():
    """Thanks page. Deliberately does not mark anything paid.

    The webhook may not have landed yet, and this page is reachable by typing
    the URL, so it reports what the order *says* rather than asserting a sale.
    """
    order = None
    session_id = request.args.get("session_id")
    if session_id:
        order = Order.query.filter_by(stripe_checkout_session_id=session_id).first()
    return render_template("store/success.html", order=order)


@store_bp.route("/cancel")
def cancel():
    public_id = request.args.get("order")
    order = Order.query.filter_by(public_id=public_id).first() if public_id else None
    return render_template("store/cancel.html", order=order)


@csrf.exempt
@store_bp.route("/webhook", methods=["POST"])
def webhook():
    """The only thing allowed to mark an order paid.

    CSRF-exempt because Stripe cannot carry a token — and safely so: a valid
    HMAC signature over the exact body proves far more than a CSRF token ever
    would.
    """
    secret = current_app.config.get("STRIPE_WEBHOOK_SECRET")
    if not secret:
        logger.error("STRIPE_WEBHOOK_SECRET is not set - rejecting webhook")
        return "", 503

    # Raw bytes. The signature covers exactly these, so parsing to JSON and
    # re-serialising would change the bytes and fail every check.
    payload = request.get_data()
    signature = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, signature, secret)
    except ValueError:
        logger.warning("Webhook rejected: body was not valid JSON")
        return "", 400
    except stripe.SignatureVerificationError:
        # Either a forgery or a secret mismatch between modes. Never fall back
        # to parsing it anyway: that is how a forged completed-checkout ships
        # a free kit.
        logger.warning("Webhook rejected: bad signature")
        return "", 400

    # Idempotency. Insert first and let the unique constraint arbitrate, so
    # two concurrent deliveries of one event cannot both proceed.
    try:
        db.session.add(StripeEvent(stripe_event_id=event["id"], type=event["type"]))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        logger.info("Webhook %s already handled - ignoring replay", event["id"])
        return "", 200

    try:
        _dispatch(event)
    except Exception:
        # The event row stays. Stripe will retry, and the retry short-circuits
        # above — so this is logged loudly for a human rather than silently
        # re-attempted forever.
        logger.exception("Webhook %s failed during fulfilment", event["id"])
        return "", 500

    return "", 200


def _plain(value):
    """Normalise a Stripe object into ordinary dicts and lists.

    construct_event hands back StripeObjects, which support value["key"] but
    raise AttributeError on value.get("key") — a dict method they deliberately
    do not implement. Every optional field below is read with .get(), because
    Stripe omits keys rather than sending nulls, so the objects have to be
    converted once at this boundary instead of being defended against at
    forty call sites.
    """
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _dispatch(event):
    kind = event["type"]
    obj = _plain(event["data"]["object"])
    if kind in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        _fulfil(obj)
    elif kind == "checkout.session.expired":
        _set_status(obj, "cancelled")
    elif kind == "charge.refunded":
        _refund(obj)
    else:
        # 200 and ignore. Returning an error for events we did not ask about
        # makes Stripe retry them forever and eventually disable the endpoint.
        logger.debug("Webhook %s ignored (%s)", event["id"], kind)


def _order_for(session):
    public_id = (session.get("metadata") or {}).get("order_public_id") \
        or session.get("client_reference_id")
    order = Order.query.filter_by(public_id=public_id).first() if public_id else None
    if order is None and session.get("id"):
        order = Order.query.filter_by(stripe_checkout_session_id=session["id"]).first()
    return order


def _fulfil(session):
    order = _order_for(session)
    if order is None:
        logger.error("Paid session %s matches no order", session.get("id"))
        return

    if session.get("payment_status") != "paid":
        logger.info("Session %s is not paid yet (%s)", session.get("id"),
                    session.get("payment_status"))
        return

    if order.status in ("paid", "fulfilled"):
        return  # already done; a retry landed

    charged = session.get("amount_total")
    if charged is not None and charged != order.amount_expected_cents:
        # Not fatal — the money has already moved, and refusing to record it
        # would be worse. But it means the catalog and the session disagree,
        # which should never happen and someone needs to look.
        logger.error(
            "Order %s amount mismatch: expected %s, Stripe charged %s",
            order.public_id, order.amount_expected_cents, charged,
        )

    order.status = "paid"
    order.paid_at = utcnow()
    order.amount_total_cents = charged
    order.stripe_payment_intent_id = session.get("payment_intent")

    shipping = (session.get("collected_information") or {}).get("shipping_details") \
        or session.get("shipping_details") or {}
    address = shipping.get("address") or {}
    order.ship_name = shipping.get("name")
    order.ship_line1 = address.get("line1")
    order.ship_line2 = address.get("line2")
    order.ship_city = address.get("city")
    order.ship_state = address.get("state")
    order.ship_postal_code = address.get("postal_code")
    order.ship_country = address.get("country")

    if order.team_id and any(i.sku == "registration" for i in order.items):
        team = db.session.get(Team, order.team_id)
        if team:
            team.kit_ordered = team.kit_ordered or any(i.sku == "kit" for i in order.items)

    db.session.commit()
    logger.info("Order %s paid (%s cents)", order.public_id, charged)


def _set_status(session, status):
    order = _order_for(session)
    if order and order.status == "pending":
        order.status = status
        db.session.commit()


def _refund(charge):
    intent = charge.get("payment_intent")
    order = Order.query.filter_by(stripe_payment_intent_id=intent).first() if intent else None
    if order:
        order.status = "refunded"
        db.session.commit()
        logger.info("Order %s refunded", order.public_id)
