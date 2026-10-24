"""Pre-making the qualification schedule from the registration sheet
(seed/schedule.py). tests/fixtures/roster.csv stands in for the sheet: 11
made-up teams, one of whom isn't coming."""

from collections import Counter
from itertools import pairwise
from datetime import datetime
from pathlib import Path

import pytest

from app.db import db
from app.models import Match, MatchResult, Team
from app.rankings.logic import get_division_rankings
from app.scheduler.generator import validate_schedule
from seed import schedule as premake
from seed.schedule import ScheduleError, premake_schedule
from tests.conftest import _build

ROSTER = str(Path(__file__).parent / "fixtures" / "roster.csv")
START = datetime(2026, 10, 24, 10, 0)


@pytest.fixture
def app(tmp_path):
    return _build(tmp_path, REGISTRATION_ONLY=False)


def _pairings():
    numbers = {t.id: t.team_number for t in Team.query}
    return [
        (m.match_number, m.arena, m.scheduled_time, numbers[m.red_team_id], numbers[m.blue_team_id])
        for m in Match.query.order_by(Match.match_number)
    ]


def test_ten_of_the_eleven_teams_get_six_series_each(app):
    with app.app_context():
        _, teams, schedule = premake_schedule(ROSTER, ["Edge Band"], start=START)

        assert len(teams) == 10
        assert Team.query.count() == 11, "the team that isn't coming stays registered"
        assert Match.query.count() == len(schedule) == 30
        assert validate_schedule(schedule) == {}

        counts = Counter()
        for match in Match.query:
            counts[match.red_team_id] += 1
            counts[match.blue_team_id] += 1
        assert set(counts.values()) == {6}
        absent = Team.query.filter_by(name="Edge Band").one()
        assert absent.id not in counts

        first = Match.query.order_by(Match.scheduled_time).first()
        assert first.scheduled_time == START
        assert all(m.status == "scheduled" for m in Match.query)
        assert MatchResult.query.count() == 0

        standings = get_division_rankings("High School")
        assert len(standings) == 10
        assert "Edge Band" not in {row["team_name"] for row in standings}


def test_the_same_teams_and_settings_always_give_the_same_schedule(tmp_path):
    results = []
    for name in ("one", "two"):
        (tmp_path / name).mkdir()
        app = _build(tmp_path / name, REGISTRATION_ONLY=False)
        with app.app_context():
            premake_schedule(ROSTER, ["Edge Band"], start=START)
            results.append(_pairings())
            db.session.remove()
    assert results[0] == results[1]


def test_round_length_and_arenas_set_the_times(app):
    with app.app_context():
        premake_schedule(ROSTER, ["Edge Band"], arenas=2, start=START, round_minutes=8)
        times = sorted({m.scheduled_time for m in Match.query})
        assert times[0] == START
        assert all(
            (later - earlier).total_seconds() % (8 * 60) == 0 for earlier, later in pairwise(times)
        )
        assert {m.arena for m in Match.query} == {"Arena 1", "Arena 2"}


def test_a_misspelled_team_is_refused_before_anything_is_written(app):
    with app.app_context():
        with pytest.raises(ScheduleError, match="No team in the sheet is called 'Edge Bnd'"):
            premake_schedule(ROSTER, ["Edge Bnd"], start=START)
        assert Team.query.count() == 0
        assert Match.query.count() == 0


def test_running_again_before_play_replaces_the_schedule(app):
    with app.app_context():
        premake_schedule(ROSTER, ["Edge Band"], start=START)
        premake_schedule(ROSTER, ["Edge Band"], start=datetime(2026, 10, 24, 10, 30))
        assert Match.query.count() == 30
        assert min(m.scheduled_time for m in Match.query) == datetime(2026, 10, 24, 10, 30)


def test_it_refuses_once_a_series_has_been_played(app):
    with app.app_context():
        premake_schedule(ROSTER, ["Edge Band"], start=START)
        first = Match.query.order_by(Match.match_number).first()
        db.session.add(
            MatchResult(
                match_id=first.id,
                game_number=1,
                outcome="red",
                red_final_zone="Plateau",
                blue_final_zone="Ring-out",
                submitted_by="ref",
            )
        )
        first.status = "in_progress"
        db.session.commit()
        before = _pairings()

        with pytest.raises(ScheduleError, match="already been played"):
            premake_schedule(ROSTER, [], start=START)
        assert _pairings() == before


def test_the_command_line_prints_the_schedule(tmp_path, monkeypatch, capsys):
    dbfile = tmp_path / "premade.db"
    monkeypatch.setattr(
        premake,
        "create_app",
        lambda: _build(
            tmp_path,
            REGISTRATION_ONLY=False,
            SQLALCHEMY_DATABASE_URI=f"sqlite:///{dbfile.as_posix()}",
        ),
    )
    assert premake.main([ROSTER, "--leave-out", "edge band", "--start", "2026-10-24 10:00"]) == 0
    out = capsys.readouterr().out
    assert "30 series for 10 teams, 6 each." in out
    assert "10:00 AM" in out

    assert premake.main([ROSTER, "--leave-out", "Nobody"]) == 1
    assert "No schedule was made" in capsys.readouterr().err
