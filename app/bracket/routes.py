# owner: Krish S
# Renders the elimination bracket. Seeds from final qualification rankings,
# advances winners as results arrive. A tie inserts a replay game into the
# series instead of advancing anyone (see app/series.py).
#
#   /bracket/<division>          public, auto-refreshing, big-screen readable
#   /bracket/<division>/manage   head ref: pick single/double and how many
#                                teams advance, preview the seeds, build it;
#                                once built, change who is in each seed,
#                                rebuild with another size, and open any
#                                bracket series to fix or award it

from flask import flash, redirect, render_template, request, url_for

from app.bracket import bracket_bp, logic
from app.bracket.service import (
    BracketError,
    bracket_games_played,
    bracket_view,
    build_bracket,
    get_config,
    qualification_unfinished,
    rebuild_bracket,
    reset_bracket,
    seeds_for,
    set_seed,
    sync_division,
)
from app.db import db
from app.match_state import games_for, series_tally
from app.models import Match, Team
from app.rankings.logic import get_division_rankings
from app.security import current_staff_name, head_ref_required

# The public page reloads itself so the bracket advances on its own as
# referees submit results.
REFRESH_SECONDS = 10


def _division_name(slug):
    return slug.replace("_", " ")


@bracket_bp.route("/<division>")
def view_bracket(division):
    name = _division_name(division)
    view = bracket_view(name)
    preview = None
    if view is None:
        # Not built yet: show who would be seeded if qualification ended now.
        preview = get_division_rankings(name)
    return render_template(
        "bracket/bracket.html",
        division=name,
        division_slug=division,
        view=view,
        preview=preview,
        refresh_seconds=REFRESH_SECONDS,
    )


@bracket_bp.route("/<division>/manage")
@head_ref_required
def manage(division):
    name = _division_name(division)
    config = get_config(name)
    # Every visit re-runs the advance step, so a bracket that missed one (a
    # referee's submission landed while the database hiccuped) catches up.
    conflicts = sync_division(name) if config else []
    standings = get_division_rankings(name)
    teams = {t.id: t for t in Team.query.all()}
    team_by_number = {t.team_number: t for t in teams.values()}
    rank_of = {team_by_number[row["team_number"]].id: row["rank"] for row in standings}

    seed_rows, series_rows = [], []
    if config:
        seed_rows = [
            {"seed": i + 1, "team": teams.get(team_id)}
            for i, team_id in enumerate(seeds_for(config))
        ]
        titles = {node.key: node.title for node in logic.build_nodes(len(seed_rows), config.format)}
        bracket_matches = (
            Match.query.filter_by(division=name, phase="elimination")
            .order_by(Match.match_number)
            .all()
        )
        for match in bracket_matches:
            key = (match.bracket_side or "W", match.bracket_round, match.bracket_slot)
            series_rows.append({
                "match": match,
                "title": titles.get(key, "Bracket"),
                "red": teams.get(match.red_team_id),
                "blue": teams.get(match.blue_team_id),
                "tally": series_tally(match),
                "played": bool(games_for(match.id)),
            })

    # Every team, best-ranked first, for the "who is in this seed" choices.
    # Teams with no qualification series (no-shows) come last, unranked.
    choices = sorted(teams.values(), key=lambda t: (rank_of.get(t.id, 10**6), t.team_number))
    return render_template(
        "bracket/manage.html",
        division=name,
        division_slug=division,
        config=config,
        conflicts=conflicts,
        standings=standings,
        unfinished=qualification_unfinished(name),
        default_size=min(8, len(standings)),
        formats=logic.FORMATS,
        seed_rows=seed_rows,
        series_rows=series_rows,
        choices=choices,
        rank_of=rank_of,
        games_played=bool(config) and bracket_games_played(name),
    )


def _size_from(form):
    raw_size = (form.get("size") or "").strip()
    if not raw_size.isdigit():
        raise BracketError("Enter how many teams advance to the bracket.")
    return int(raw_size)


@bracket_bp.route("/<division>/build", methods=["POST"])
@head_ref_required
def build(division):
    name = _division_name(division)
    fmt = request.form.get("format", logic.SINGLE)
    try:
        build_bracket(
            name, fmt, _size_from(request.form), current_staff_name() or "head ref",
            allow_unfinished=request.form.get("allow_unfinished") == "1",
        )
    except BracketError as exc:
        flash(str(exc), "error")
        return redirect(url_for("bracket.manage", division=division))
    flash("Bracket built. First-round series are on the referee screens.", "ok")
    return redirect(url_for("bracket.manage", division=division))


@bracket_bp.route("/<division>/rebuild", methods=["POST"])
@head_ref_required
def rebuild(division):
    """A different number of teams (or format), before any bracket game."""
    name = _division_name(division)
    fmt = request.form.get("format", logic.SINGLE)
    try:
        size = _size_from(request.form)
        rebuild_bracket(
            name, fmt, size, current_staff_name() or "head ref",
            allow_unfinished=request.form.get("allow_unfinished") == "1",
        )
    except BracketError as exc:
        flash(str(exc), "error")
    else:
        flash(f"Bracket rebuilt with {size} teams, seeded from the standings.", "ok")
    return redirect(url_for("bracket.manage", division=division))


@bracket_bp.route("/<division>/seed", methods=["POST"])
@head_ref_required
def change_seed(division):
    """Put a different team in one seed of the built bracket."""
    name = _division_name(division)
    raw_seed = (request.form.get("seed") or "").strip()
    raw_team = (request.form.get("team_id") or "").strip()
    try:
        if not (raw_seed.isdigit() and raw_team.isdigit()):
            raise BracketError("Pick a seed and a team.")
        changed = set_seed(name, int(raw_seed), int(raw_team))
    except BracketError as exc:
        flash(str(exc), "error")
    else:
        if changed:
            team = db.session.get(Team, int(raw_team))
            flash(f"Seed {raw_seed} is now {team.team_number} {team.name}.", "ok")
    return redirect(url_for("bracket.manage", division=division))


@bracket_bp.route("/<division>/reset", methods=["POST"])
@head_ref_required
def reset(division):
    try:
        reset_bracket(_division_name(division))
    except BracketError as exc:
        flash(str(exc), "error")
    else:
        flash("Bracket removed. It can be built again.", "ok")
    return redirect(url_for("bracket.manage", division=division))
