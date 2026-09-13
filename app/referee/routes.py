# owner: Serena
# Shows the current match, a start button, an on-screen timer, and the
# end-of-match result entry (winner/tie/double DQ + final zones), with a
# confirm step before submitting. Locked after submission.

import math

from flask import render_template, request, redirect, url_for, abort
from sqlalchemy.exc import SQLAlchemyError

from app.db import db
from app.models import Match, MatchResult, Team
from app.referee import referee_bp

# The four values models.py already fixes for MatchResult.outcome. Not a new
# vocabulary - just enforcing the one the data contract already names.
VALID_OUTCOMES = ("red", "blue", "tie", "double_dq")

# The four options this page has always offered in its <select>.
#
# UNRESOLVED: tiebreak.py's ZONE_POINTS recognises "Out", "Band",
# "Ring 2".."Ring 6" and "Plateau", and scores anything else 0 - so every
# result written here contributes 0 ring points and tiebreak tier 3 stays
# dead. Agreeing one vocabulary between this page and tiebreak.py is the
# open item at the top of tiebreak.py. It is deliberately NOT decided here:
# changing these strings quietly would rewrite the standings rules.
VALID_ZONES = ("Center", "Red Zone", "Blue Zone", "Off Arena")


def _teams_for(match):
    """The red and blue Team rows for a match, either of which may be None."""
    if match is None:
        return None, None
    red = db.session.get(Team, match.red_team_id) if match.red_team_id else None
    blue = db.session.get(Team, match.blue_team_id) if match.blue_team_id else None
    return red, blue


def _existing_result(match_id):
    return MatchResult.query.filter_by(match_id=match_id).first()


def _validate(source):
    """Validate a submitted result. Returns (values, errors).

    `source` is request.form or request.args - the confirm step round-trips
    through the query string, so a hand-edited URL has to be checked again
    before it can reach the database.
    """
    values = {
        "outcome": (source.get("outcome") or "").strip(),
        "red_final_zone": (source.get("red_final_zone") or "").strip(),
        "blue_final_zone": (source.get("blue_final_zone") or "").strip(),
        "win_time_seconds": None,
    }
    errors = []

    if values["outcome"] not in VALID_OUTCOMES:
        errors.append("Pick a winner: RED, BLUE, TIE or DOUBLE DQ.")
    for side in ("red", "blue"):
        if values[side + "_final_zone"] not in VALID_ZONES:
            errors.append(
                side.capitalize()
                + " final zone must be one of: "
                + ", ".join(VALID_ZONES)
                + "."
            )

    raw_win_time = (source.get("win_time_seconds") or "").strip()
    if raw_win_time:
        try:
            win_time = float(raw_win_time)
        except ValueError:
            errors.append("Win time must be a number of seconds. Got %r." % raw_win_time)
        else:
            # float() accepts "nan" and "inf". A NaN stores as NULL on SQLite
            # and makes the standings sort non-deterministic on Postgres.
            if not math.isfinite(win_time) or win_time < 0:
                errors.append(
                    "Win time must be a real number of seconds, zero or more. "
                    "Got %r." % raw_win_time
                )
            else:
                values["win_time_seconds"] = win_time

    return values, errors


@referee_bp.route("/")
def current_match():
    match = (
        Match.query.filter_by(status="in_progress")
        .order_by(Match.match_number.asc())
        .first()
    )
    red, blue = _teams_for(match)
    return render_template("referee/current_match.html", match=match, red=red, blue=blue)


@referee_bp.route("/result/<int:match_id>", methods=["GET", "POST"])
def result_entry(match_id):
    # TODO(Serena): drive win_time_seconds from the on-screen timer (start
    # button tap to winner tap) instead of leaving it blank. The hidden
    # win_time_seconds field in the template is where it goes.
    match = Match.query.filter_by(id=match_id).first()
    if match is None:
        abort(404)

    red, blue = _teams_for(match)
    result = _existing_result(match_id)

    def _render(errors=None, values=None, status=200):
        page = render_template(
            "referee/result_entry.html",
            match=match,
            red=red,
            blue=blue,
            result=result,
            locked=result is not None,
            errors=errors or [],
            values=values or {},
            valid_zones=VALID_ZONES,
        )
        return page if status == 200 else (page, status)

    if request.method == "POST":
        if result is not None:
            return _render(
                errors=[
                    "This match already has a result. Only the head ref can change it."
                ],
                status=409,
            )

        values, errors = _validate(request.form)
        if errors:
            return _render(errors=errors, values=values, status=400)

        # On to the confirm step. Nothing is written until it is confirmed.
        return redirect(
            url_for(
                "referee.confirm",
                match_id=match_id,
                outcome=values["outcome"],
                red_final_zone=values["red_final_zone"],
                blue_final_zone=values["blue_final_zone"],
                win_time_seconds=(
                    "" if values["win_time_seconds"] is None else values["win_time_seconds"]
                ),
            )
        )

    return _render()


@referee_bp.route("/confirm/<int:match_id>")
def confirm(match_id):
    match = Match.query.filter_by(id=match_id).first()
    if match is None:
        abort(404)

    red, blue = _teams_for(match)
    result = _existing_result(match_id)
    if result is not None:
        return render_template(
            "referee/confirm.html",
            match=match,
            red=red,
            blue=blue,
            values=None,
            result=result,
            locked=True,
        )

    values, errors = _validate(request.args)
    if errors:
        # Reached without going through the form, or the URL was edited by
        # hand. Send them back rather than offering to submit invalid data.
        return redirect(url_for("referee.result_entry", match_id=match_id))

    return render_template(
        "referee/confirm.html",
        match=match,
        red=red,
        blue=blue,
        values=values,
        result=None,
        locked=False,
    )


@referee_bp.route("/submit/<int:match_id>", methods=["POST"])
def submit_result(match_id):
    """Write the result. This is the only place a MatchResult is created."""
    match = Match.query.filter_by(id=match_id).first()
    if match is None:
        abort(404)

    red, blue = _teams_for(match)
    result = _existing_result(match_id)

    if result is not None:
        return (
            render_template(
                "referee/confirm.html",
                match=match,
                red=red,
                blue=blue,
                values=None,
                result=result,
                locked=True,
            ),
            409,
        )

    def _back_to_form(errors, values, status):
        return (
            render_template(
                "referee/result_entry.html",
                match=match,
                red=red,
                blue=blue,
                result=None,
                locked=False,
                errors=errors,
                values=values,
                valid_zones=VALID_ZONES,
            ),
            status,
        )

    values, errors = _validate(request.form)
    if errors:
        return _back_to_form(errors, values, 400)

    # models.py:92 - "referee name or arena id". There is no auth layer, so
    # the arena is the most specific thing actually known here.
    submitted_by = (request.form.get("submitted_by") or "").strip() or match.arena

    db.session.add(
        MatchResult(
            match_id=match.id,
            outcome=values["outcome"],
            win_time_seconds=values["win_time_seconds"],
            red_final_zone=values["red_final_zone"],
            blue_final_zone=values["blue_final_zone"],
            submitted_by=submitted_by,
        )
    )
    match.status = "complete"

    try:
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        return _back_to_form(
            [
                "Could not save the result, so nothing was written: "
                + exc.__class__.__name__
                + ". Try again."
            ],
            values,
            500,
        )

    return redirect(url_for("referee.result_entry", match_id=match_id))
