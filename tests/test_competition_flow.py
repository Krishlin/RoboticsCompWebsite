"""End-to-end checks for the competition pages that write results.

Covers the paths where two branches' code meets: the referee records games,
rankings read them, the admin edits or replays them, and the scheduler must
not regenerate over them. Every pairing is a best-of-three series (game
manual T3), so most tests play a series game by game.
"""

import csv
import io
import zipfile
from datetime import datetime

import pytest

from app.db import db
from app.match_state import series_tally
from app.models import AuditEntry, Match, MatchResult, ScheduleState, Team
from tests.conftest import _build, head_ref_auth, staff_auth

STAFF = staff_auth(name="Ref Ana")
HEAD = head_ref_auth()


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


def _add_teams(numbers):
    teams = []
    for number in numbers:
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
    return teams


@pytest.fixture
def teams_and_match(app):
    """Four High School teams and one scheduled qualification series, 101 v 102."""
    with app.app_context():
        teams = _add_teams((101, 102, 103, 104))
        match = Match(
            match_number=1,
            phase="qualification",
            division="High School",
            arena="Arena 1",
            scheduled_time=datetime(2026, 10, 24, 10, 0),
            red_team_id=teams[0].id,
            blue_team_id=teams[1].id,
            status="scheduled",
        )
        db.session.add(match)
        db.session.commit()
        return match.id


def game(outcome, number, **extra):
    """Form data for one game, as the confirm screen posts it."""
    data = {
        "game_number": str(number),
        "outcome": outcome,
        "red_final_zone": "Plateau" if outcome != "blue" else "Ring-out",
        "blue_final_zone": "Plateau" if outcome != "red" else "Ring-out",
        "win_time_seconds": "42.5" if outcome in ("red", "blue") else "",
    }
    data.update(extra)
    return data


def submit(client, match_id, outcome, number, **extra):
    return client.post(f"/referee/submit/{match_id}", data=game(outcome, number, **extra), headers=STAFF)


def _rankings(app):
    from app.rankings.logic import get_division_rankings

    with app.app_context():
        return {r["team_number"]: r for r in get_division_rankings("High School")}


# --- the referee screen ------------------------------------------------------

def test_series_is_best_of_three_and_locks_each_game(app, client, teams_and_match):
    match_id = teams_and_match

    assert client.post(f"/referee/start/{match_id}", headers=STAFF).status_code == 302
    with app.app_context():
        match = db.session.get(Match, match_id)
        assert match.status == "in_progress"
        assert match.game_started_at is not None

    assert submit(client, match_id, "red", 1).status_code == 302
    with app.app_context():
        match = db.session.get(Match, match_id)
        assert match.status == "in_progress", "one win is not a series"
        assert match.game_started_at is None, "the next game needs its own Start"
        first = MatchResult.query.filter_by(match_id=match_id, game_number=1).one()
        assert first.win_time_seconds == 42.5
        assert first.submitted_by == "Ref Ana"

    # Submit tapped again for game 1 (a retry after the wifi dropped) is
    # refused instead of being recorded as game 2.
    again = submit(client, match_id, "blue", 1)
    assert again.status_code == 409
    with app.app_context():
        assert MatchResult.query.filter_by(match_id=match_id).count() == 1

    # A tie wins nothing: the next game is the replay.
    assert submit(client, match_id, "tie", 2).status_code == 302
    with app.app_context():
        assert series_tally(db.session.get(Match, match_id)).winner is None

    assert submit(client, match_id, "red", 3).status_code == 302
    with app.app_context():
        match = db.session.get(Match, match_id)
        assert match.status == "complete"
        assert series_tally(match).winner == "red"

    # Locked: only the head ref can change it now.
    assert submit(client, match_id, "blue", 4).status_code == 409

    by_number = _rankings(app)
    assert by_number[101]["qual_points"] == 3
    assert (by_number[101]["match_wins"], by_number[101]["match_losses"]) == (2, 0)
    assert by_number[101]["match_diff"] == 2
    assert by_number[102]["qual_points"] == 0
    assert by_number[102]["match_diff"] == -2
    assert by_number[101]["rank"] < by_number[102]["rank"]


