# owner: Jon
# Rankings pages per division, the big-screen auto-refreshing display
# (current match, next three matches, live rankings), and the pit lookup
# page (enter a team number, see next match and arena).
#
# Reads real data via app/rankings/logic.py, which itself defers the actual
# standings math to the pure functions in app/rankings/tiebreak.py.

from flask import render_template, request

from app.rankings import rankings_bp
from app.rankings.logic import (
    get_division_rankings,
    get_current_match,
    get_upcoming_matches,
    get_team_next_match,
)


@rankings_bp.route("/<division>")
def rankings(division):
    division_name = division.replace("_", " ")
    return render_template(
        "rankings/rankings.html",
        division=division_name,
        rankings=get_division_rankings(division_name),
    )


@rankings_bp.route("/display/<division>")
def display(division):
    division_name = division.replace("_", " ")
    return render_template(
        "rankings/display.html",
        division=division_name,
        current_match=get_current_match(division_name),
        next_matches=get_upcoming_matches(division_name, limit=3),
        rankings=get_division_rankings(division_name)[:8],
    )


@rankings_bp.route("/pit", methods=["GET", "POST"])
def pit_lookup():
    team = None
    next_match = None
    if request.method == "POST":
        team_number = request.form.get("team_number")
        if team_number and team_number.isdigit():
            team, next_match = get_team_next_match(int(team_number))
    return render_template(
        "rankings/pit_lookup.html",
        team=team,
        next_match=next_match,
    )
