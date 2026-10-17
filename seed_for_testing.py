# FOR LOCAL TESTING ONLY -- not part of the app, not meant to be part of
# your pull request. Drops and recreates every table, then fills them with
# the same fake event seed/seed.py builds: 24 teams, a real generated
# schedule of best-of-three series, and about two thirds of it played.
#
# Run from the project root, with your virtualenv/deps installed:
#   python seed_for_testing.py
#
# It wipes the database DATABASE_URL points at (your local SQLite file when
# that is unset). Never run it with the event database configured.

from app import create_app
from app.db import db
from seed.seed import seed_matches, seed_teams


def seed():
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        team_count = seed_teams()
        match_count, game_count = seed_matches()
        print(f"Seeded {team_count} teams, {match_count} series and {game_count} games.")


if __name__ == "__main__":
    seed()
