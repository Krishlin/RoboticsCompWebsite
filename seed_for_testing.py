# FOR LOCAL TESTING ONLY -- not part of the app, not meant to be part of
# your pull request. Drops and recreates every table, then fills them with
# the real teams from the registration sheet plus a generated schedule with
# about two thirds of it played (made-up results; see seed/seed.py --play).
#
# Run from the project root, with your virtualenv/deps installed:
#   python seed_for_testing.py <sheet link, CSV link, or .csv file>
#
# It wipes the database DATABASE_URL points at (your local SQLite file when
# that is unset). Never run it with the event database configured.

import sys

from app import create_app
from app.db import db
from seed.seed import seed_matches, seed_teams


def seed(source):
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        team_count = seed_teams(source)
        match_count, game_count = seed_matches()
        print(f"Seeded {team_count} teams, {match_count} series and {game_count} games.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python seed_for_testing.py <sheet link, CSV link, or .csv file>")
    seed(sys.argv[1])
