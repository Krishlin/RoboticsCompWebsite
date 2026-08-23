# owner: Shivani
# Check-in list (one tap per team), and the inspection checklist
# (pass/fail, timestamped, re-inspection allowed with both attempts kept).

from flask import render_template

from app.fake_data import TEAMS, INSPECTIONS, get_team
from app.checkin import checkin_bp


@checkin_bp.route("/")
def checkin_list():
    return render_template("checkin/checkin_list.html", teams=TEAMS)


@checkin_bp.route("/inspect/<int:team_number>", methods=["GET", "POST"])
def inspection_form(team_number):
    # TODO(Shivani): on POST, save a new Inspection row (see
    # logic.py:record_inspection). For now this just shows the form.
    team = get_team(team_number)
    return render_template("checkin/inspection_form.html", team=team)


@checkin_bp.route("/history/<int:team_number>")
def inspection_history(team_number):
    team = get_team(team_number)
    history = [i for i in INSPECTIONS if i["team_number"] == team_number]
    return render_template("checkin/inspection_history.html", team=team, history=history)
