# FOR LOCAL TESTING ONLY -- not part of the app, not meant to be part of
# your pull request. Seeding the real database is Shivani's assignment
# (seed/seed.py); this is just a quick way to get some fake data in your
# own local database so you can click through rankings/display/pit and see
# something other than an empty table while her real seed script isn't
# built yet.
#
# Run from the project root, with your virtualenv/deps installed:
#   python seed_for_testing.py
#
# It wipes and recreates your LOCAL database file only. Safe to run as
# many times as you want.

import random
from datetime import datetime, timedelta

from app import create_app
from app.db import db
from app.models import Team, Match, MatchResult

DIVISION = "High School"
ARENAS = ["Arena 1", "Arena 2"]


def seed():
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        # 24 fake teams
        teams = []
        for i in range(24):
            number = 1000 + i
            team = Team(
                team_number=number,
                name=f"Team {number}",
                affiliation=f"Test School {i}",
                division=DIVISION,
                students=f"Student {i}A\nStudent {i}B",
                adult_name=f"Adult {i}",
                adult_email=f"adult{i}@example.com",
                kit_ordered=True,
                checked_in=True,
            )
            teams.append(team)
        db.session.add_all(teams)
        db.session.commit()

        # A simple round of quals: pair teams up, a few matches per team.
        # This is NOT the real scheduler (that's Shaurya's) -- just enough
        # variety to test rankings math and the display pages.
        random.shuffle(teams)
        now = datetime.utcnow()
        matches = []
        match_number = 1
        for _round_num in range(3):  # 3 rounds -> 3 matches per team
            shuffled = teams[:]
            random.shuffle(shuffled)
            for i in range(0, len(shuffled), 2):
                if i + 1 >= len(shuffled):
                    break
                red, blue = shuffled[i], shuffled[i + 1]
                offset = match_number * 6  # spread matches out in time
                match = Match(
                    match_number=match_number,
                    phase="qualification",
                    division=DIVISION,
                    arena=ARENAS[match_number % len(ARENAS)],
                    scheduled_time=now + timedelta(minutes=offset),
                    red_team_id=red.id,
                    blue_team_id=blue.id,
                    status="scheduled",
                )
                matches.append(match)
                match_number += 1
        db.session.add_all(matches)
        db.session.commit()

        # Mark most matches complete with a result, leave the last couple
        # scheduled/in_progress so display + pit lookup have something to show.
        outcomes = ["red", "blue", "tie"]
        for match in matches[:-3]:
            match.status = "complete"
            result = MatchResult(
                match_id=match.id,
                outcome=random.choice(outcomes),
                win_time_seconds=round(random.uniform(2.0, 15.0), 2),
                red_final_zone="Center",
                blue_final_zone="Center",
                submitted_by="Test Ref",
            )
            db.session.add(result)

        if len(matches) >= 2:
            matches[-2].status = "in_progress"

        db.session.commit()

        print(f"Seeded {len(teams)} teams and {len(matches)} matches in '{DIVISION}'.")


if __name__ == "__main__":
    seed()
