# owner: Serena
# The phone screen a referee runs at one arena all day. Shows that arena's
# current series (red team, blue team, arena, match number, which game), a
# Start button that starts the on-screen timer, and the end-of-game result
# entry: winner, tie or double DQ, plus each robot's final zone, with the win
# time taken automatically from Start to the winner tap. Every game goes
# through a confirm step and locks once submitted; after that only the head
# ref can change it, from the admin panel.
#
# Each pairing is a best-of-three series (manual T3/T5): the screen keeps
# offering the next game until one team has two wins. A tied game is simply
# followed by another one, which is the replay the manual calls for.
#
# What happens when things go wrong at the arena:
#   - The page reloads, the phone locks, or the referee swaps phones: the
#     game's start time lives on the server (Match.game_started_at), so the
#     timer picks up where it was instead of restarting from zero.
#   - Wifi drops: nothing is lost. The screen's choices are kept on the phone
#     until they are submitted, a form tapped while offline is held back with
#     a message instead of disappearing into an error page, and tapping
#     Submit twice (once offline, once again) cannot record the game twice,
#     because each submission names the game number it is for.
#   - Start tapped by mistake: "Timer problems" restarts or cancels it.

import logging
import math

from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.db import db
from app.match_state import (
    arena_names,
    current_match_for_arena,
    games_for,
    is_paused,
    next_game_number,
    refresh_series_status,
    series_tally,
)
from app.models import Match, MatchResult, Team, utcnow
from app.referee import referee_bp
from app.security import current_staff_name, staff_required
from app.series import GAME_SECONDS, VALID_OUTCOMES, VALID_ZONES

logger = logging.getLogger(__name__)

# Re-exported: admin/routes.py validates against the same two vocabularies.
__all__ = ["VALID_OUTCOMES", "VALID_ZONES"]


def _arena_slug(arena):
    return arena.replace(" ", "_")


def _arena_url(arena):
    return url_for("referee.arena_screen", arena=_arena_slug(arena))


def _teams_for(match):
    """The red and blue Team rows for a match, either of which may be None."""
    if match is None:
        return None, None
    red = db.session.get(Team, match.red_team_id) if match.red_team_id else None
    blue = db.session.get(Team, match.blue_team_id) if match.blue_team_id else None
    return red, blue


def _get_match_or_404(match_id):
    match = db.session.get(Match, match_id)
    if match is None:
        abort(404)
    return match


def _validate(source):
    """Validate a submitted game result. Returns (values, errors).

    `source` is request.form or request.args - the confirm step round-trips
    through the query string, so a hand-edited URL has to be checked again
    before it can reach the database.
    """
    values = {
        "outcome": (source.get("outcome") or "").strip(),
        "red_final_zone": (source.get("red_final_zone") or "").strip(),
        "blue_final_zone": (source.get("blue_final_zone") or "").strip(),
        "win_time_seconds": None,
        "game_number": None,
    }
    errors = []

    if values["outcome"] not in VALID_OUTCOMES:
        errors.append("Pick a result: RED, BLUE, TIE or DOUBLE DQ.")
    for side in ("red", "blue"):
        if values[side + "_final_zone"] not in VALID_ZONES:
            errors.append("Pick the " + side.upper() + " robot's final zone.")

    raw_game = (source.get("game_number") or "").strip()
    if raw_game.isdigit() and int(raw_game) >= 1:
        values["game_number"] = int(raw_game)
    else:
        errors.append("This screen is out of date. Reload it and enter the result again.")

    raw_win_time = (source.get("win_time_seconds") or "").strip()
    if raw_win_time and values["outcome"] in ("red", "blue"):
        try:
            win_time = float(raw_win_time)
        except ValueError:
            errors.append("Win time must be a number of seconds. Got %r." % raw_win_time)
        else:
            # float() accepts "nan" and "inf". A NaN stores as NULL on SQLite
            # and makes any sort over it non-deterministic on Postgres.
            if not math.isfinite(win_time) or win_time < 0:
                errors.append(
                    "Win time must be a real number of seconds, zero or more. "
                    "Got %r." % raw_win_time
                )
            else:
                values["win_time_seconds"] = round(win_time, 1)

    return values, errors


