# owner: Shivani
# Check-in list (one tap per team), and the inspection checklist
# (pass/fail, timestamped, re-inspection allowed with both attempts kept).

from flask import render_template

from app.fake_data import TEAMS, INSPECTIONS, get_team
from app.checkin import checkin_bp
from app.db import db
from app.models import Team
from flask import render_template, redirect, url_for 

@checkin_bp.route("/")
def checkin_list():
    # Get every team from the real database,
    # ordered by team number.
    teams = Team.query.order_by(Team.team_number).all()

    # Send those teams to the check-in page.
    return render_template("checkin/checkin_list.html", teams=teams)


@checkin_bp.route("/<int:team_id>/check-in", methods=["POST"])
def check_in_team(team_id):
    # Find the team that matches the ID from the button.
    team = Team.query.get_or_404(team_id)

    # Mark the team as arrived.
    team.checked_in = True

    # Save that change to the database.
    db.session.commit()

    # Send the user back to the check-in list.
    return redirect(url_for("checkin.checkin_list"))

@checkin_bp.route("/inspect/<int:team_number>", methods=["GET", "POST"])
def inspection_form(team_number):
    # TODO(Shivani): on POST, save a new Inspection row. For now this just
    # shows the form.
    team = get_team(team_number)
    return render_template("checkin/inspection_form.html", team=team)


@checkin_bp.route("/history/<int:team_number>")
def inspection_history(team_number):
    team = get_team(team_number)
    history = [i for i in INSPECTIONS if i["team_number"] == team_number]
    return render_template("checkin/inspection_history.html", team=team, history=history)
