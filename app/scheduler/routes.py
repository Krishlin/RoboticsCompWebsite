# owner: Shaurya
# Generates and displays the qualification schedule: full list, per-arena,
# and per-team views.

from flask import render_template

from app.fake_data import MATCHES, get_team
from app.scheduler import scheduler_bp


def _with_team_names(matches):
    """Attach red/blue team names to each match dict for display."""
    enriched = []
    for match in matches:
        red = get_team(match["red_team_number"])
        blue = get_team(match["blue_team_number"])
        enriched.append({
            **match,
            "red_team_name": red["name"] if red else "TBD",
            "blue_team_name": blue["name"] if blue else "TBD",
        })
    return enriched


@scheduler_bp.route("/")
def schedule_full():
    return render_template("scheduler/schedule_full.html", matches=_with_team_names(MATCHES))


@scheduler_bp.route("/arena/<arena>")
def schedule_by_arena(arena):
    arena_name = arena.replace("_", " ")
    matches = [m for m in MATCHES if m["arena"] == arena_name]
    return render_template(
        "scheduler/schedule_by_arena.html",
        arena=arena_name,
        matches=_with_team_names(matches),
    )


@scheduler_bp.route("/team/<int:team_number>")
def schedule_by_team(team_number):
    matches = [
        m for m in MATCHES
        if m["red_team_number"] == team_number or m["blue_team_number"] == team_number
    ]
    return render_template(
        "scheduler/schedule_by_team.html",
        team_number=team_number,
        matches=_with_team_names(matches),
    )
