"""The seed data everyone develops against: 24 teams, a legal schedule, and a
mix of finished and unplayed best-of-three series."""

from app.db import db
from app.match_state import series_tally
from app.models import Match, MatchResult, Team
from app.rankings.logic import get_division_rankings
from app.scheduler.generator import validate_schedule
from app.series import VALID_ZONES
from seed.seed import seed_matches, seed_teams
from tests.conftest import _build


def test_seed_builds_a_playable_event(tmp_path):
    app = _build(tmp_path, REGISTRATION_ONLY=False)
    with app.app_context():
        assert seed_teams() == 24
        series, games = seed_matches()

        assert Team.query.count() == 24
        assert series == Match.query.count() == 72  # 24 teams x 6 series / 2
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
        assert 0 < len(complete) < 72
        assert all(series_tally(m).winner for m in complete)
        assert {g.red_final_zone for g in MatchResult.query} <= set(VALID_ZONES)

        standings = get_division_rankings("High School")
        assert len(standings) == 24
        assert standings[0]["qual_points"] > 0
        db.session.remove()
