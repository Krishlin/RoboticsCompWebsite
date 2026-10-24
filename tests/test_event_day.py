"""Things that go wrong on the day: the event runs late, teams don't come, a
volunteer taps the wrong row, and a public page keyed by team number."""

from datetime import datetime, timedelta

import pytest

from app.db import db
from app.models import Match, MatchResult, ScheduleState, Team, utcnow
from tests.conftest import _build, head_ref_auth, staff_auth

STAFF = staff_auth(name="Ref Ana")
HEAD = head_ref_auth()


@pytest.fixture
def app(tmp_path):
    return _build(tmp_path, REGISTRATION_ONLY=False)


def _team(number, checked_in=True):
    team = Team(
        team_number=number,
        name=f"Team {number}",
        affiliation="Test School",
        division="High School",
        students="Student A",
        adult_name="Coach",
        adult_email=f"coach{number}@example.org",
        checked_in=checked_in,
    )
    db.session.add(team)
    db.session.flush()
    return team


@pytest.fixture
def schedule(app):
    """Six series on two arenas from 10:00, every 15 minutes, plus one bracket
    series with no time. Match 1 is finished and match 2 is being played."""
    with app.app_context():
        teams = [_team(n) for n in range(100, 108)]
        ids = {}
        for number in range(1, 7):
            slot = (number - 1) // 2
            red, blue = teams[(number * 2) % 8], teams[(number * 2 + 1) % 8]
            match = Match(
                match_number=number,
                phase="qualification",
                division="High School",
                arena=f"Arena {1 + (number - 1) % 2}",
                scheduled_time=_clock(10, 0) + timedelta(minutes=15 * slot),
                red_team_id=red.id,
                blue_team_id=blue.id,
            )
            db.session.add(match)
            db.session.flush()
            ids[number] = match.id
        bracket = Match(
            match_number=7,
            phase="elimination",
            division="High School",
            arena="Arena 1",
            scheduled_time=None,
            red_team_id=teams[0].id,
            blue_team_id=teams[1].id,
            bracket_side="W",
            bracket_round=1,
            bracket_slot=1,
        )
        db.session.add(bracket)

        first = db.session.get(Match, ids[1])
        for game_number in (1, 2):
            db.session.add(
                MatchResult(
                    match_id=first.id,
                    game_number=game_number,
                    outcome="red",
                    red_final_zone="Plateau",
                    blue_final_zone="Ring-out",
                    submitted_by="ref",
                )
            )
        first.status = "complete"
        running = db.session.get(Match, ids[2])
        running.status = "in_progress"
        running.game_started_at = utcnow()
        db.session.commit()
        return ids


def _times(app):
    with app.app_context():
        return {m.match_number: m.scheduled_time for m in Match.query}


def _clock(hour, minute):
    return datetime(2026, 10, 24, hour, minute)


# --- shifting the schedule ---------------------------------------------------


def test_a_delay_moves_every_match_that_has_not_started(app, schedule):
    client = app.test_client()
    before = _times(app)
    response = client.post("/admin/shift-schedule", data={"minutes": "20"}, headers=HEAD)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/")

    after = _times(app)
    assert after[1] == before[1], "a finished series keeps its time"
    assert after[2] == before[2], "a running series keeps its time"
    for number in (3, 4, 5, 6):
        assert (after[number] - before[number]).total_seconds() == 20 * 60, number
    assert after[7] is None, "a bracket series has no time to move"

    page = client.get("/admin/", headers=HEAD).get_data(as_text=True)
    assert "Moved 4 matches 20 minutes later. Match 3 is now at 10:35 AM." in page


def test_the_public_schedule_shows_the_new_times(app, schedule):
    client = app.test_client()
    assert "10:15 AM" in client.get("/schedule/arena/Arena_1").get_data(as_text=True)
    client.post("/admin/shift-schedule", data={"minutes": "10"}, headers=HEAD)
    arena = client.get("/schedule/arena/Arena_1").get_data(as_text=True)
    assert "10:25 AM" in arena
    assert "10:00 AM" in arena, "match 1 was played at 10:00 and stays there"


