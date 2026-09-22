# owner: shared / lead
#
# This file is the data contract for the whole app. Every blueprint reads
# and writes these tables — nobody creates their own tables or invents a
# parallel shape for the same data. If a field you need isn't here, ask
# before adding it, so everyone stays on the same page.
#
# All datetimes are stored in UTC.

from datetime import datetime, timezone

from app.db import db


def utcnow():
    """Naive UTC, the way this file has always stored time.

    datetime.utcnow() is deprecated on 3.12+ and scheduled for removal, but
    its replacement — datetime.now(timezone.utc) — returns an *aware* value.
    Handing that to these naive DateTime columns would mix aware and naive
    datetimes in the same column, and comparing the two raises TypeError, so
    the failure would surface later and somewhere else.

    Stripping the tzinfo keeps the stored value byte-for-byte what it was
    while dropping the deprecation. The module docstring's promise — every
    datetime here is UTC — still holds.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Team(db.Model):
    __tablename__ = "team"

    id = db.Column(db.Integer, primary_key=True)
    team_number = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    affiliation = db.Column(db.String(120), nullable=False)  # school name, or "Independent"
    division = db.Column(db.String(50), nullable=False)  # single division: "High School"

    # Stored as a single string with one student name per line. SQLite/Postgres
    # don't have a native "list of strings" column, so this is the simplest
    # thing that works. Split on "\n" to get the list back.
    students = db.Column(db.Text, nullable=False)

    adult_name = db.Column(db.String(120), nullable=False)
    adult_email = db.Column(db.String(200), unique=True, nullable=False)
    adult_phone = db.Column(db.String(30), nullable=True)

    kit_ordered = db.Column(db.Boolean, default=False, nullable=False)
    checked_in = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class Inspection(db.Model):
    __tablename__ = "inspection"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)

    passed = db.Column(db.Boolean, nullable=False)
    size_ok = db.Column(db.Boolean, nullable=False)
    weight_ok = db.Column(db.Boolean, nullable=False)
    microbit_present = db.Column(db.Boolean, nullable=False)
    team_number_displayed = db.Column(db.Boolean, nullable=False)
    ref_start_stop_test = db.Column(db.Boolean, nullable=False)

    notes = db.Column(db.Text, nullable=True)
    inspector_name = db.Column(db.String(120), nullable=True)

    # A team may have several Inspections (re-inspection is allowed and both
    # attempts are kept). The one with the latest inspected_at is current.
    inspected_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class Match(db.Model):
    __tablename__ = "match"

    id = db.Column(db.Integer, primary_key=True)
    match_number = db.Column(db.Integer, nullable=False)
    phase = db.Column(db.String(20), nullable=False)  # "qualification" or "elimination"
    division = db.Column(db.String(50), nullable=False)
    arena = db.Column(db.String(50), nullable=False)  # e.g. "Arena 1"
    scheduled_time = db.Column(db.DateTime, nullable=True)  # approximate

    red_team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=True)  # nullable: TBD in bracket
    blue_team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=True)

    status = db.Column(db.String(20), default="scheduled", nullable=False)  # scheduled/in_progress/complete
    is_replay = db.Column(db.Boolean, default=False, nullable=False)

    # Set on a replay, pointing at the match it supersedes. The superseded
    # match keeps its row and its MatchResult (the audit trail still needs
    # them) but must not be counted twice in standings, so anything that
    # scores matches has to skip every id that appears here. At most one
    # live replay per match: admin.insert_replay_match refuses a second.
    replaces_match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=True)

    bracket_round = db.Column(db.Integer, nullable=True)  # elimination only
    bracket_slot = db.Column(db.Integer, nullable=True)  # elimination only


class MatchResult(db.Model):
    __tablename__ = "match_result"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)

    outcome = db.Column(db.String(20), nullable=False)  # "red", "blue", "tie", "double_dq"
    win_time_seconds = db.Column(db.Float, nullable=True)  # start button to winner tap
    red_final_zone = db.Column(db.String(50), nullable=False)
    blue_final_zone = db.Column(db.String(50), nullable=False)

    submitted_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    submitted_by = db.Column(db.String(120), nullable=False)  # referee name or arena id

    # Rule: a MatchResult is created once, by the referee blueprint. After
    # that it may only be changed through the admin blueprint, and every
    # change must write an AuditEntry.


class AuditEntry(db.Model):
    __tablename__ = "audit_entry"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)
    changed_by = db.Column(db.String(120), nullable=False)
    changed_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    field = db.Column(db.String(50), nullable=False)
    old_value = db.Column(db.String(200), nullable=True)
    new_value = db.Column(db.String(200), nullable=True)


class Order(db.Model):
    """One trip through Stripe Checkout.

    Deliberately not hung off Team: an order may be placed before a team
    exists, may never be tied to one (a coach buying a spare micro:bit), and a
    team may place several over the season. Money and registration are
    separate records that reference each other, not one record wearing two
    hats.
    """

    __tablename__ = "order"

    id = db.Column(db.Integer, primary_key=True)

    # What goes in URLs and what a coach reads down the phone. Random, not
    # sequential: /store/success?order=4 invites walking the integers, and the
    # page names what somebody bought and where it ships.
    public_id = db.Column(db.String(32), unique=True, nullable=False, index=True)

    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=True)
    email = db.Column(db.String(200), nullable=False)

    # pending -> paid -> fulfilled, or -> cancelled / refunded.
    # "paid" means a signed webhook said so. Nothing else may set it.
    status = db.Column(db.String(20), default="pending", nullable=False, index=True)

    # Unique, so a replayed webhook that slips past the StripeEvent guard
    # still cannot create a second paid order for one checkout session.
    stripe_checkout_session_id = db.Column(db.String(120), unique=True, nullable=True)
    stripe_payment_intent_id = db.Column(db.String(120), nullable=True)

    currency = db.Column(db.String(3), default="usd", nullable=False)
    # What we intended to charge, computed from the catalog before redirecting.
    amount_expected_cents = db.Column(db.Integer, nullable=False)
    # What Stripe says it actually took. The two are compared on fulfilment
    # and a mismatch is logged loudly rather than quietly accepted.
    amount_total_cents = db.Column(db.Integer, nullable=True)

    school_name = db.Column(db.String(120), nullable=True)
    ship_name = db.Column(db.String(120), nullable=True)
    ship_line1 = db.Column(db.String(200), nullable=True)
    ship_line2 = db.Column(db.String(200), nullable=True)
    ship_city = db.Column(db.String(120), nullable=True)
    ship_state = db.Column(db.String(60), nullable=True)
    ship_postal_code = db.Column(db.String(20), nullable=True)
    ship_country = db.Column(db.String(2), nullable=True)

    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    paid_at = db.Column(db.DateTime, nullable=True)
    fulfilled_at = db.Column(db.DateTime, nullable=True)

    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")


class OrderItem(db.Model):
    """One line of an order, with the price frozen at purchase time.

    label and unit_amount_cents are copies, not lookups. When the practice
    field finally gets a price, or the kit goes up, every order placed before
    that must still show what its buyer was actually charged.
    """

    __tablename__ = "order_item"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)

    sku = db.Column(db.String(40), nullable=False)
    label = db.Column(db.String(120), nullable=False)
    unit_amount_cents = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)


class StripeEvent(db.Model):
    """Every webhook Stripe has delivered, by its event id.

    The unique constraint is the whole idempotency mechanism. Stripe retries
    on any non-2xx and on timeouts, so the same checkout.session.completed
    arrives more than once as a matter of course, not as an edge case. The
    handler inserts here first and treats the IntegrityError as "already done".
    """

    __tablename__ = "stripe_event"

    id = db.Column(db.Integer, primary_key=True)
    stripe_event_id = db.Column(db.String(120), unique=True, nullable=False, index=True)
    type = db.Column(db.String(80), nullable=False)
    received_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class ScheduleState(db.Model):
    __tablename__ = "schedule_state"

    id = db.Column(db.Integer, primary_key=True)
    is_paused = db.Column(db.Boolean, default=False, nullable=False)
    changed_by = db.Column(db.String(120), nullable=True)  # who paused/resumed the schedule
    changed_at = db.Column(db.DateTime, default=utcnow, nullable=False)  # when the state last changed

    # Use single-row design: always maintain exactly one row with id=1
    # for global schedule state.
