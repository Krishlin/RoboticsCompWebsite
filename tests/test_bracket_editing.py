"""Today's format: a round robin (everyone plays everyone once, best of three),
then a bracket the head ref can edit: who is in each seed, who wins a series,
and how many teams advance."""

from collections import Counter
from datetime import datetime, timedelta
from itertools import combinations
from pathlib import Path

import pytest

from app.db import db
from app.match_state import series_tally
from app.models import AuditEntry, BracketConfig, Match, MatchResult, Team
from app.rankings.logic import get_division_rankings
from seed.schedule import premake_schedule
from tests.conftest import _build, head_ref_auth, staff_auth

HEAD = head_ref_auth()
STAFF = staff_auth(name="Ref Ana")
ROSTER = str(Path(__file__).parent / "fixtures" / "roster.csv")


@pytest.fixture
def app(tmp_path):
    return _build(tmp_path, REGISTRATION_ONLY=False)


def _team(number):
    team = Team(
        team_number=number,
        name=f"Team {number}",
        affiliation="Test School",
        division="High School",
        students="Student A",
        adult_name="Coach",
        adult_email=f"coach{number}@example.org",
        checked_in=True,
    )
    db.session.add(team)
    db.session.flush()
    return team


def _win(match, side, games=2):
    for number in range(1, games + 1):
        db.session.add(
            MatchResult(
                match_id=match.id,
                game_number=number,
                outcome=side,
                red_final_zone="Plateau" if side == "red" else "Ring-out",
                blue_final_zone="Plateau" if side == "blue" else "Ring-out",
                submitted_by="ref",
            )
        )
    match.status = "complete"


@pytest.fixture
def round_robin_played(app):
    """Ten teams, a full round robin, every series played: the lower number
    always wins, so the standings are 100, 101, ... 109."""
    with app.app_context():
        teams = [_team(n) for n in range(100, 110)]
        start = datetime(2026, 10, 24, 10, 0)
        for number, (a, b) in enumerate(combinations(teams, 2), start=1):
            match = Match(
                match_number=number,
                phase="qualification",
                division="High School",
                arena="Arena 1",
                scheduled_time=start + timedelta(minutes=10 * number),
                red_team_id=a.id,
                blue_team_id=b.id,
            )
            db.session.add(match)
            db.session.flush()
            _win(match, "red")
        db.session.commit()


def _ids():
    return {t.team_number: t.id for t in Team.query}


def _seeds():
    numbers = {t.id: t.team_number for t in Team.query}
    return [numbers[int(i)] for i in BracketConfig.query.one().seeds.splitlines()]


def _quarterfinal_pairs():
    numbers = {t.id: t.team_number for t in Team.query}
    rows = Match.query.filter_by(phase="elimination", bracket_round=1).all()
    return {frozenset((numbers[m.red_team_id], numbers[m.blue_team_id])) for m in rows}


def _build_bracket(client, size="8", **extra):
    return client.post(
        "/bracket/High_School/build",
        headers=HEAD,
        data={"format": "single", "size": size, **extra},
    )


# --- the round robin ------------------------------------------------------------


def test_the_generator_button_can_schedule_a_round_robin(app):
    with app.app_context():
        for number in range(100, 107):
            _team(number)
        db.session.commit()
    client = app.test_client()
    response = client.post("/schedule/api/generate", headers=HEAD, json={"round_robin": True})
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["series_per_team"] == [6]  # 7 teams: everyone plays the other 6
    assert body["matches_generated"] == 21
    with app.app_context():
        numbers = {t.id: t.team_number for t in Team.query}
        pairs = Counter(
            frozenset((numbers[m.red_team_id], numbers[m.blue_team_id])) for m in Match.query
        )
        assert len(pairs) == 21 and set(pairs.values()) == {1}, "every pair exactly once"

    page = client.get("/schedule/admin", headers=HEAD).get_data(as_text=True)
    assert 'id="round-robin" checked' in page


