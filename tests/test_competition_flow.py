"""End-to-end checks for the competition pages that write results.

Covers the paths where two branches' code meets: the referee creates a
result, rankings read it, the admin edits or replays it, and the scheduler
must not regenerate over it.
"""

from datetime import datetime

import pytest

from app.db import db
from app.models import AuditEntry, Match, MatchResult, Team
from tests.conftest import _build


# These pages are only registered with REGISTRATION_ONLY off, and it defaults
# to on, so the shared fixtures would 404 every request in this file.
@pytest.fixture
def app(tmp_path):
    return _build(tmp_path, REGISTRATION_ONLY=False)


@pytest.fixture
def app_factory(tmp_path):
    def make(**overrides):
        return _build(tmp_path, REGISTRATION_ONLY=False, **overrides)

    return make


@pytest.fixture
def teams_and_match(app):
    """Four High School teams and one scheduled qualification match, 101 v 102."""
    with app.app_context():
        teams = []
        for number in (101, 102, 103, 104):
            team = Team(
                team_number=number,
                name=f"Team {number}",
                affiliation="Test School",
                division="High School",
                students="Student A",
                adult_name="Coach",
                adult_email=f"coach{number}@example.org",
            )
            db.session.add(team)
            teams.append(team)
        db.session.flush()
        match = Match(
            match_number=1,
            phase="qualification",
            division="High School",
            arena="Arena 1",
            scheduled_time=datetime(2026, 10, 24, 9, 0),
            red_team_id=teams[0].id,
            blue_team_id=teams[1].id,
            status="scheduled",
        )
        db.session.add(match)
        db.session.commit()
        return match.id


RED_WIN = {
    "outcome": "red",
    "red_final_zone": "Center",
    "blue_final_zone": "Off Arena",
    "win_time_seconds": "42.5",
}


def _rankings(client):
    return client.get("/rankings/High_School").get_data(as_text=True)


def test_referee_submit_locks_and_feeds_rankings(app, client, teams_and_match):
    match_id = teams_and_match

    resp = client.post(f"/referee/submit/{match_id}", data=RED_WIN)
    assert resp.status_code == 302

    with app.app_context():
        result = MatchResult.query.filter_by(match_id=match_id).one()
        assert result.outcome == "red"
        assert result.win_time_seconds == 42.5
        assert db.session.get(Match, match_id).status == "complete"

    # A second submission is refused: only the head ref can change it now.
    again = client.post(f"/referee/submit/{match_id}", data={**RED_WIN, "outcome": "blue"})
    assert again.status_code == 409
    with app.app_context():
        assert MatchResult.query.filter_by(match_id=match_id).one().outcome == "red"


def test_admin_edit_writes_audit_and_rejects_unknown_zone(app, client, teams_and_match):
    match_id = teams_and_match
    client.post(f"/referee/submit/{match_id}", data=RED_WIN)

    bad = client.post(f"/admin/edit/{match_id}", data={**RED_WIN, "red_final_zone": "Moon"})
    assert "final zone must be one of" in bad.get_data(as_text=True)

    ok = client.post(f"/admin/edit/{match_id}", data={**RED_WIN, "outcome": "tie"})
    assert ok.status_code == 302
    with app.app_context():
        assert MatchResult.query.filter_by(match_id=match_id).one().outcome == "tie"
        entry = AuditEntry.query.filter_by(match_id=match_id, field="outcome").one()
        assert (entry.old_value, entry.new_value) == ("red", "tie")


def test_admin_can_enter_missing_result(app, client, teams_and_match):
    match_id = teams_and_match

    resp = client.post(f"/admin/edit/{match_id}", data=RED_WIN)
    assert resp.status_code == 302
    with app.app_context():
        assert MatchResult.query.filter_by(match_id=match_id).one().submitted_by == "admin"
        assert db.session.get(Match, match_id).status == "complete"
        assert AuditEntry.query.filter_by(match_id=match_id).count() >= 3


def test_replay_replaces_original_only_once_complete(app, client, teams_and_match):
    match_id = teams_and_match
    client.post(f"/referee/submit/{match_id}", data=RED_WIN)
    assert client.post("/admin/replay", data={"original_match_id": match_id}).status_code == 302

    # A second replay of the same match is refused.
    assert client.post("/admin/replay", data={"original_match_id": match_id}).status_code == 400

    with app.app_context():
        replay = Match.query.filter_by(replaces_match_id=match_id).one()
        replay_id = replay.id
        assert replay.status == "scheduled"

    # Until the replay is played, the original still counts: 101 has 3 points.
    from app.rankings.logic import get_division_rankings

    with app.app_context():
        by_number = {r["team_number"]: r for r in get_division_rankings("High School")}
        assert by_number[101]["win_points"] == 3
        assert by_number[101]["matches_played"] == 1

    client.post(f"/referee/submit/{replay_id}", data={**RED_WIN, "outcome": "blue"})

    # Once it is, only the replay counts: 102 won it, 101 is back to 0.
    with app.app_context():
        by_number = {r["team_number"]: r for r in get_division_rankings("High School")}
        assert by_number[101]["win_points"] == 0
        assert by_number[102]["win_points"] == 3
        assert by_number[101]["matches_played"] == 1


def test_regenerate_refused_once_matches_are_played(app, client, teams_and_match):
    match_id = teams_and_match
    client.post(f"/referee/submit/{match_id}", data=RED_WIN)

    resp = client.post("/schedule/api/generate", json={"use_advanced": True, "clear_existing": True})
    assert resp.status_code == 409
    assert "already been played" in resp.get_json()["error"]

    with app.app_context():
        # Nothing was deleted and the result still belongs to the same pairing.
        match = db.session.get(Match, match_id)
        assert match is not None and match.status == "complete"
        assert MatchResult.query.filter_by(match_id=match_id).count() == 1


def test_regenerate_allowed_before_anything_is_played(app, client, teams_and_match):
    # Four teams on two arenas can't avoid back-to-back matches, and the
    # generator rightly refuses that; ten can.
    with app.app_context():
        for number in range(105, 111):
            db.session.add(Team(
                team_number=number,
                name=f"Team {number}",
                affiliation="Test School",
                division="High School",
                students="Student A",
                adult_name="Coach",
                adult_email=f"coach{number}@example.org",
            ))
        db.session.commit()

    resp = client.post("/schedule/api/generate", json={"use_advanced": True, "clear_existing": True})
    assert resp.status_code == 200, resp.get_json()
    with app.app_context():
        assert Match.query.filter_by(phase="qualification").count() == resp.get_json()["matches_generated"]


def test_schedule_generate_needs_csrf_header_when_csrf_is_on(app_factory):
    app = app_factory(WTF_CSRF_ENABLED=True)
    resp = app.test_client().post("/schedule/api/generate", json={"use_advanced": True})
    assert resp.status_code == 400
