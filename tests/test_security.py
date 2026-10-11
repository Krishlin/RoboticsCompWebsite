"""The security properties that must not regress.

Each test here corresponds to something that was actually wrong, or to a
guard that is easy to remove by accident. They are cheap; the failures they
prevent are not.
"""

import pytest

from tests.conftest import staff_auth

PII_ROUTES = ["/register/teams", "/register/teams.csv", "/routes"]


# --- the staff gate -------------------------------------------------------

@pytest.mark.parametrize("path", PII_ROUTES)
def test_pii_routes_refuse_anonymous(client, team, path):
    """These published coach and student data to anyone with the URL."""
    resp = client.get(path)
    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers
    assert b"coach@example.org" not in resp.data


@pytest.mark.parametrize("path", PII_ROUTES)
def test_pii_routes_allow_staff(client, team, path):
    assert client.get(path, headers=staff_auth()).status_code == 200


def test_wrong_passcode_is_refused(client, team):
    resp = client.get("/register/teams.csv", headers=staff_auth("wrong"))
    assert resp.status_code == 401
    assert b"coach@example.org" not in resp.data


def test_gate_fails_closed_on_a_deployment(app_factory, client):
    """No passcode configured on Vercel must mean nobody, not everybody."""
    app = app_factory(STAFF_PASSCODE=None, ON_VERCEL=True)
    resp = app.test_client().get("/register/teams.csv")
    assert resp.status_code == 403


def test_gate_falls_open_locally(app_factory):
    """`python run.py` keeps working with no configuration at all."""
    app = app_factory(STAFF_PASSCODE=None, ON_VERCEL=False)
    assert app.test_client().get("/register/teams.csv").status_code == 200


# --- CSRF -----------------------------------------------------------------

def test_post_without_csrf_token_is_rejected(app_factory):
    app = app_factory(WTF_CSRF_ENABLED=True)
    resp = app.test_client().post("/register/", data={
        "team_name": "No Token", "adult_name": "A", "student_1": "S",
        "adult_email": "notoken@example.org", "adult_phone": "555",
    })
    assert resp.status_code == 400


def test_registration_still_works_with_csrf_enabled(app_factory):
    """The token must be reachable from the form, not just enforced."""
    app = app_factory(WTF_CSRF_ENABLED=True)
    c = app.test_client()
    page = c.get("/register/").get_data(as_text=True)
    assert 'name="csrf_token"' in page, "signup form is missing its token field"


# --- headers --------------------------------------------------------------

def test_security_headers_present(client):
    h = client.get("/").headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"


# --- the CSV contract -----------------------------------------------------

def test_csv_includes_team_number(client, team):
    """Everything else joins on team_number; a paper list without it is inert."""
    body = client.get("/register/teams.csv", headers=staff_auth()).get_data(as_text=True)
    header, first = body.splitlines()[0], body.splitlines()[1]
    assert header.split(",")[0] == "team_number"
    assert first.split(",")[0] == "100"


# --- mail honesty ---------------------------------------------------------

def test_shared_sender_is_not_promised_to_the_registrant(app_factory, monkeypatch):
    """The sandbox sender cannot reach a coach, so don't claim it will."""
    import app.registration.routes as reg
    monkeypatch.setattr(reg, "send_email", lambda **kw: True)

    app = app_factory(MAIL_SENDER_IS_SHARED=True)
    body = app.test_client().post("/register/", data={
        "team_name": "Shared", "adult_name": "A", "student_1": "S",
        "adult_email": "shared@example.org", "adult_phone": "555",
    }, follow_redirects=True).get_data(as_text=True)

    assert "could not send" in body
    assert "on its way" not in body