def test_the_premade_round_robin_for_eleven_teams(app):
    with app.app_context():
        _, teams, schedule = premake_schedule(
            ROSTER, [], start=datetime(2026, 10, 24, 10, 0), round_minutes=10, round_robin=True
        )
        assert len(teams) == 11
        assert len(schedule) == Match.query.count() == 55
        pairs = Counter(frozenset((m["red_team_number"], m["blue_team_number"])) for m in schedule)
        assert len(pairs) == 55 and set(pairs.values()) == {1}
        times = sorted({m["scheduled_time"] for m in schedule})
        assert times[0] == "2026-10-24 10:00"
        assert len(times) == 28, "two arenas: 28 rounds, the fewest 55 series allow"


# --- building ---------------------------------------------------------------------


def test_the_bracket_can_be_built_before_qualification_finishes_if_the_head_ref_says_so(app):
    with app.app_context():
        teams = [_team(n) for n in range(100, 104)]
        played = Match(
            match_number=1,
            phase="qualification",
            division="High School",
            arena="Arena 1",
            red_team_id=teams[0].id,
            blue_team_id=teams[1].id,
        )
        unplayed = Match(
            match_number=2,
            phase="qualification",
            division="High School",
            arena="Arena 1",
            red_team_id=teams[2].id,
            blue_team_id=teams[3].id,
        )
        db.session.add_all([played, unplayed])
        db.session.flush()
        _win(played, "red")
        db.session.commit()
    client = app.test_client()

    refused = _build_bracket(client, size="4")
    assert refused.status_code == 302
    with app.app_context():
        assert BracketConfig.query.count() == 0
    assert "not finished" in client.get("/bracket/High_School/manage", headers=HEAD).get_data(
        as_text=True
    )

    _build_bracket(client, size="4", allow_unfinished="1")
    with app.app_context():
        assert len(_seeds()) == 4
        assert _seeds()[0] == 100


# --- who is in each seed ------------------------------------------------------------


def test_the_head_ref_swaps_two_seeds(app, round_robin_played):
    client = app.test_client()
    _build_bracket(client)
    with app.app_context():
        assert _seeds() == [100, 101, 102, 103, 104, 105, 106, 107]
        team_106 = _ids()[106]

    response = client.post(
        "/bracket/High_School/seed", headers=HEAD, data={"seed": "3", "team_id": str(team_106)}
    )
    assert response.status_code == 302
    with app.app_context():
        assert _seeds() == [100, 101, 106, 103, 104, 105, 102, 107]
        assert _quarterfinal_pairs() == {
            frozenset(p) for p in ((100, 107), (103, 104), (101, 102), (106, 105))
        }
    page = client.get("/bracket/High_School/manage", headers=HEAD).get_data(as_text=True)
    assert "Seed 3 is now 106 Team 106." in page


def test_a_team_that_was_cut_can_be_put_into_the_bracket(app, round_robin_played):
    client = app.test_client()
    _build_bracket(client)
    with app.app_context():
        team_109 = _ids()[109]
    client.post(
        "/bracket/High_School/seed", headers=HEAD, data={"seed": "8", "team_id": str(team_109)}
    )
    with app.app_context():
        assert _seeds()[-1] == 109
        assert 107 not in _seeds()
        assert frozenset((100, 109)) in _quarterfinal_pairs()


def test_a_seed_whose_series_was_played_cannot_change(app, round_robin_played):
    client = app.test_client()
    _build_bracket(client)
    with app.app_context():
        one_v_eight = Match.query.filter_by(
            phase="elimination", bracket_slot=1, bracket_round=1
        ).one()
        db.session.add(
            MatchResult(
                match_id=one_v_eight.id,
                game_number=1,
                outcome="red",
                red_final_zone="Plateau",
                blue_final_zone="Ring-out",
                submitted_by="ref",
            )
        )
        one_v_eight.status = "in_progress"
        db.session.commit()
        team_109 = _ids()[109]
        before = _seeds()

    client.post(
        "/bracket/High_School/seed", headers=HEAD, data={"seed": "8", "team_id": str(team_109)}
    )
    with app.app_context():
        assert _seeds() == before
    page = client.get("/bracket/High_School/manage", headers=HEAD).get_data(as_text=True)
    assert "Not changed" in page


