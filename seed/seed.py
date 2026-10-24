# owner: Shivani
#
# Resets a database to the real event's starting point: the registered teams
# from the registration sheet, and nothing else. Nobody is checked in, there
# is no schedule and no result, which is exactly where the head ref starts on
# the day (check teams in, then generate the schedule from the ones who came).
#
#   python -m seed.seed <sheet link, CSV link, or .csv file>
#   python -m seed.seed <...> --play
#
# --play is for development only. It also generates a qualification schedule
# with Shaurya's generator (app/scheduler/generator.py) and plays about two
# thirds of it game by game, so rankings, the bracket and the admin pages have
# something on them without clicking through the referee flow. Those results
# are made up; never use --play on a database the event will run on.
#
# The sheet link is not in this repo on purpose; see seed/teams.py.
#
# WARNING: it empties the database it points at first. That is whatever
# DATABASE_URL says - check it is not the event database.

import argparse
import random
import sys
from datetime import datetime

from app import create_app
from app.db import db
from app.models import AuditEntry, BracketConfig, Inspection, Match, MatchResult, Team
from app.roster import RosterError, import_roster, parse_roster
from app.scheduler.generator import generate_advanced_schedule
from app.series import VALID_ZONES, tally
from seed.teams import load_teams, print_summary, read_source


def seed_teams(source):
    """Import the roster from `source`. Returns how many teams were added."""
    return len(load_teams(source).added)


def _play_series(match, rng):
    """Play one series game by game until someone has two wins.

    Mostly decisive games, with the odd tie (which the next game replays)
    and a rare double DQ, the same mix a real event throws at the rankings.
    """
    outcomes = []
    game_number = 0
    while tally(outcomes).winner is None:
        game_number += 1
        outcome = rng.choices(["red", "blue", "tie", "double_dq"], weights=[45, 45, 8, 2])[0]
        outcomes.append(outcome)
        winner_zone = rng.choice(VALID_ZONES[:4])
        db.session.add(MatchResult(
            match_id=match.id,
            game_number=game_number,
            outcome=outcome,
            win_time_seconds=round(rng.uniform(8, 180), 1) if outcome in ("red", "blue") else None,
            red_final_zone=winner_zone if outcome != "blue" else "Ring-out",
            blue_final_zone=winner_zone if outcome != "red" else "Ring-out",
            submitted_by=match.arena,
        ))
    match.status = "complete"
    return game_number


def seed_matches():
    """Development only: a generated schedule with two thirds of it played."""
    rng = random.Random(2026)
    random.seed(2026)  # the generator draws from the module-level random

    teams = Team.query.order_by(Team.team_number).all()
    team_by_number = {team.team_number: team for team in teams}

    schedule = generate_advanced_schedule(
        [{"team_number": t.team_number, "division": t.division} for t in teams],
        arenas=["Arena 1", "Arena 2"],
        start_time=datetime(2026, 10, 24, 10, 0),
    )

    match_count = 0
    game_count = 0
    played = (len(schedule) * 2) // 3

    for index, entry in enumerate(schedule):
        match = Match(
            match_number=entry["match_number"],
            phase="qualification",
            division=entry["division"],
            arena=entry["arena"],
            scheduled_time=datetime.strptime(entry["scheduled_time"], "%Y-%m-%d %H:%M"),
            red_team_id=team_by_number[entry["red_team_number"]].id,
            blue_team_id=team_by_number[entry["blue_team_number"]].id,
            status="scheduled",
        )
        db.session.add(match)
        db.session.flush()
        match_count += 1

        if index < played:
            game_count += _play_series(match, rng)

    db.session.commit()

    return match_count, game_count


def empty_event_tables():
    AuditEntry.query.delete()
    MatchResult.query.delete()
    Match.query.delete()
    BracketConfig.query.delete()
    Inspection.query.delete()
    Team.query.delete()
    db.session.commit()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reset the database to the real teams.")
    parser.add_argument("source", help="Google Sheets link, CSV link, or path to a .csv file")
    parser.add_argument(
        "--play",
        action="store_true",
        help="development only: also generate a schedule and play made-up results",
    )
    args = parser.parse_args(argv)

    app = create_app()
    with app.app_context():
        print(f"Database: {app.config['SQLALCHEMY_DATABASE_URI'].split('@')[-1]}")
        # Read and check the sheet before emptying anything, so a bad link or
        # a broken row leaves the database as it was.
        try:
            rows = parse_roster(read_source(args.source))
        except RosterError as exc:
            print("Nothing was changed:", file=sys.stderr)
            for problem in exc.problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        empty_event_tables()
        print_summary(import_roster(rows))

        if args.play:
            match_count, game_count = seed_matches()
            print(f"Generated {match_count} series and played {game_count} made-up games.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
