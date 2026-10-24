"""The seed script: the real teams and nothing else by default, and with
--play a legal schedule and a mix of finished and unplayed series to develop
against. tests/fixtures/roster.csv stands in for the registration sheet."""

from pathlib import Path

from app.db import db
from app.match_state import series_tally
from app.models import Match, MatchResult, Team
from app.rankings.logic import get_division_rankings
from app.scheduler.generator import validate_schedule
from app.series import VALID_ZONES
from seed import seed as seed_module
from seed.seed import seed_matches, seed_teams
from tests.conftest import _build

ROSTER = str(Path(__file__).parent / "fixtures" / "roster.csv")


def test_seed_loads_the_roster_and_nothing_else(tmp_path, monkeypatch):
    dbfile = tmp_path / "seed.db"
    monkeypatch.setattr(
        seed_module, "create_app",
        lambda: _build(tmp_path, REGISTRATION_ONLY=False, SQLALCHEMY_DATABASE_URI=f"sqlite:///{dbfile.as_posix()}"),
    )
    assert seed_module.main([ROSTER]) == 0
    # Run twice: the second run empties the first one's teams before loading.
    assert seed_module.main([ROSTER]) == 0

    app = _build(tmp_path, SQLALCHEMY_DATABASE_URI=f"sqlite:///{dbfile.as_posix()}")
    with app.app_context():
        assert Team.query.count() == 11
        assert Match.query.count() == 0
        assert MatchResult.query.count() == 0
        db.session.remove()


def test_a_bad_roster_leaves_the_database_alone(tmp_path, monkeypatch):
    dbfile = tmp_path / "seed.db"
    monkeypatch.setattr(
        seed_module, "create_app",
        lambda: _build(tmp_path, SQLALCHEMY_DATABASE_URI=f"sqlite:///{dbfile.as_posix()}"),
    )
    assert seed_module.main([ROSTER]) == 0
    assert seed_module.main(["no/such/roster.csv"]) == 1

    app = _build(tmp_path, SQLALCHEMY_DATABASE_URI=f"sqlite:///{dbfile.as_posix()}")
    with app.app_context():
        assert Team.query.count() == 11
        db.session.remove()


def test_play_builds_a_playable_event(tmp_path):
    app = _build(tmp_path, REGISTRATION_ONLY=False)
    with app.app_context():
        assert seed_teams(ROSTER) == 11
        series, games = seed_matches()

        assert Team.query.count() == 11
        assert series == Match.query.count() == 33  # 11 teams x 6 series / 2
        assert games == MatchResult.query.count()

        numbers = {t.id: t.team_number for t in Team.query}
        schedule = [
            {
                "match_number": m.match_number, "division": m.division,
                "scheduled_time": m.scheduled_time.strftime("%Y-%m-%d %H:%M"),
                "red_team_number": numbers[m.red_team_id],
                "blue_team_number": numbers[m.blue_team_id],
            }
            for m in Match.query
        ]
        assert validate_schedule(schedule) == {}

        complete = Match.query.filter_by(status="complete").all()
        assert 0 < len(complete) < 33
        assert all(series_tally(m).winner for m in complete)
        assert {g.red_final_zone for g in MatchResult.query} <= set(VALID_ZONES)

        standings = get_division_rankings("High School")
        assert len(standings) == 11
        assert standings[0]["qual_points"] > 0
        db.session.remove()