def test_editing_the_bracket_needs_the_head_ref(app, round_robin_played):
    client = app.test_client()
    _build_bracket(client)
    with app.app_context():
        team_109 = _ids()[109]
        before = _seeds()
    for headers in ({}, STAFF):
        assert (
            client.post(
                "/bracket/High_School/seed",
                headers=headers,
                data={"seed": "8", "team_id": str(team_109)},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/bracket/High_School/rebuild",
                headers=headers,
                data={"format": "single", "size": "4"},
            ).status_code
            == 401
        )
    with app.app_context():
        assert _seeds() == before


# --- who wins ---------------------------------------------------------------------------


def test_awarding_a_bracket_series_moves_the_winner_on(app, round_robin_played):
    client = app.test_client()
    _build_bracket(client, size="4")  # 100v103, 101v102
    with app.app_context():
        first = Match.query.filter_by(phase="elimination", bracket_round=1, bracket_slot=1).one()
        second = Match.query.filter_by(phase="elimination", bracket_round=1, bracket_slot=2).one()
        first_id, second_id = first.id, second.id
        # 100 is the better seed, so it is blue (the lower seed plays red).
        blue_of_first = db.session.get(Team, first.blue_team_id).team_number

    # A no-show: the head ref gives both semifinals to red without a game.
    for match_id in (first_id, second_id):
        response = client.post(f"/admin/award/{match_id}", headers=HEAD, data={"side": "red"})
        assert response.status_code == 302

    with app.app_context():
        first = db.session.get(Match, first_id)
        tally = series_tally(first)
        assert (tally.red_wins, tally.blue_wins, tally.winner) == (2, 0, "red")
        assert first.status == "complete"
        games = MatchResult.query.filter_by(match_id=first_id).all()
        assert all("(awarded)" in g.submitted_by for g in games)
        final = Match.query.filter_by(phase="elimination", bracket_round=2).one()
        assert {final.red_team_id, final.blue_team_id} == {
            first.red_team_id,
            db.session.get(Match, second_id).red_team_id,
        }
        log = {e.field for e in AuditEntry.query.filter_by(match_id=first_id)}
        assert "series awarded to" in log
        assert blue_of_first == 100


def test_awarding_overrides_a_result_and_keeps_the_old_games_as_voided(app, round_robin_played):
    client = app.test_client()
    _build_bracket(client, size="4")
    with app.app_context():
        match = Match.query.filter_by(phase="elimination", bracket_round=1, bracket_slot=1).one()
        _win(match, "blue")  # blue 2-0
        db.session.commit()
        match_id = match.id

    client.post(f"/admin/award/{match_id}", headers=HEAD, data={"side": "red"})
    with app.app_context():
        games = (
            MatchResult.query.filter_by(match_id=match_id).order_by(MatchResult.game_number).all()
        )
        assert [(g.outcome, g.voided) for g in games] == [
            ("blue", True),
            ("blue", True),
            ("red", False),
            ("red", False),
        ]
        assert series_tally(db.session.get(Match, match_id)).winner == "red"


