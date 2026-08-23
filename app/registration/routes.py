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


@registration_bp.route("/", methods=["GET", "POST"])
def signup():
    # TODO(Emily): on POST, validate the form and create a real Team row
    # (see logic.py for the pieces you'll need: assign_team_number,
    # is_email_unique, validate_student_count). For now this just re-renders
    # the empty form no matter what is submitted.
    return render_template("registration/signup.html", divisions=DIVISIONS)


@registration_bp.route("/confirmation")
def confirmation():
    # Fake "just registered" team, standing in for the real one until the
    # signup form actually saves something.
    fake_new_team = TEAMS[0]
    return render_template("registration/confirmation.html", team=fake_new_team)


@registration_bp.route("/teams")
def team_list():
    return render_template("registration/team_list.html", teams=TEAMS)
