"""Shared test fixtures.

Every fixture builds the app through create_app(**overrides) rather than
poking at config.Config, so a test never depends on what happens to be in the
developer's .env or in Vercel.

The database is a real file in a tmp_path rather than sqlite:///:memory:.
In-memory SQLite gives each *connection* its own empty database unless the
engine is pinned to a StaticPool, and the factory deliberately clears
SQLALCHEMY_ENGINE_OPTIONS for non-Postgres URIs - so a file is the honest way
to get one database that survives across connections within a test.
"""

import base64

import pytest

from app import create_app
from app.db import db
from app.models import Team

STAFF_PASSCODE = "test-passcode-not-a-real-one"


def staff_auth(passcode: str = STAFF_PASSCODE) -> dict[str, str]:
    """An HTTP Basic header for the staff gate.

    The username is ignored by app.security - there are no usernames yet - so
    it is spelled "staff" here purely to make failures readable.
    """
    raw = base64.b64encode(f"staff:{passcode}".encode()).decode()
    return {"Authorization": f"Basic {raw}"}


def _build(tmp_path, **overrides):
    dbfile = tmp_path / "test.db"
    settings = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{dbfile.as_posix()}",
        "WTF_CSRF_ENABLED": False,
        "STAFF_PASSCODE": STAFF_PASSCODE,
        "ON_VERCEL": False,
        "SECRET_KEY": "test-secret",
        "RESEND_API_KEY": None,  # never let a test reach the network
        "MAIL_FROM": "Summit <noreply@send.stemsters.org>",
        "MAIL_SENDER_IS_SHARED": False,
    }
    settings.update(overrides)
    return create_app(**settings)


@pytest.fixture
def app(tmp_path):
    """The default app: staff passcode set, CSRF off, not a deployment."""
    return _build(tmp_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def app_factory(tmp_path):
    """For tests that need non-default config - CSRF on, no passcode, etc."""

    def make(**overrides):
        return _build(tmp_path, **overrides)

    return make


@pytest.fixture
def team(app):
    """One saved team, so the PII routes have something to leak."""
    with app.app_context():
        t = Team(
            team_number=100,
            name="Test Team",
            affiliation="Test School",
            division="High School",
            students="Alice Example\nBob Example",
            adult_name="Coach Example",
            adult_email="coach@example.org",
            adult_phone="555-0100",
        )
        db.session.add(t)
        db.session.commit()
        return t.team_number
