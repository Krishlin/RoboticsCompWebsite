# owner: Serena
# Shows the current match, a start button, an on-screen timer, and the
# end-of-match result entry (winner/tie/double DQ + final zones), with a
# confirm step before submitting. Locked after submission.

from flask import render_template

from app.fake_data import CURRENT_MATCH, MATCHES_BY_ID, get_team
from app.referee import referee_bp


@referee_bp.route("/")
def current_match():
    match = CURRENT_MATCH
    red = get_team(match["red_team_number"]) if match else None
    blue = get_team(match["blue_team_number"]) if match else None
    return render_template("referee/current_match.html", match=match, red=red, blue=blue)


@referee_bp.route("/result/<int:match_id>", methods=["GET", "POST"])
def result_entry(match_id):
    # TODO(Serena): on POST, record win_time_seconds automatically (start
    # button tap to winner tap) and hand off to logic.py:submit_result.
    match = MATCHES_BY_ID.get(match_id)
    red = get_team(match["red_team_number"]) if match else None
    blue = get_team(match["blue_team_number"]) if match else None
    return render_template("referee/result_entry.html", match=match, red=red, blue=blue)


@referee_bp.route("/confirm/<int:match_id>")
def confirm(match_id):
    match = MATCHES_BY_ID.get(match_id)
    return render_template("referee/confirm.html", match=match)
