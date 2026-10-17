# owner: Shivani
#
# This script will generate realistic fake data directly into the real
# database (as opposed to app/fake_data.py, which is hardcoded Python used
# by every blueprint's routes.py before the database is wired up).
#
# What it does:
#   1. Create 24 fake Team rows in the one division.
#   2. Generate a qualification schedule for them with Shaurya's generator
#      (app/scheduler/generator.py), so the fake schedule obeys the same
#      rules as the real one.
#   3. Create Match rows from that schedule. Each one is a best-of-three
#      series (game manual T3).
#   4. Play out about two thirds of those series game by game, so there's
#      something to look at in rankings, the bracket, and admin without
#      everyone having to click through the referee flow by hand first.
#
# Run with: python -m seed.seed   (from the project root, venv active)
#
# WARNING: it empties the database it points at first. That is whatever
# DATABASE_URL says - check it is not the event database.

import random
from datetime import datetime

from app import create_app
from app.db import db
from app.models import AuditEntry, BracketConfig, Inspection, Match, MatchResult, Team
from app.scheduler.generator import generate_advanced_schedule
from app.series import VALID_ZONES, tally


DIVISIONS = ["High School"]

SCHOOLS = [
    "Lincoln High",
    "Oakwood High School",
    "Riverside STEM Academy",
    "Independent",
    "Maple Grove High",
    "Central High School",
    "Hillcrest High",
    "Westview High School",
]

STUDENT_NAMES = [
    "Ava", "Liam", "Noah", "Emma", "Mia", "Ethan",
    "Sofia", "Lucas", "Zoe", "Mason", "Ella", "Owen",
    "Grace", "Leo", "Nora", "Kai", "Ruby", "Sam",
    "Ivy", "Theo", "Luna", "Max", "Isla", "Finn",
]


def seed_teams():
    team_count = 0

    for division_index, division in enumerate(DIVISIONS):
        base_number = 100 + (division_index * 100)

        for i in range(24):
            team_number = base_number + i + 1

            first_student = STUDENT_NAMES[
                (team_count * 2) % len(STUDENT_NAMES)
            ]

            second_student = STUDENT_NAMES[
                (team_count * 2 + 1) % len(STUDENT_NAMES)
            ]

            team = Team(
                team_number=team_number,
                name=f"Team {team_number}",
                affiliation=SCHOOLS[i % len(SCHOOLS)],
                division=division,
                students=f"{first_student}\n{second_student}",
                adult_name=f"Adult of Team {team_number}",
                adult_email=f"adult{team_number}@example.com",
                adult_phone=f"555-01{team_count:02d}",
                kit_ordered=False,
                checked_in=False,
            )

            db.session.add(team)
            team_count += 1

    db.session.commit()

    return team_count


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


def seed_database():
    app = create_app()

    with app.app_context():
        AuditEntry.query.delete()
        MatchResult.query.delete()
        Match.query.delete()
        BracketConfig.query.delete()
        Inspection.query.delete()
        Team.query.delete()
        db.session.commit()

        team_count = seed_teams()

        match_count, game_count = seed_matches()

        print(
            f"Successfully seeded {team_count} teams, "
            f"{match_count} series, and "
            f"{game_count} game results."
        )


if __name__ == "__main__":
    seed_database()