def test_awarding_is_refused_when_a_later_series_already_used_the_old_winner(
    app, round_robin_played
):
    client = app.test_client()
    _build_bracket(client, size="4")
    with app.app_context():
        semis = (
            Match.query.filter_by(phase="elimination", bracket_round=1)
            .order_by(Match.bracket_slot)
            .all()
        )
        for semi in semis:
            _win(semi, "blue")
        db.session.commit()
        semi_id = semis[0].id
    client.get("/bracket/High_School/manage", headers=HEAD)  # the bracket catches up
    with app.app_context():
        final = Match.query.filter_by(phase="elimination", bracket_round=2).one()
        db.session.add(
            MatchResult(
                match_id=final.id,
                game_number=1,
                outcome="red",
                red_final_zone="Plateau",
                blue_final_zone="Ring-out",
                submitted_by="ref",
            )
        )
        final.status = "in_progress"
        db.session.commit()

    response = client.post(f"/admin/award/{semi_id}", headers=HEAD, data={"side": "red"})
    assert response.status_code == 409
    assert "Not saved" in response.get_data(as_text=True)
    with app.app_context():
        assert series_tally(db.session.get(Match, semi_id)).winner == "blue"


def test_a_forfeit_in_qualification_counts_as_a_two_nil_win(app):
    with app.app_context():
        a, b = _team(100), _team(101)
        match = Match(
            match_number=1,
            phase="qualification",
            division="High School",
            arena="Arena 1",
            red_team_id=a.id,
            blue_team_id=b.id,
        )
        db.session.add(match)
        db.session.commit()
        match_id = match.id
    app.test_client().post(f"/admin/award/{match_id}", headers=HEAD, data={"side": "blue"})
    with app.app_context():
        standings = {row["team_number"]: row for row in get_division_rankings("High School")}
        assert standings[101]["qual_points"] == 3
        assert standings[101]["match_diff"] == 2
        assert standings[100]["match_diff"] == -2


def test_award_needs_the_head_ref_and_a_side(app):
    with app.app_context():
        a, b = _team(100), _team(101)
        match = Match(
            match_number=1,
            phase="qualification",
            division="High School",
            arena="Arena 1",
            red_team_id=a.id,
            blue_team_id=b.id,
        )
        db.session.add(match)
        db.session.commit()
        match_id = match.id
    client = app.test_client()
    assert client.post(f"/admin/award/{match_id}", data={"side": "red"}).status_code == 401
    assert (
        client.post(f"/admin/award/{match_id}", headers=STAFF, data={"side": "red"}).status_code
        == 401
    )
    assert (
        client.post(f"/admin/award/{match_id}", headers=HEAD, data={"side": "green"}).status_code
        == 400
    )
    assert client.post("/admin/award/9999", headers=HEAD, data={"side": "red"}).status_code == 404
    with app.app_context():
        assert MatchResult.query.count() == 0


# --- how many teams -----------------------------------------------------------------------


def test_the_number_of_teams_can_change_until_a_bracket_game_is_played(app, round_robin_played):
    client = app.test_client()
    _build_bracket(client)
    client.post(
        "/bracket/High_School/rebuild", headers=HEAD, data={"format": "single", "size": "6"}
    )
    with app.app_context():
        assert _seeds() == [100, 101, 102, 103, 104, 105]
        # Six teams: seeds 1 and 2 have byes, so two first-round series.
        assert Match.query.filter_by(phase="elimination").count() == 2
        first = Match.query.filter_by(phase="elimination").first()
        _win(first, "red")
        db.session.commit()

    client.post(
        "/bracket/High_School/rebuild", headers=HEAD, data={"format": "single", "size": "8"}
    )
    with app.app_context():
        assert len(_seeds()) == 6, "refused once a bracket game is played"
    page = client.get("/bracket/High_School/manage", headers=HEAD).get_data(as_text=True)
    assert "can&#39;t change" in page or "can't change" in page


def test_a_refused_rebuild_leaves_the_bracket_as_it_was(app, round_robin_played):
    client = app.test_client()
    _build_bracket(client)
    client.post(
        "/bracket/High_School/rebuild", headers=HEAD, data={"format": "single", "size": "99"}
    )
    with app.app_context():
        assert len(_seeds()) == 8
        assert Match.query.filter_by(phase="elimination").count() == 4