def test_setting_when_the_next_match_starts_moves_everything_after_it(app, schedule):
    client = app.test_client()
    client.post("/admin/shift-schedule", data={"next_start": "10:50"}, headers=HEAD)
    after = _times(app)
    assert after[3] == _clock(10, 50)
    assert after[4] == _clock(10, 50)
    assert after[5] == _clock(11, 5)
    assert after[6] == _clock(11, 5)


def test_a_negative_shift_pulls_the_schedule_earlier(app, schedule):
    client = app.test_client()
    client.post("/admin/shift-schedule", data={"minutes": "-5"}, headers=HEAD)
    assert _times(app)[3] == _clock(10, 10)


@pytest.mark.parametrize(
    "form, message",
    [
        ({"minutes": "ten"}, "Enter a whole number of minutes"),
        ({"minutes": ""}, "Enter a whole number of minutes"),
        ({"minutes": "0"}, "Nothing moved"),
        ({"minutes": "600"}, "more than the 240-minute limit"),
        ({"minutes": "99999999999999999"}, "limit for one shift"),
        ({"next_start": "25:99"}, "Enter the time like 10:45"),
        ({"next_start": "10:15"}, "Nothing moved"),
    ],
)
def test_a_bad_shift_changes_nothing_and_says_why(app, schedule, form, message):
    client = app.test_client()
    before = _times(app)
    client.post("/admin/shift-schedule", data=form, headers=HEAD)
    assert _times(app) == before
    page = client.get("/admin/", headers=HEAD).get_data(as_text=True)
    assert message in page


def test_shifting_needs_the_head_ref(app, schedule):
    client = app.test_client()
    before = _times(app)
    assert client.post("/admin/shift-schedule", data={"minutes": "10"}).status_code == 401
    assert (
        client.post("/admin/shift-schedule", data={"minutes": "10"}, headers=STAFF).status_code
        == 401
    )
    assert _times(app) == before


def test_shifting_needs_a_csrf_token_when_csrf_is_on(tmp_path):
    app = _build(tmp_path, REGISTRATION_ONLY=False, WTF_CSRF_ENABLED=True)
    assert (
        app.test_client()
        .post("/admin/shift-schedule", data={"minutes": "10"}, headers=HEAD)
        .status_code
        == 400
    )


def test_the_dashboard_offers_the_pause_length_as_the_delay(app, schedule):
    with app.app_context():
        db.session.add(
            ScheduleState(
                id=1,
                is_paused=True,
                changed_by="Head Ref Rio",
                changed_at=utcnow() - timedelta(minutes=12, seconds=30),
            )
        )
        db.session.commit()
    page = app.test_client().get("/admin/", headers=HEAD).get_data(as_text=True)
    assert "Next to start: <strong>match 3</strong>" in page
    assert "paused for 12 minutes" in page
    assert 'name="minutes"' in page and 'value="12"' in page


def test_nothing_to_shift_is_said_plainly(app):
    client = app.test_client()
    page = client.get("/admin/", headers=HEAD).get_data(as_text=True)
    assert "No upcoming match has a time to move" in page
    client.post("/admin/shift-schedule", data={"minutes": "10"}, headers=HEAD)
    assert "no upcoming matches" in client.get("/admin/", headers=HEAD).get_data(as_text=True)


# --- teams that don't come ---------------------------------------------------