def test_unfinished_series_does_not_count_in_rankings(app, client, teams_and_match):
    submit(client, teams_and_match, "red", 1)
    by_number = _rankings(app)
    assert by_number[101]["qual_points"] == 0
    assert by_number[101]["series_played"] == 0


def test_result_screen_rejects_old_zone_names(app, client, teams_and_match):
    resp = submit(client, teams_and_match, "red", 1, red_final_zone="Center")
    assert resp.status_code == 400
    with app.app_context():
        assert MatchResult.query.count() == 0


def test_referee_pages_need_the_staff_passcode(app, client, teams_and_match):
    assert client.get("/referee/").status_code == 401
    assert client.post(f"/referee/start/{teams_and_match}").status_code == 401
    assert client.get("/referee/", headers=STAFF).status_code == 200


def test_each_arena_shows_its_own_series(app, client, teams_and_match):
    with app.app_context():
        team_103 = Team.query.filter_by(team_number=103).one()
        team_104 = Team.query.filter_by(team_number=104).one()
        db.session.add(Match(
            match_number=2, phase="qualification", division="High School", arena="Arena 2",
            scheduled_time=datetime(2026, 10, 24, 10, 0),
            red_team_id=team_103.id, blue_team_id=team_104.id,
        ))
        db.session.commit()

    one = client.get("/referee/arena/Arena_1", headers=STAFF).get_data(as_text=True)
    two = client.get("/referee/arena/Arena_2", headers=STAFF).get_data(as_text=True)
    assert "101 Team 101" in one and "103 Team 103" not in one
    assert "103 Team 103" in two and "101 Team 101" not in two
    assert "Start game 1" in one


def test_reload_mid_game_keeps_the_timer(app, client, teams_and_match):
    client.post(f"/referee/start/{teams_and_match}", headers=STAFF)
    with app.app_context():
        started = db.session.get(Match, teams_and_match).game_started_at

    # A second Start (double tap, or a retry after a dropped connection)
    # must not restart the clock.
    client.post(f"/referee/start/{teams_and_match}", headers=STAFF)
    page = client.get("/referee/arena/Arena_1", headers=STAFF).get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Match, teams_and_match).game_started_at == started
    assert 'id="timer"' in page and "data-elapsed=" in page
    assert "Start game" not in page


def test_pause_blocks_new_games_but_not_a_running_one(app, client, teams_and_match):
    match_id = teams_and_match
    client.post(f"/referee/start/{match_id}", headers=STAFF)
    client.post("/admin/pause", headers=HEAD)

    # The game already running can be finished.
    assert submit(client, match_id, "red", 1).status_code == 302

    # The next one cannot be started until the head ref resumes.
    client.post(f"/referee/start/{match_id}", headers=STAFF)
    with app.app_context():
        assert db.session.get(Match, match_id).game_started_at is None
    page = client.get("/referee/arena/Arena_1", headers=STAFF).get_data(as_text=True)
    assert "Matches are paused" in page

    client.post("/admin/resume", headers=HEAD)
    client.post(f"/referee/start/{match_id}", headers=STAFF)
    with app.app_context():
        assert db.session.get(Match, match_id).game_started_at is not None
        assert db.session.get(ScheduleState, 1).changed_by == "Head Ref Rio"


# --- the head ref's panel ----------------------------------------------------

def test_admin_needs_the_head_ref_passcode_and_a_name(app, client, teams_and_match):
    assert client.get("/admin/").status_code == 401
    assert client.get("/admin/", headers=staff_auth()).status_code == 401
    assert client.get("/admin/", headers=head_ref_auth(name="")).status_code == 401
    assert client.get("/admin/", headers=HEAD).status_code == 200


def test_admin_edit_writes_audit_with_who_and_rejects_unknown_zone(app, client, teams_and_match):
    match_id = teams_and_match
    submit(client, match_id, "red", 1)
    with app.app_context():
        game_id = MatchResult.query.filter_by(match_id=match_id).one().id

    bad = client.post(f"/admin/edit/{match_id}",
                      data={**game("red", 1), "game_id": game_id, "red_final_zone": "Moon"},
                      headers=HEAD)
    assert "final zone must be one of" in bad.get_data(as_text=True)

    ok = client.post(f"/admin/edit/{match_id}", data={**game("tie", 1), "game_id": game_id},
                     headers=HEAD)
    assert ok.status_code == 302
    with app.app_context():
        assert db.session.get(MatchResult, game_id).outcome == "tie"
        entry = AuditEntry.query.filter_by(match_id=match_id, field="game 1 outcome").one()
        assert (entry.old_value, entry.new_value) == ("red", "tie")
        assert entry.changed_by == "Head Ref Rio"


