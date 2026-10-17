# owner: Krish S
# Renders the elimination bracket. Seeds from final qualification rankings,
# advances winners as results arrive. A tie inserts a replay game into the
# series instead of advancing anyone (see app/series.py).
#
#   /bracket/<division>          public, auto-refreshing, big-screen readable
#   /bracket/<division>/manage   head ref: pick single/double and how many
#                                teams advance, preview the seeds, build it

from flask import flash, redirect, render_template, request, url_for

from app.bracket import bracket_bp, logic
from app.bracket.service import (
    BracketError,
    bracket_view,
    build_bracket,
    get_config,
    qualification_unfinished,
    reset_bracket,
    sync_division,
)
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
    )


@bracket_bp.route("/<division>/build", methods=["POST"])
@head_ref_required
def build(division):
    name = _division_name(division)
    fmt = request.form.get("format", logic.SINGLE)
    raw_size = (request.form.get("size") or "").strip()
    try:
        if not raw_size.isdigit():
            raise BracketError("Enter how many teams advance to the bracket.")
        build_bracket(name, fmt, int(raw_size), current_staff_name() or "head ref")
    except BracketError as exc:
        flash(str(exc), "error")
        return redirect(url_for("bracket.manage", division=division))
    flash("Bracket built. First-round series are on the referee screens.", "ok")
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
