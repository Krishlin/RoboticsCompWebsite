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
# Run with: python seed/seed.py
# (once this is implemented, from the project root, with the virtualenv
# active)


def seed_database():
    """Wipe and repopulate the database with fake tournament data."""
    pass


if __name__ == "__main__":
    seed_database()
