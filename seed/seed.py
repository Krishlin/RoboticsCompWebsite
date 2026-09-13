# owner: Shivani
#
# This script will generate realistic fake data directly into the real
# database (as opposed to app/fake_data.py, which is hardcoded Python used
# by every blueprint's routes.py before the database is wired up).
#
# What this should do, once it's real:
#   1. Create ~24 fake Team rows, split across the two divisions.
#   2. Generate a qualification schedule for them (using Shaurya's
#      generate_schedule from app/scheduler/logic.py once it exists).
#   3. Create Match rows from that schedule.
#   4. Create MatchResult rows for some of those matches, so there's
#      something to look at in rankings, the bracket, and admin without
#      everyone having to click through the referee flow by hand first.
#
# Run with: python3 -m seed.seed
# (once this is implemented, from the project root, with the virtualenv
# active)

from datetime import datetime, timedelta

from app import create_app
from app.db import db
from app.models import Team, Match, MatchResult


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


def seed_matches():
    teams = Team.query.order_by(Team.team_number).all()

    teams_by_division = {}

    for team in teams:
        if team.division not in teams_by_division:
            teams_by_division[team.division] = []

        teams_by_division[team.division].append(team)

    zones = [
        "Center",
        "Red Zone",
        "Blue Zone",
        "Off Arena",
    ]

    outcomes = [
        "red",
        "blue",
        "tie",
        "double_dq",
    ]

    match_number = 1
    match_count = 0
    result_count = 0

    start_time = datetime(2026, 9, 12, 9, 0)

    for division, division_teams in teams_by_division.items():

        for round_offset in range(5):

            for i in range(0, len(division_teams), 2):

                if i + 1 >= len(division_teams):
                    continue

                red_team = division_teams[
                    (i + round_offset) % len(division_teams)
                ]

                blue_team = division_teams[
                    (i + 1 + round_offset) % len(division_teams)
                ]

                match_count += 1

                is_complete = round_offset < 3

                match = Match(
                    match_number=match_number,
                    phase="qualification",
                    division=division,
                    arena=(
                        "Arena 1"
                        if match_count % 2 == 0
                        else "Arena 2"
                    ),
                    scheduled_time=(
                        start_time
                        + timedelta(minutes=15 * (match_count - 1))
                    ),
                    red_team_id=red_team.id,
                    blue_team_id=blue_team.id,
                    status=(
                        "complete"
                        if is_complete
                        else "scheduled"
                    ),
                    is_replay=False,
                    bracket_round=None,
                    bracket_slot=None,
                )

                db.session.add(match)
                db.session.flush()

                if is_complete:
                    outcome = outcomes[
                        match_count % len(outcomes)
                    ]

                    result = MatchResult(
                        match_id=match.id,
                        outcome=outcome,
                        win_time_seconds=round(
                            3.5 + (match_count % 10) * 0.8,
                            2,
                        ),
                        red_final_zone=zones[
                            match_count % len(zones)
                        ],
                        blue_final_zone=zones[
                            (match_count + 1) % len(zones)
                        ],
                        submitted_by=(
                            "Referee A"
                            if match_count % 2
                            else "Referee B"
                        ),
                    )

                    db.session.add(result)
                    result_count += 1

                match_number += 1

    db.session.commit()

    return match_count, result_count


def seed_database():
    app = create_app()

    with app.app_context():
        MatchResult.query.delete()
        Match.query.delete()
        Team.query.delete()
        db.session.commit()

        team_count = seed_teams()

        match_count, result_count = seed_matches()

        print(
            f"Successfully seeded {team_count} teams, "
            f"{match_count} matches, and "
            f"{result_count} results."
        )


if __name__ == "__main__":
    seed_database()