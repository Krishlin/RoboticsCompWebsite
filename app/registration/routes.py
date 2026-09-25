from flask import render_template, request

from app.fake_data import DIVISIONS
from app.registration import registration_bp
from app.db import db
from app.models import Team
from sqlalchemy.exc import IntegrityError


@registration_bp.route("/", methods=["GET", "POST"])
def signup():
    success = False
    errors = []

    # Default values shown on the form. Used both for a fresh GET request
    # and to re-populate the form if validation fails on POST, so the
    # person doesn't have to retype everything.
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
        # Pull every field out of the submitted form. .strip() removes
        # accidental leading/trailing whitespace from typing.
        team_name = request.form.get("team_name", "").strip()
        affiliation = request.form.get("affiliation", "").strip() or "Independent"
        division = request.form.get("division", "").strip()

        # Collect up to 4 student name fields, then drop any that were
        # left blank (so "student 3" being empty doesn't count as a student).
        student_names = [
            request.form.get(f"student_{i}", "").strip() for i in range(1, 5)
        ]
        student_names = [name for name in student_names if name]

        adult_name = request.form.get("adult_name", "").strip()
        adult_email = request.form.get("adult_email", "").strip()
        adult_phone = request.form.get("adult_phone", "").strip() or None
        # Checkboxes only send a value when checked, so "was it submitted
        # at all" is how we detect true/false here.
        kit_ordered = request.form.get("kit_ordered") is not None

        # Save whatever the person typed back into form_data, so if we
        # end up re-rendering the page below (due to errors), the form
        # still shows their input instead of going blank.
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
        # Required-field checks. Each failure adds a human-readable
        # message to errors, which the template displays back to the user.
        if not team_name:
            errors.append("Team name is required.")
        if not division:
            errors.append("Please choose a division.")
        if not adult_name:
            errors.append("Adult of record is required.")
        if not adult_email:
            errors.append("Adult email is required.")

        # Team size must be between 1 and 4 students.
        if len(student_names) < 1:
            errors.append("Enter at least 1 student.")
        if len(student_names) > 4:
            errors.append("You can only enter up to 4 students.")

        # --- Email uniqueness (Week 4) ---
        # Look up whether any existing team already used this email.
        # If so, block the submission and name the conflicting team so
        # the error is actually useful, not just "email taken."
        if adult_email:
            existing_team = Team.query.filter_by(adult_email=adult_email).first()
            if existing_team:
                errors.append(
                    f"That email is already registered on Team "
                    f"#{existing_team.team_number} ({existing_team.name}). "
                    f"Each adult of record can only be used once."
                )

        # Only attempt to save if nothing above failed.
        if not errors:
            students_text = "\n".join(student_names)

            # --- Team numbering (Week 4: safer than before) ---
            # Retry a couple times in case two people submit at the exact
            # same instant and both try to grab the same next number —
            # the database's unique constraint on team_number will reject
            # the second one, so we catch that and try again with a fresh
            # number instead of crashing.
            attempts = 0
            saved = False
            while attempts < 3 and not saved:
                attempts += 1
                # Find the highest team_number currently in use, then
                # claim the next one up.
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
                    saved = True
                except IntegrityError:
                    # Someone else grabbed this team_number first (a
                    # race condition). Roll back this failed attempt and
                    # loop again to try the next number instead of crashing.
                    db.session.rollback()

            if saved:
                success = True
                # Reset the form back to blank now that registration
                # actually succeeded.
                form_data = {key: "" for key in form_data}
                form_data["kit_ordered"] = False
            else:
                # Only reachable if all 3 retry attempts hit a collision —
                # extremely unlikely, but fail gracefully instead of 500ing.
                errors.append(
                    "Something went wrong assigning a team number. Please try again."
                )

    return render_template(
        "registration/signup.html",
        divisions=DIVISIONS,
        success=success,
        errors=errors,
        form_data=form_data,
    )

