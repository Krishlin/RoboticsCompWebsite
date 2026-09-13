from flask import render_template, request, redirect, url_for, abort

from app.fake_data import DIVISIONS
from app.registration import registration_bp
from app.db import db
from app.models import Team
from sqlalchemy.exc import IntegrityError


@registration_bp.route("/", methods=["GET", "POST"])
def signup():
    errors = []

    form_data = {
        "team_name": "",
        "affiliation": "",
        "division": "",
        "student_1": "",
        "student_2": "",
        "student_3": "",
        "student_4": "",
        "adult_name": "",
        "adult_email": "",
        "adult_phone": "",
        "kit_ordered": False,
    }

    if request.method == "POST":
        team_name = request.form.get("team_name", "").strip()
        affiliation = request.form.get("affiliation", "").strip() or "Independent"
        division = request.form.get("division", "").strip()

        student_names = [
            request.form.get(f"student_{i}", "").strip() for i in range(1, 5)
        ]
        student_names = [name for name in student_names if name]

        adult_name = request.form.get("adult_name", "").strip()
        adult_email = request.form.get("adult_email", "").strip()
        adult_phone = request.form.get("adult_phone", "").strip() or None
        kit_ordered = request.form.get("kit_ordered") is not None

        # Everything the registrant typed, so signup.html can put it back in
        # the form when validation fails. A coach entering four students
        # should not have to retype the lot because one field was blank.
        form_data.update(
            team_name=team_name,
            affiliation=request.form.get("affiliation", "").strip(),
            division=division,
            student_1=request.form.get("student_1", ""),
            student_2=request.form.get("student_2", ""),
            student_3=request.form.get("student_3", ""),
            student_4=request.form.get("student_4", ""),
            adult_name=adult_name,
            adult_email=adult_email,
            adult_phone=request.form.get("adult_phone", ""),
            kit_ordered=kit_ordered,
        )

        # --- Validation (Week 3) ---
        if not team_name:
            errors.append("Team name is required.")
        if not division:
            errors.append("Please choose a division.")
        if not adult_name:
            errors.append("Adult of record is required.")
        if not adult_email:
            errors.append("Adult email is required.")

        if len(student_names) < 1:
            errors.append("Enter at least 1 student.")
        if len(student_names) > 4:
            errors.append("You can only enter up to 4 students.")

        # --- Email uniqueness (Week 4) ---
        if adult_email:
            existing_team = Team.query.filter_by(adult_email=adult_email).first()
            if existing_team:
                errors.append(
                    f"That email is already registered on Team "
                    f"#{existing_team.team_number} ({existing_team.name}). "
                    f"Each adult of record can only be used once."
                )

        if not errors:
            students_text = "\n".join(student_names)

            # --- Team numbering (Week 4: safer than before) ---
            # Retry a couple times in case two people submit at the exact
            # same instant and both try to grab the same next number —
            # the database's unique constraint on team_number will reject
            # the second one, so we catch that and try again with a fresh
            # number instead of crashing.
            attempts = 0
            saved_team_number = None
            while attempts < 3 and saved_team_number is None:
                attempts += 1
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
                try:
                    db.session.commit()
                    saved_team_number = new_team.team_number
                except IntegrityError:
                    db.session.rollback()
                    # loop again and try the next number

            if saved_team_number is not None:
                # Send them to the confirmation page, which is the only place
                # they are told their team number.
                return redirect(
                    url_for("registration.confirmation", team_number=saved_team_number)
                )

            errors.append(
                "Something went wrong assigning a team number. Please try again."
            )

    return render_template(
        "registration/signup.html",
        divisions=DIVISIONS,
        errors=errors,
        form_data=form_data,
    )


@registration_bp.route("/confirmation/<int:team_number>")
def confirmation(team_number):
    """Shown straight after a team registers, so they learn their number."""
    team = Team.query.filter_by(team_number=team_number).first()
    if team is None:
        abort(404)
    return render_template("registration/confirmation.html", team=team)


@registration_bp.route("/teams")
def team_list():
    """Full team list, used as the check-in reference."""
    teams = Team.query.order_by(Team.team_number).all()
    return render_template("registration/team_list.html", teams=teams)
