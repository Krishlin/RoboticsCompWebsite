# owner: Emily
# Public signup form (team name, school/independent, division, 1-4
# students, adult of record, kit order), team numbering, confirmation
# email, and CSV export for check-in.
#
# Right now every page here renders fake data from app/fake_data.py. The
# form doesn't save anything yet — submitting it just re-shows the form.

from flask import render_template, request

from app.fake_data import TEAMS, DIVISIONS
from app.registration import registration_bp
from app.db import db
from app.models import Team


@registration_bp.route("/", methods=["GET", "POST"])
def signup():
    success = False

    if request.method == "POST":
        team_name = request.form.get("team_name", "").strip()
        affiliation = request.form.get("affiliation", "").strip() or "Independent"
        division = request.form.get("division", "").strip()

        student_names = [
            request.form.get(f"student_{i}", "").strip() for i in range(1, 5)
        ]
        student_names = [name for name in student_names if name]  # drop blanks
        students_text = "\n".join(student_names)

        adult_name = request.form.get("adult_name", "").strip()
        adult_email = request.form.get("adult_email", "").strip()
        adult_phone = request.form.get("adult_phone", "").strip() or None
        kit_ordered = request.form.get("kit_ordered") is not None  # checkbox

        # Temporary team-number logic for Week 2 — Week 4 will make this
        # safer (e.g. handling two people submitting at the same instant).
        last_team = Team.query.order_by(Team.team_number.desc()).first()
        next_number = (last_team.team_number + 1) if last_team else 1

        new_team = Team(
            team_number=next_number,
            name=team_name,
            affiliation=affiliation,
            division=division,
            students=students_text,
            adult_name=adult_name,
            adult_email=adult_email,
            adult_phone=adult_phone,
            kit_ordered=kit_ordered,
        )
        db.session.add(new_team)
        db.session.commit()

        success = True

    return render_template(
        "registration/signup.html", divisions=DIVISIONS, success=success
    )