def test_a_team_left_out_of_the_schedule_is_not_ranked_or_seeded(app):
    """A no-show sat at 0 points and +0, above a team that came and lost 0-2,
    and the bracket seeds the top of that list."""
    from app.bracket.service import build_bracket
    from app.models import BracketConfig
    from app.rankings.logic import get_division_rankings

    with app.app_context():
        here = [_team(n) for n in (100, 101, 102)]
        _team(103, checked_in=False)
        for number, (red, blue) in enumerate(((0, 1), (1, 2), (0, 2)), start=1):
            match = Match(
                match_number=number,
                phase="qualification",
                division="High School",
                arena="Arena 1",
                scheduled_time=_clock(10, number),
                red_team_id=here[red].id,
                blue_team_id=here[blue].id,
                status="complete",
            )
            db.session.add(match)
            db.session.flush()
            for game_number in (1, 2):
                db.session.add(
                    MatchResult(
                        match_id=match.id,
                        game_number=game_number,
                        outcome="red",
                        red_final_zone="Plateau",
                        blue_final_zone="Ring-out",
                        submitted_by="ref",
                    )
                )
        db.session.commit()

        standings = [row["team_number"] for row in get_division_rankings("High School")]
        assert standings == [100, 101, 102]

        build_bracket("High School", "single", 3, "Head Ref Rio")
        seeds = BracketConfig.query.one().seeds.splitlines()
        no_show = Team.query.filter_by(team_number=103).one()
        assert str(no_show.id) not in seeds


def test_before_a_schedule_exists_every_registered_team_is_listed(app):
    from app.rankings.logic import get_division_rankings

    with app.app_context():
        _team(100)
        _team(101, checked_in=False)
        db.session.commit()
        assert len(get_division_rankings("High School")) == 2


def test_a_mistaken_check_in_can_be_undone(app):
    client = app.test_client()
    with app.app_context():
        team = _team(100)
        db.session.commit()
        team_id = team.id

    page = client.get("/checkin/", headers=STAFF).get_data(as_text=True)
    assert "Undo" in page
    assert "Test School" in page, "the school helps the desk find the right row"

    assert client.post(f"/checkin/{team_id}/undo").status_code == 401
    response = client.post(f"/checkin/{team_id}/undo", headers=STAFF)
    assert response.status_code == 302
    with app.app_context():
        assert not db.session.get(Team, team_id).checked_in
    assert "no longer checked in" in client.get("/checkin/", headers=STAFF).get_data(as_text=True)

    assert client.post(f"/checkin/{team_id}/check-in", headers=STAFF).status_code == 302
    with app.app_context():
        assert db.session.get(Team, team_id).checked_in
    assert client.post("/checkin/9999/undo", headers=STAFF).status_code == 404


# --- pages that name a team's people --------------------------------------------


def test_a_stranger_cannot_read_a_teams_details_by_number(app):
    with app.app_context():
        _team(100)
        db.session.commit()
    stranger = app.test_client()
    page = stranger.get("/register/confirmation/100")
    assert page.status_code == 404
    assert "coach100@example.org" not in page.get_data(as_text=True)


def test_the_team_that_just_registered_still_sees_its_confirmation(app):
    client = app.test_client()
    response = client.post(
        "/register/",
        data={
            "team_name": "Fresh Team",
            "affiliation": "Some School",
            "student_1": "Ann Example",
            "adult_name": "Coach Example",
            "adult_email": "fresh@example.org",
            "adult_phone": "555-0100",
        },
    )
    assert response.status_code == 302
    location = response.headers["Location"]
    assert location.endswith("/register/confirmation/100")
    page = client.get(location)
    assert page.status_code == 200
    assert "fresh@example.org" in page.get_data(as_text=True)
    # And only that number: the same browser can't walk to the next team.
    with app.app_context():
        _team(101)
        db.session.commit()
    assert client.get("/register/confirmation/101").status_code == 404


def test_pit_lookup_for_a_bracket_series_does_not_say_about_tbd(app, schedule):
    with app.app_context():
        # Finish everything but the bracket series, which has no time.
        Match.query.filter(Match.phase == "qualification").update({"status": "complete"})
        db.session.commit()
    page = (
        app.test_client().post("/rankings/pit", data={"team_number": "100"}).get_data(as_text=True)
    )
    assert "about TBD" not in page
    assert "Arena 1, when called" in page