def test_admin_edit_can_undecide_a_series(app, client, teams_and_match):
    match_id = teams_and_match
    submit(client, match_id, "red", 1)
    submit(client, match_id, "red", 2)
    with app.app_context():
        assert db.session.get(Match, match_id).status == "complete"
        game_two = MatchResult.query.filter_by(match_id=match_id, game_number=2).one().id

    client.post(f"/admin/edit/{match_id}", data={**game("blue", 2), "game_id": game_two},
                headers=HEAD)
    with app.app_context():
        match = db.session.get(Match, match_id)
        assert match.status == "in_progress"
        assert (series_tally(match).red_wins, series_tally(match).blue_wins) == (1, 1)
    assert _rankings(app)[101]["qual_points"] == 0


def test_admin_can_enter_a_missing_game(app, client, teams_and_match):
    match_id = teams_and_match
    resp = client.post(f"/admin/edit/{match_id}", data=game("red", 1), headers=HEAD)
    assert resp.status_code == 302
    with app.app_context():
        result = MatchResult.query.filter_by(match_id=match_id).one()
        assert result.submitted_by == "Head Ref Rio"
        assert result.game_number == 1
        assert db.session.get(Match, match_id).status == "in_progress"
        assert AuditEntry.query.filter_by(match_id=match_id).count() == 4


def test_voiding_a_game_orders_a_replay(app, client, teams_and_match):
    match_id = teams_and_match
    submit(client, match_id, "red", 1)
    submit(client, match_id, "red", 2)

    # Dashboard shortcut: replay the latest counted game.
    assert client.post("/admin/replay", data={"original_match_id": match_id}, headers=HEAD).status_code == 302
    with app.app_context():
        match = db.session.get(Match, match_id)
        assert match.status == "in_progress"
        assert series_tally(match).red_wins == 1
        assert MatchResult.query.filter_by(match_id=match_id, game_number=2).one().voided
        assert AuditEntry.query.filter_by(match_id=match_id, field="game 2 voided").count() == 1
    assert _rankings(app)[101]["qual_points"] == 0

    # The replay is game 3; game 2 keeps its number in the record.
    page = client.get("/referee/arena/Arena_1", headers=STAFF).get_data(as_text=True)
    assert "game 3" in page
    assert submit(client, match_id, "blue", 3).status_code == 302
    assert submit(client, match_id, "red", 4).status_code == 302
    by_number = _rankings(app)
    assert by_number[101]["qual_points"] == 3
    assert (by_number[101]["match_wins"], by_number[101]["match_losses"]) == (2, 1)


def test_full_export_has_every_csv_and_team_numbers(app, client, teams_and_match):
    submit(client, teams_and_match, "red", 1)
    resp = client.get("/admin/export/all.zip", headers=HEAD)
    assert resp.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(resp.data))
    assert sorted(archive.namelist()) == sorted(
        ["teams.csv", "inspections.csv", "matches.csv", "games.csv", "rankings.csv", "audit.csv"]
    )
    games_csv = archive.read("games.csv").decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(games_csv)))
    assert rows[0]["red_team_number"] == "101"
    assert rows[0]["outcome"] == "red"
    assert client.get("/admin/export/all.zip").status_code == 401


# --- displays ------------------------------------------------------------------

def test_display_and_pit_show_the_running_series(app, client, teams_and_match):
    client.post(f"/referee/start/{teams_and_match}", headers=STAFF)
    submit(client, teams_and_match, "red", 1)

    display = client.get("/rankings/display/High_School").get_data(as_text=True)
    assert "Arena 1, match 1" in display and "game 2" in display
    assert 'class="wins">1<' in display and 'class="wins">0<' in display

    pit = client.post("/rankings/pit", data={"team_number": "102"}).get_data(as_text=True)
    assert "Now, Arena 1" in pit


