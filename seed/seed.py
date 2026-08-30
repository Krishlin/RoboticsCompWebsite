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

from app import create_app
from app.db import db
from app.models import Team

DIVISIONS = ["Elementary", "Middle School"]

SCHOOLS = [
    "Lincoln Elementary",
    "Oakwood Middle School",
    "Riverside STEM Academy",
    "Independent",
    "Maple Grove Elementary",
    "Central Middle School",
    "Hillcrest Elementary",
    "Westview Middle School",
]

STUDENT_NAMES = [
    "Ava", "Liam", "Noah", "Emma", "Mia", "Ethan",
    "Sofia", "Lucas", "Zoe", "Mason", "Ella", "Owen",
    "Grace", "Leo", "Nora", "Kai", "Ruby", "Sam",
    "Ivy", "Theo", "Luna", "Max", "Isla", "Finn",
]


def seed_database():
    app = create_app()

    with app.app_context():

        # Remove existing teams - script can run again.
        Team.query.delete()
        db.session.commit()


        team_count = 0

        for division_index, division in enumerate(DIVISIONS):

            
            
            base_number = 100 + (division_index * 100)

            for i in range(12):
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

        print(f"Successfully seeded {team_count} teams.")



if __name__ == "__main__":
    seed_database()
