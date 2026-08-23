# owner: Jon
# Rankings pages per division, the big-screen auto-refreshing display
# (current match, next three matches, live rankings), and the pit lookup
# page (enter a team number, see next match and arena).

from flask import render_template, request

from app.fake_data import fake_rankings, CURRENT_MATCH, upcoming_matches, get_team
from app.rankings import rankings_bp


@rankings_bp.route("/<division>")
def rankings(division):
    division_name = division.replace("_", " ")
    return render_template(
        "rankings/rankings.html",
        division=division_name,
        rankings=fake_rankings(division_name),
    )


@rankings_bp.route("/display/<division>")
def display(division):
    division_name = division.replace("_", " ")
    return render_template(
        "rankings/display.html",
        division=division_name,
        current_match=CURRENT_MATCH,
        next_matches=upcoming_matches(division_name, limit=3),
        rankings=fake_rankings(division_name)[:8],
    )


@rankings_bp.route("/pit", methods=["GET", "POST"])
def pit_lookup():
    # TODO(Jon): on POST, look up the real next match for the team number
    # entered. For now this always shows the same fake next match.
    team_number = request.form.get("team_number")
    team = get_team(int(team_number)) if team_number and team_number.isdigit() else None
    next_match = upcoming_matches(limit=1)
    return render_template(
        "rankings/pit_lookup.html",
        team=team,
        next_match=next_match[0] if next_match else None,
    )