# --- the scheduler ---------------------------------------------------------------

def test_regenerate_refused_once_matches_are_played(app, client, teams_and_match):
    match_id = teams_and_match
    submit(client, match_id, "red", 1)

    resp = client.post("/schedule/api/generate", json={"use_advanced": True, "clear_existing": True},
                       headers=HEAD)
    assert resp.status_code == 409
    assert "already been played" in resp.get_json()["error"]

    with app.app_context():
        # Nothing was deleted and the result still belongs to the same pairing.
        assert db.session.get(Match, match_id) is not None
        assert MatchResult.query.filter_by(match_id=match_id).count() == 1


def test_regenerate_allowed_before_anything_is_played(app, client, teams_and_match):
    # Four teams on two arenas can't avoid back-to-back matches, and the
    # generator rightly refuses that; ten can.
    with app.app_context():
        _add_teams(range(105, 111))
        db.session.commit()

    resp = client.post("/schedule/api/generate", json={"use_advanced": True, "clear_existing": True},
                       headers=HEAD)
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["series_per_team"] == [6], "manual T3: at least six series each"
    assert body["matches"][0]["time"] == "10:00 AM"
    with app.app_context():
        assert Match.query.filter_by(phase="qualification").count() == body["matches_generated"]
        first = Match.query.order_by(Match.scheduled_time).first()
        assert first.scheduled_time == datetime(2026, 10, 24, 10, 0)


def test_generate_only_checked_in_teams_on_more_arenas(app, client, teams_and_match):
    with app.app_context():
        teams = _add_teams(range(105, 121))
        for team in teams:
            team.checked_in = True
        db.session.commit()

    resp = client.post("/schedule/api/generate", json={
        "checked_in_only": True, "arena_count": 3, "start_time": "2026-10-24T09:30",
    }, headers=HEAD)
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["teams_scheduled"] == 16
    assert body["arenas"] == ["Arena 1", "Arena 2", "Arena 3"]
    with app.app_context():
        unchecked = {t.id for t in Team.query.filter_by(checked_in=False)}
        for match in Match.query.filter_by(phase="qualification"):
            assert match.red_team_id not in unchecked and match.blue_team_id not in unchecked


def test_a_refused_schedule_keeps_the_old_one(app, client, teams_and_match):
    # Four teams on two arenas cannot avoid back-to-back series.
    resp = client.post("/schedule/api/generate", json={"use_advanced": True}, headers=HEAD)
    assert resp.status_code == 400
    with app.app_context():
        assert db.session.get(Match, teams_and_match) is not None


def test_schedule_generate_needs_csrf_header_when_csrf_is_on(app_factory):
    app = app_factory(WTF_CSRF_ENABLED=True)
    resp = app.test_client().post("/schedule/api/generate", json={"use_advanced": True}, headers=HEAD)
    assert resp.status_code == 400


def test_schedule_generate_needs_the_head_ref(app, client, teams_and_match):
    assert client.post("/schedule/api/generate", json={}, headers=STAFF).status_code == 401


def test_landing_page_links_into_every_tool(app, client, teams_and_match):
    # The landing page does not extend base.html, so this bar is the only way
    # from the front door into the tools. Every link must land on a real page.
    page = client.get("/").get_data(as_text=True)
    bar = page.split('aria-label="Tournament"', 1)[1].split("</nav>", 1)[0]
    links = [chunk.split('"', 1)[0] for chunk in bar.split('href="')[1:]]
    assert links == [
        "/schedule/", "/rankings/High_School", "/rankings/display/High_School",
        "/bracket/High_School", "/rankings/pit", "/checkin/", "/referee/", "/admin/",
    ]
    for link in links:
        headers = HEAD if link.startswith("/admin") else STAFF
        assert client.get(link, headers=headers).status_code == 200, link


def test_landing_page_hides_the_tools_while_registration_only(tmp_path):
    page = _build(tmp_path, REGISTRATION_ONLY=True).test_client().get("/").get_data(as_text=True)
    assert 'aria-label="Tournament"' not in page
    assert "/referee/" not in page
