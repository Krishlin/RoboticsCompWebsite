import csv
import io
import re

from flask import (
    current_app,
    render_template,
    request,
    redirect,
    url_for,
    abort,
    flash,
    Response,
)
from markupsafe import escape

from app.fake_data import DIVISION
from app.mail import send_email
from app.registration import registration_bp
from app.db import db
from app.models import Team
from sqlalchemy.exc import IntegrityError

# Deliberately loose: this catches typos like a missing "@" or a trailing
# comma, not every RFC 5322 edge case. The real check is that a confirmation
# email actually arrives.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Team numbers start here rather than at 1. Three digits reads as a team
# number at a glance on a pit sign, a match schedule and a bracket, and it
# leaves 1-99 free for anything that needs a reserved number later.
FIRST_TEAM_NUMBER = 100


def _send_confirmation_email(team):
    """Best-effort confirmation email. The team is saved either way.

    Everything interpolated below is escaped: team and student names come
    straight from a public form, and this is HTML going into someone's inbox.
    """
    students = ", ".join(team.students.splitlines())
    # config, not a literal: the same URL is on the confirmation page, and one
    # of the two going stale when the form changes is worse than neither.
    payment_url = current_app.config["PAYMENT_FORM_URL"]
    html = (
        f"<p>Hi {escape(team.adult_name)},</p>"
        f"<p><strong>{escape(team.name)}</strong> is registered for Summit on "
        f"October 24, 2026.</p>"
        f"<p>Your team number is <strong>{team.team_number}</strong>. Enter it in the "
        f"starter code so the field controller can start and stop your robot, and "
        f"give it at check-in.</p>"
        f"<ul>"
        f"<li>Team number: {team.team_number}</li>"
        f"<li>School: {escape(team.affiliation)}</li>"
        f"<li>Students: {escape(students)}</li>"
        f"</ul>"
        f"<p><strong>One step left:</strong> registration is complete once the $20 team "
        f'fee is paid. <a href="{escape(payment_url)}">Pay here</a> — the form asks for '
        f"your team number, which is {team.team_number}.</p>"
        f"<p>Climb together.</p>"
    )
    # Collapse whitespace: a newline pasted into the team name would otherwise
    # end up inside a header value.
    subject_name = " ".join(team.name.split())
    return send_email(
        to=team.adult_email,
        subject=f"You are registered - {subject_name}",
        html=html,
    )


@registration_bp.route("/", methods=["GET", "POST"])
def signup():
    errors = []

    form_data = {
        "team_name": "",
        "affiliation": "",
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

        student_names = [
            request.form.get(f"student_{i}", "").strip() for i in range(1, 5)
        ]
        student_names = [name for name in student_names if name]

        adult_name = request.form.get("adult_name", "").strip()
        # Stored and compared lowercased: the uniqueness rule is meant to be
        # "one adult, one team", and Coach.Diaz@x.com is the same mailbox as
        # coach.diaz@x.com. Comparing raw input let the same adult register twice.
        adult_email = request.form.get("adult_email", "").strip().lower()
        adult_phone = request.form.get("adult_phone", "").strip() or None
        kit_ordered = request.form.get("kit_ordered") is not None

        # Everything the registrant typed, so signup.html can put it back in
        # the form when validation fails. A coach entering four students
        # should not have to retype the lot because one field was blank.
        form_data.update(
            team_name=team_name,
            affiliation=request.form.get("affiliation", "").strip(),
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
        if not adult_name:
            errors.append("Adult of record is required.")
        if not adult_email:
            errors.append("Adult email is required.")
        elif not EMAIL_RE.match(adult_email):
            errors.append("Enter a valid email address for the adult of record.")
        # Presence only - phone formats vary too much to validate usefully, and
        # a rejected-but-correct number is worse than an odd-looking one.
        if not adult_phone:
            errors.append("Adult phone number is required.")

        if len(student_names) < 1:
            errors.append("Enter at least 1 student.")
        if len(student_names) > 4:
            errors.append("You can only enter up to 4 students.")

        # --- Email uniqueness (Week 4) ---
        if adult_email and EMAIL_RE.match(adult_email):
            existing_team = Team.query.filter_by(adult_email=adult_email).first()
            if existing_team:
                errors.append(
                    f"That email is already registered to {existing_team.name}. "
                    f"Each adult of record can only be used once."
                )

        if not errors:
            students_text = "\n".join(student_names)

            # --- Team numbering (internal only) ---
            # Nothing shows this to a registrant any more, but team_number is
            # still unique and non-null on the model, and check-in, the
            # schedule, rankings and the bracket all join on it - so it keeps
            # being assigned here.
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
                # Never below FIRST_TEAM_NUMBER, even if rows already exist
                # with lower numbers from before the floor was introduced —
                # otherwise the first real team after a test row would be
                # numbered 3 rather than 100.
                next_number = max(
                    (last_team.team_number + 1) if last_team else FIRST_TEAM_NUMBER,
                    FIRST_TEAM_NUMBER,
                )

                new_team = Team(
                    team_number=next_number,
                    name=team_name,
                    affiliation=affiliation,
                    # Not taken from the form: there is only one division, and a
                    # team filed under anything else is invisible to the schedule,
                    # rankings and bracket pages.
                    division=DIVISION,
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
                # Flashed either way, so the confirmation page can tell the
                # truth about whether an email actually went out — and so a
                # later visit to that URL claims nothing about email at all.
                if _send_confirmation_email(new_team):
                    flash(f"A confirmation email is on its way to {new_team.adult_email}.")
                else:
                    flash(
                        "We could not send a confirmation email just now - "
                        "write your team number down, you will need it at check-in."
                    )

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
        errors=errors,
        form_data=form_data,
    )


@registration_bp.route("/confirmation/<int:team_number>")
def confirmation(team_number):
    """Shown straight after a team registers, so they learn their number."""
    team = Team.query.filter_by(team_number=team_number).first()
    if team is None:
        abort(404)
    return render_template(
        "registration/confirmation.html",
        team=team,
        payment_url=current_app.config["PAYMENT_FORM_URL"],
    )


@registration_bp.route("/teams")
def team_list():
    """Full team list, used as the check-in reference."""
    teams = Team.query.order_by(Team.team_number).all()
    return render_template("registration/team_list.html", teams=teams)


@registration_bp.route("/teams.csv")
def team_list_csv():
    """The team list as a CSV download, for check-in desks working off paper."""
    teams = Team.query.order_by(Team.team_number).all()

    # StringIO rather than writing a file: the response is built in memory and
    # streamed straight back, so there is no temp file to clean up.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "name", "division", "affiliation", "students",
        "adult_name", "adult_email", "adult_phone", "kit_ordered", "checked_in",
    ])
    for team in teams:
        writer.writerow([
            team.name,
            team.division,
            team.affiliation,
            "; ".join(team.students.splitlines()),
            team.adult_name,
            team.adult_email,
            team.adult_phone or "",
            "yes" if team.kit_ordered else "no",
            "yes" if team.checked_in else "no",
        ])

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=teams.csv"},
    )