def _render_screen(match, arena, errors=None, values=None, status=200):
    """The match screen: one series at one arena, whatever state it is in."""
    red, blue = _teams_for(match)
    context = {
        "match": match,
        "arena": arena,
        "arena_slug": _arena_slug(arena) if arena else None,
        "red": red,
        "blue": blue,
        "paused": is_paused(),
        "errors": errors or [],
        "values": values or {},
        "valid_zones": VALID_ZONES,
        "game_seconds": GAME_SECONDS,
    }
    if match is not None:
        tally = series_tally(match)
        started = match.game_started_at
        context.update(
            tally=tally,
            locked=tally.winner is not None,
            game_number=next_game_number(match),
            games=games_for(match.id),
            elapsed=(utcnow() - started).total_seconds() if started else None,
            teams_known=red is not None and blue is not None,
        )
    page = render_template("referee/result_entry.html", **context)
    return page if status == 200 else (page, status)


@referee_bp.route("/")
@staff_required
def current_match():
    """Pick an arena. Each referee phone then stays on its arena's screen."""
    arenas = []
    for arena in arena_names():
        match = current_match_for_arena(arena)
        red, blue = _teams_for(match)
        arenas.append({"name": arena, "slug": _arena_slug(arena), "match": match,
                       "red": red, "blue": blue})
    return render_template("referee/current_match.html", arenas=arenas, paused=is_paused())


@referee_bp.route("/arena/<arena>")
@staff_required
def arena_screen(arena):
    name = arena.replace("_", " ")
    return _render_screen(current_match_for_arena(name), name)


@referee_bp.route("/result/<int:match_id>", methods=["GET", "POST"])
@staff_required
def result_entry(match_id):
    match = _get_match_or_404(match_id)

    if request.method == "POST":
        if series_tally(match).winner is not None:
            return _render_screen(
                match, match.arena,
                errors=["This series is finished. Only the head ref can change it."],
                status=409,
            )

        values, errors = _validate(request.form)
        if errors:
            return _render_screen(match, match.arena, errors=errors, values=values, status=400)

        # On to the confirm step. Nothing is written until it is confirmed.
        return redirect(
            url_for(
                "referee.confirm",
                match_id=match_id,
                game_number=values["game_number"],
                outcome=values["outcome"],
                red_final_zone=values["red_final_zone"],
                blue_final_zone=values["blue_final_zone"],
                win_time_seconds=(
                    "" if values["win_time_seconds"] is None else values["win_time_seconds"]
                ),
            )
        )

    return _render_screen(match, match.arena)


@referee_bp.route("/start/<int:match_id>", methods=["POST"])
@staff_required
def start_game(match_id):
    """Start the timer for this series' next game. Tapping it twice is harmless."""
    match = _get_match_or_404(match_id)
    back = _arena_url(match.arena)

    if is_paused():
        flash("Matches are paused by the head ref. Wait for them to resume.", "warn")
        return redirect(back)
    if match.red_team_id is None or match.blue_team_id is None:
        flash("Both teams for this match are not known yet.", "warn")
        return redirect(back)
    if series_tally(match).winner is not None:
        flash("This series is already finished.", "warn")
        return redirect(back)

    other = Match.query.filter(
        Match.arena == match.arena,
        Match.status == "in_progress",
        Match.id != match.id,
    ).first()
    if other is not None:
        flash(f"Match {other.match_number} is still in progress on {match.arena}. Finish it first.", "warn")
        return redirect(back)

    if match.game_started_at is None:
        match.game_started_at = utcnow()
        match.status = "in_progress"
        db.session.commit()
    return redirect(back)


@referee_bp.route("/restart/<int:match_id>", methods=["POST"])
@staff_required
def restart_timer(match_id):
    """Undo a false start: restart the running game's timer, or cancel it."""
    match = _get_match_or_404(match_id)
    if match.game_started_at is not None:
        if request.form.get("action") == "cancel":
            match.game_started_at = None
            refresh_series_status(match)
            flash("Timer cancelled. Tap Start when the game really starts.", "ok")
        elif is_paused():
            flash("Matches are paused by the head ref. The timer was not restarted.", "warn")
        else:
            match.game_started_at = utcnow()
            flash("Timer restarted from zero.", "ok")
        db.session.commit()
    return redirect(_arena_url(match.arena))


