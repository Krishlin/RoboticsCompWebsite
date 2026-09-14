# owner: Serena
# Shows the current match, a start button, an on-screen timer, and the
# end-of-match result entry (winner/tie/double DQ + final zones), with a
# confirm step before submitting. Locked after submission.

from flask import abort, redirect, render_template, request, url_for

from app import fake_data
from app.fake_data import CURRENT_MATCH, MATCHES_BY_ID, get_team
from . import referee_bp


@referee_bp.route("/")
def current_match():
  match = fake_data.CURRENT_MATCH
  red = get_team(match["red_team_number"]) if match else None
  blue = get_team(match["blue_team_number"]) if match else None
  return render_template(
      "referee/current_match.html", match=match, red=red, blue=blue
  )


@referee_bp.route("/result/<int:match_id>", methods=["GET", "POST"])
def result_entry(match_id):
  match = MATCHES_BY_ID.get(match_id)
  if not match:
    abort(404)

  # Check if match is already locked
  if match.get("is_locked", False):
    return render_template(
        "referee/result_entry.html", match=match, locked=True
    )

  if request.method == "POST":
    # Save submitted data
    match["winner"] = request.form.get("winner")
    match["win_time_seconds"] = request.form.get("win_time_seconds")
    match["red_zone"] = request.form.get("red_zone")
    match["blue_zone"] = request.form.get("blue_zone")

    # Lock the match upon submission
    match["is_locked"] = True

    # Automatically advance to the next match in line
    next_match_id = match_id + 1
    if next_match_id in MATCHES_BY_ID:
      fake_data.CURRENT_MATCH = MATCHES_BY_ID[next_match_id]

    return redirect(url_for("referee.current_match"))

  red = get_team(match["red_team_number"]) if match else None
  blue = get_team(match["blue_team_number"]) if match else None
  return render_template(
      "referee/result_entry.html", match=match, red=red, blue=blue, locked=False
  )


@referee_bp.route("/head-ref/unlock/<int:match_id>", methods=["POST"])
def unlock_match(match_id):
  # Head Referee override route to unlock a match
  match = MATCHES_BY_ID.get(match_id)
  if match:
    match["is_locked"] = False
  return redirect(url_for("referee.result_entry", match_id=match_id))


@referee_bp.route("/confirm/<int:match_id>")
def confirm(match_id):
  match = MATCHES_BY_ID.get(match_id)
  return render_template("referee/confirm.html", match=match)