@referee_bp.route("/confirm/<int:match_id>")
@staff_required
def confirm(match_id):
    match = _get_match_or_404(match_id)
    red, blue = _teams_for(match)

    values, errors = _validate(request.args)
    if errors:
        # Reached without going through the form, or the URL was edited by
        # hand. Send them back rather than offering to submit invalid data.
        return redirect(url_for("referee.result_entry", match_id=match_id))

    already = (
        series_tally(match).winner is not None
        or values["game_number"] < next_game_number(match)
    )
    return render_template(
        "referee/confirm.html",
        match=match,
        red=red,
        blue=blue,
        values=values,
        locked=already,
        arena_url=_arena_url(match.arena),
    )


@referee_bp.route("/submit/<int:match_id>", methods=["POST"])
@staff_required
def submit_result(match_id):
    """Write one game's result. The only place a referee creates a MatchResult."""
    match = _get_match_or_404(match_id)
    red, blue = _teams_for(match)

    def _locked(message):
        return (
            render_template(
                "referee/confirm.html",
                match=match, red=red, blue=blue, values=None, locked=True,
                locked_message=message, arena_url=_arena_url(match.arena),
            ),
            409,
        )

    values, errors = _validate(request.form)
    if errors:
        return _render_screen(match, match.arena, errors=errors, values=values, status=400)

    if series_tally(match).winner is not None:
        return _locked("This series is already finished. Only the head ref can change it.")

    expected = next_game_number(match)
    if values["game_number"] < expected:
        # The usual way here: Submit tapped again after a slow or dropped
        # connection, when the first tap had in fact got through.
        return _locked(
            f"Game {values['game_number']} is already recorded. Only the head ref can change it."
        )
    if values["game_number"] > expected:
        return _render_screen(
            match, match.arena,
            errors=["This screen is out of date. Reload it and enter the result again."],
            values=values, status=400,
        )

    # "referee name or arena id" (models.py). The name is whatever the
    # referee typed as their username at the staff prompt, if anything.
    submitted_by = current_staff_name() or match.arena

    db.session.add(
        MatchResult(
            match_id=match.id,
            game_number=values["game_number"],
            outcome=values["outcome"],
            win_time_seconds=values["win_time_seconds"],
            red_final_zone=values["red_final_zone"],
            blue_final_zone=values["blue_final_zone"],
            submitted_by=submitted_by,
        )
    )
    match.game_started_at = None
    tally = refresh_series_status(match)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _locked(
            f"Game {values['game_number']} is already recorded. Only the head ref can change it."
        )
    except SQLAlchemyError as exc:
        db.session.rollback()
        return _render_screen(
            match, match.arena,
            errors=[
                "Could not save the result, so nothing was written: "
                + exc.__class__.__name__ + ". Try again."
            ],
            values=values, status=500,
        )

    if match.phase == "elimination":
        _advance_bracket(match.division)

    flash(_summary(values, tally, red, blue), "ok")
    return redirect(_arena_url(match.arena))


def _advance_bracket(division):
    """Move the bracket on after a bracket game. The result is already saved.

    A failure here must not look like a failed submission - the game is
    recorded either way - so it is logged and left for the head ref's bracket
    page, which re-runs the same step every time it loads.
    """
    from app.bracket.service import sync_division

    try:
        conflicts = sync_division(division)
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("bracket sync failed after a referee submission")
        return
    for conflict in conflicts:
        logger.warning("bracket conflict in %s: %s", division, conflict)


def _summary(values, tally, red, blue):
    game = values["game_number"]
    names = {"red": f"RED ({red.name})" if red else "RED", "blue": f"BLUE ({blue.name})" if blue else "BLUE"}
    if values["outcome"] in ("red", "blue"):
        what = f"{names[values['outcome']]} won game {game}."
    elif values["outcome"] == "tie":
        what = f"Game {game} was a tie, so it is replayed."
    else:
        what = f"Game {game}: double DQ, a loss for both teams."
    if tally.winner:
        return f"{what} {names[tally.winner]} wins the series {max(tally.red_wins, tally.blue_wins)}-{min(tally.red_wins, tally.blue_wins)}."
    return f"{what} Series is RED {tally.red_wins} - {tally.blue_wins} BLUE."
