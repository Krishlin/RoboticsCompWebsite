# owner: Yueyue
# Head ref panel: edit any game result (writing an AuditEntry every time),
# order a replay of a game, pause and resume the event, and export
# everything to CSV at the end.
#
# Every route is behind head_ref_required. The head ref types their name as
# the username at that prompt, and that name is what the audit log records
# as "changed by" (self-reported; see app/security.py).
#
# A Match is a best-of-three series and each game is a MatchResult (see
# models.py). Editing or voiding a game can change who won the series, so
# every write here re-derives the series status, and a bracket series also
# moves the bracket on - or is refused, if a later bracket series has
# already been played on the strength of the old result.

import csv
import io
import logging
import math
import zipfile
from datetime import datetime, timedelta

from flask import Response, abort, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.admin import admin_bp
from app.db import db
from app.formatting import clock
from app.match_state import (
    games_for,
    is_paused,
    next_game_number,
    refresh_series_status,
    series_tally,
)
from app.models import (
    AuditEntry,
    BracketConfig,
    Inspection,
    Match,
    MatchResult,
    ScheduleState,
    Team,
    utcnow,
)
from app.roster import MAX_BYTES, RosterError, decode, import_roster, parse_roster
from app.security import current_staff_name, head_ref_required
from app.series import VALID_OUTCOMES, VALID_ZONES, WINS_NEEDED

logger = logging.getLogger(__name__)

EDITABLE_FIELDS = ("outcome", "win_time_seconds", "red_final_zone", "blue_final_zone")

# The furthest one shift may move the schedule. A typed 600 for 60 should be
# refused, not obeyed.
MAX_SHIFT_MINUTES = 240


@admin_bp.before_request
@head_ref_required
def _require_head_ref():
    """Every page in this blueprint is the head ref's."""
    return None


def _current_admin_name():
    # Whatever the head ref typed as their username at the passcode prompt.
    # Only missing when no passcode is configured at all (a laptop).
    return current_staff_name() or "head ref"


def _team_numbers():
    return {t.id: t.team_number for t in Team.query.all()}


def _series_rows():
    """Every series with its teams and score, for the dashboard."""
    matches = Match.query.order_by(Match.division, Match.match_number).all()
    teams = {t.id: t for t in Team.query.all()}
    rows = []
    for match in matches:
        games = games_for(match.id)
        tally = series_tally(match)
        rows.append({
            "match": match,
            "red": teams.get(match.red_team_id),
            "blue": teams.get(match.blue_team_id),
            "tally": tally,
            "games": games,
        })
    return rows


def _read_schedule_state():
    """The global schedule state, for read-only handlers.

    Returns an unsaved default when the row doesn't exist yet. Rendering a
    page must never write: /admin/ used to create the row on GET, so a
    browser prefetch or a crawler mutated the database, and two dashboards
    loading at once both inserted id=1 and every loser got a 500.
    """
    state = ScheduleState.query.filter_by(id=1).first()
    if state is None:
        return ScheduleState(id=1, is_paused=False, changed_by=None)
    return state


def _get_or_create_schedule_state():
    """Get the global schedule state, creating the single row if needed.

    Only for handlers that are about to change it. The insert races against
    other requests doing the same thing, so a duplicate id=1 is expected and
    means someone else won — re-read rather than failing the request.
    """
    state = ScheduleState.query.filter_by(id=1).first()
    if state is not None:
        return state

    state = ScheduleState(id=1, is_paused=False, changed_by=None)
    db.session.add(state)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        state = ScheduleState.query.filter_by(id=1).first()
        if state is None:
            raise
    return state


def _unstarted_timed_matches():
    """Every match no game has started in that has a time, soonest first.

    Bracket series have no time (scheduled_time is None), so they never move.
    """
    return (
        Match.query.filter(Match.status == "scheduled", Match.scheduled_time.isnot(None))
        .order_by(Match.scheduled_time, Match.match_number)
        .all()
    )


@admin_bp.route("/")
def dashboard():
    state = _read_schedule_state()
    upcoming = _unstarted_timed_matches()
    paused_minutes = None
    if state.is_paused and state.changed_at is not None:
        paused_minutes = int((utcnow() - state.changed_at).total_seconds() // 60)
    return render_template(
        "admin/dashboard.html",
        series_rows=_series_rows(),
        schedule_state=state,
        brackets=BracketConfig.query.all(),
        admin_name=_current_admin_name(),
        exports=EXPORTS,
        paused=is_paused(),
        next_match=upcoming[0] if upcoming else None,
        upcoming_count=len(upcoming),
        paused_minutes=paused_minutes,
        max_shift=MAX_SHIFT_MINUTES,
        team_count=Team.query.count(),
    )


@admin_bp.route("/shift-schedule", methods=["POST"])
def shift_schedule():
    """Move every match that hasn't started by the same amount.

    For a delay: the event runs late, so everything still to come moves back
    and the schedule, the team pages and the big screen tell the truth again.
    Finished and running series keep their times, and everything that moves
    moves together, so the gaps between a team's series stay as generated.
    """
    # No #timing anchor: the confirmation is flashed at the top of the page,
    # and the card is right under it anyway.
    back = redirect(url_for("admin.dashboard"))
    matches = _unstarted_timed_matches()
    if not matches:
        flash("There are no upcoming matches with a time to move.", "warn")
        return back
    first = matches[0]

    next_start = (request.form.get("next_start") or "").strip()
    if next_start:
        try:
            wanted = datetime.strptime(next_start, "%H:%M").time()
        except ValueError:
            flash(f"Enter the time like 10:45, not {next_start!r}.", "error")
            return back
        delta = datetime.combine(first.scheduled_time.date(), wanted) - first.scheduled_time
    else:
        raw = (request.form.get("minutes") or "").strip()
        try:
            typed = int(raw)
        except ValueError:
            flash(f"Enter a whole number of minutes, not {raw!r}.", "error")
            return back
        # Clamped before it reaches timedelta, which raises OverflowError on
        # a long enough string of digits; the limit check below then refuses it.
        delta = timedelta(minutes=max(-10_000, min(typed, 10_000)))

    minutes = int(delta.total_seconds() // 60)
    if minutes == 0:
        flash("Nothing moved: that is the schedule's current time.", "warn")
        return back
    if abs(minutes) > MAX_SHIFT_MINUTES:
        flash(
            f"Not moved: {abs(minutes)} minutes is more than the {MAX_SHIFT_MINUTES}-minute "
            "limit for one shift. Check the number, or shift in two steps.",
            "error",
        )
        return back

    old_first = first.scheduled_time
    for match in matches:
        match.scheduled_time += delta
    try:
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        flash(f"Could not move the schedule, so nothing changed: {exc.__class__.__name__}.", "error")
        return back

    logger.info(
        "schedule shifted %+d minutes by %s (%d matches, match %s %s -> %s)",
        minutes, _current_admin_name(), len(matches), first.match_number,
        clock(old_first), clock(first.scheduled_time),
    )
    flash(
        f"Moved {len(matches)} match{'es' if len(matches) != 1 else ''} "
        f"{abs(minutes)} minutes {'later' if minutes > 0 else 'earlier'}. "
        f"Match {first.match_number} is now at {clock(first.scheduled_time)}.",
        "ok",
    )
    return back


@admin_bp.route("/import-teams", methods=["GET", "POST"])
def import_teams():
    """Load the registered teams from the registration sheet's CSV export."""
    summary = None
    problems = []
    if request.method == "POST":
        upload = request.files.get("roster")
        if upload is None or not upload.filename:
            problems = ["Choose the sheet's .csv file first."]
        else:
            try:
                rows = parse_roster(decode(upload.read(MAX_BYTES + 1)))
                summary = import_roster(
                    rows, remove_missing=request.form.get("remove_missing") == "1"
                )
            except RosterError as exc:
                problems = exc.problems
        if summary is not None:
            logger.info(
                "roster imported by %s: %d added, %d updated, %d removed",
                _current_admin_name(), len(summary.added), len(summary.updated),
                len(summary.removed),
            )
    page = render_template(
        "admin/import_teams.html",
        summary=summary,
        problems=problems,
        team_count=Team.query.count(),
        schedule_exists=Match.query.first() is not None,
    )
    return (page, 400) if problems else page


def _parse_win_time(raw_value):
    """Validate the win_time_seconds form field.

    Returns (value, error_message); exactly one of the two is None. float()
    accepts "nan" and "inf", and SQLite stores a NaN as NULL — so an audit
    entry would record a new_value the database does not contain, and on
    Postgres a stored NaN makes any sort over it non-deterministic because
    NaN compares false against everything.
    """
    if raw_value in (None, ""):
        return None, None
    try:
        value = float(raw_value)
    except ValueError:
        return None, f"Win time must be a number. Got {raw_value!r}."
    if not math.isfinite(value):
        return None, f"Win time must be a real number. Got {raw_value!r}."
    if value < 0:
        return None, f"Win time cannot be negative. Got {raw_value!r}."
    return value, None


def _validated_game_values(form):
    """The four editable fields of a game from a form. Returns (values, error)."""
    missing = [name for name in ("outcome", "red_final_zone", "blue_final_zone")
               if form.get(name) is None]
    if missing:
        return None, "Missing form field(s): " + ", ".join(missing) + "."
    # Server-side, because form controls can be bypassed by a direct POST.
    # Same vocabulary the referee page enforces.
    if form.get("outcome") not in VALID_OUTCOMES:
        return None, "Outcome must be one of: " + ", ".join(VALID_OUTCOMES) + "."
    for side in ("red", "blue"):
        if form.get(side + "_final_zone") not in VALID_ZONES:
            return None, (side.capitalize() + " final zone must be one of: "
                          + ", ".join(VALID_ZONES) + ".")
    win_time, error = _parse_win_time(form.get("win_time_seconds"))
    if error:
        return None, error
    if form.get("outcome") not in ("red", "blue"):
        win_time = None  # there is no winner to time
    return {
        "outcome": form.get("outcome"),
        "win_time_seconds": win_time,
        "red_final_zone": form.get("red_final_zone"),
        "blue_final_zone": form.get("blue_final_zone"),
    }, None


def _audit(match_id, field, old_value, new_value):
    db.session.add(AuditEntry(
        match_id=match_id,
        changed_by=_current_admin_name(),
        field=field[:50],
        old_value=None if old_value is None else str(old_value)[:200],
        new_value=None if new_value is None else str(new_value)[:200],
    ))


def _commit_series_change(match):
    """Re-derive the series, check the bracket, and commit. Returns an error or None.

    Runs inside the request's transaction: anything that does not add up is
    rolled back whole, so the database never holds an edit without its audit
    entries, or a bracket built on a result that no longer exists.
    """
    refresh_series_status(match)
    db.session.flush()

    if match.phase == "elimination":
        from app.bracket.service import sync_division

        conflicts = sync_division(match.division, dry_run=True)
        if conflicts:
            db.session.rollback()
            return (
                "Not saved: this changes who advanced from this series, and a later "
                "bracket series has already been played. " + " ".join(conflicts)
            )

    try:
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        return f"Could not save the change, so nothing was committed: {exc.__class__.__name__}."

    if match.phase == "elimination":
        from app.bracket.service import sync_division

        sync_division(match.division)
    return None


def _render_series(match, error_message=None, status=200):
    tally = series_tally(match)
    page = render_template(
        "admin/edit_result.html",
        match=match,
        red=db.session.get(Team, match.red_team_id) if match.red_team_id else None,
        blue=db.session.get(Team, match.blue_team_id) if match.blue_team_id else None,
        games=games_for(match.id),
        tally=tally,
        next_game=next_game_number(match),
        valid_zones=VALID_ZONES,
        error_message=error_message,
    )
    return page if status == 200 else (page, status)


@admin_bp.route("/edit/<int:match_id>", methods=["GET", "POST"])
def edit_result(match_id):
    """One series: every game, editable, plus adding a game the referee could not."""
    match = db.session.get(Match, match_id)
    if match is None:
        abort(404)
    if request.method == "GET":
        return _render_series(match)

    game_id = request.form.get("game_id")
    values, error = _validated_game_values(request.form)
    if error:
        return _render_series(match, error, 400)

    if game_id:
        game = db.session.get(MatchResult, int(game_id)) if game_id.isdigit() else None
        if game is None or game.match_id != match.id:
            abort(404)
        label = f"game {game.game_number} "
        changed = False
        for field in EDITABLE_FIELDS:
            old_value = getattr(game, field)
            if old_value != values[field]:
                _audit(match.id, label + field, old_value, values[field])
                setattr(game, field, values[field])
                changed = True
        if not changed:
            return redirect(url_for("admin.edit_result", match_id=match.id))
    else:
        # The head ref entering a game the referee could not (a phone died).
        if match.red_team_id is None or match.blue_team_id is None:
            return _render_series(match, "Both teams must be known before a game is recorded.", 400)
        if series_tally(match).winner is not None:
            return _render_series(match, "This series is already decided. Edit a game instead.", 400)
        number = next_game_number(match)
        db.session.add(MatchResult(
            match_id=match.id,
            game_number=number,
            submitted_by=_current_admin_name(),
            **values,
        ))
        match.game_started_at = None
        match.game_paused_at = None
        for field in EDITABLE_FIELDS:
            _audit(match.id, f"game {number} {field}", None, values[field])

    error = _commit_series_change(match)
    if error:
        return _render_series(match, error, 409)
    flash("Saved.", "ok")
    return redirect(url_for("admin.edit_result", match_id=match.id))


@admin_bp.route("/game/<int:game_id>/void", methods=["POST"])
def void_game(game_id):
    """Order a replay of one game (interference, field failure, a bad call).

    The game stays in the record, marked voided, and stops counting; the
    series then needs another game, which the referee screen offers next.
    Un-voiding is the same button, for a replay ordered by mistake.
    """
    game = db.session.get(MatchResult, game_id)
    if game is None:
        abort(404)
    match = db.session.get(Match, game.match_id)
    new_value = not game.voided
    _audit(match.id, f"game {game.game_number} voided", game.voided, new_value)
    game.voided = new_value

    error = _commit_series_change(match)
    if error:
        return _render_series(match, error, 409)
    flash(
        f"Game {game.game_number} voided: the series needs a replay game."
        if new_value else f"Game {game.game_number} counts again.",
        "ok",
    )
    return redirect(url_for("admin.edit_result", match_id=match.id))


@admin_bp.route("/award/<int:match_id>", methods=["POST"])
def award_series(match_id):
    """Give a series to one team: a forfeit, a no-show, or the head ref's call.

    The team ends 2-0 up. Games it already won stay; every other counted game
    (the opponent's wins, ties, double DQs) is voided, not deleted, and forfeit
    wins are added until it has two, which is how the manual scores a forfeit
    (a match win for the opponent). In the bracket the winner moves on, unless
    a later series has already been played on the old result, in which case
    nothing is saved.
    """
    match = db.session.get(Match, match_id)
    if match is None:
        abort(404)
    side = request.form.get("side")
    if side not in ("red", "blue"):
        abort(400)
    if match.red_team_id is None or match.blue_team_id is None:
        return _render_series(match, "Both teams must be known before a series is awarded.", 400)

    before = series_tally(match).winner
    if before == side:
        flash(f"{side.capitalize()} has already won this series.", "warn")
        return redirect(url_for("admin.edit_result", match_id=match.id))

    for game in games_for(match.id, include_voided=False):
        if game.outcome != side:
            _audit(match.id, f"game {game.game_number} voided", False, True)
            game.voided = True
    db.session.flush()

    tally = series_tally(match)
    wins = tally.red_wins if side == "red" else tally.blue_wins
    number = next_game_number(match)
    while wins < WINS_NEEDED:
        db.session.add(MatchResult(
            match_id=match.id,
            game_number=number,
            outcome=side,
            win_time_seconds=None,
            red_final_zone="Plateau" if side == "red" else "Ring-out",
            blue_final_zone="Plateau" if side == "blue" else "Ring-out",
            submitted_by=f"{_current_admin_name()} (awarded)",
        ))
        _audit(match.id, f"game {number} outcome", None, f"{side} (awarded)")
        number += 1
        wins += 1
    _audit(match.id, "series awarded to", before or "undecided", side)
    match.game_started_at = None
    match.game_paused_at = None

    error = _commit_series_change(match)
    if error:
        return _render_series(match, error, 409)
    winner = db.session.get(Team, match.red_team_id if side == "red" else match.blue_team_id)
    flash(f"Series awarded to {winner.team_number} {winner.name}.", "ok")
    return redirect(url_for("admin.edit_result", match_id=match.id))


@admin_bp.route("/replay", methods=["POST"])
def insert_replay_match():
    """Dashboard shortcut: replay the most recent counted game of a series."""
    raw = request.form.get("original_match_id") or ""
    if not raw.isdigit():
        abort(400)
    match = db.session.get(Match, int(raw))
    if match is None:
        abort(404)
    counted = games_for(match.id, include_voided=False)
    if not counted:
        abort(400, description=f"Match {match.match_number} has no game to replay yet.")
    return void_game(counted[-1].id)


@admin_bp.route("/audit-log")
def audit_log():
    entries = AuditEntry.query.order_by(AuditEntry.changed_at.desc()).all()
    numbers = {m.id: m.match_number for m in Match.query.all()}
    return render_template("admin/audit_log.html", entries=entries, match_numbers=numbers)


@admin_bp.route("/match/<int:match_id>/history")
def match_history(match_id):
    match = db.session.get(Match, match_id)
    if match is None:
        abort(404)
    entries = (
        AuditEntry.query.filter_by(match_id=match_id)
        .order_by(AuditEntry.changed_at.desc())
        .all()
    )
    return render_template("admin/match_history.html", match=match, entries=entries)


@admin_bp.route("/pause", methods=["POST"])
def pause_schedule():
    """Pause the event. See ScheduleState in models.py for what that means."""
    state = _get_or_create_schedule_state()
    state.is_paused = True
    state.changed_by = _current_admin_name()
    state.changed_at = utcnow()
    db.session.commit()
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/resume", methods=["POST"])
def resume_schedule():
    state = _get_or_create_schedule_state()
    state.is_paused = False
    state.changed_by = _current_admin_name()
    state.changed_at = utcnow()
    db.session.commit()
    return redirect(url_for("admin.dashboard"))


# --- CSV export --------------------------------------------------------------
# One CSV per kind of record, plus all of them in one zip for the end of the
# event. Written with a byte-order mark: without it Excel opens UTF-8 as the
# local code page and mangles any accented name, which is the difference
# between a file that downloads and a file that is actually usable.

def _iso(value):
    return value.isoformat(sep=" ", timespec="seconds") if value else ""


def _yes(value):
    return "yes" if value else "no"


def _csv_teams():
    latest = {}
    attempts = {}
    for insp in Inspection.query.order_by(Inspection.inspected_at).all():
        latest[insp.team_id] = insp
        attempts[insp.team_id] = attempts.get(insp.team_id, 0) + 1
    rows = [[
        "team_number", "name", "division", "affiliation", "students",
        "adult_name", "adult_email", "adult_phone", "kit_ordered", "checked_in",
        "inspection_status", "inspection_attempts", "registered_at",
    ]]
    for team in Team.query.order_by(Team.team_number).all():
        insp = latest.get(team.id)
        rows.append([
            team.team_number, team.name, team.division, team.affiliation,
            "; ".join(team.students.splitlines()), team.adult_name,
            team.adult_email, team.adult_phone or "", _yes(team.kit_ordered),
            _yes(team.checked_in),
            ("passed" if insp.passed else "failed") if insp else "not inspected",
            attempts.get(team.id, 0), _iso(team.created_at),
        ])
    return rows


def _csv_inspections():
    numbers = _team_numbers()
    rows = [[
        "team_number", "inspected_at", "passed", "size_ok", "weight_ok",
        "microbit_present", "team_number_displayed", "ref_start_stop_test",
        "inspector_name", "notes",
    ]]
    for insp in Inspection.query.order_by(Inspection.team_id, Inspection.inspected_at).all():
        rows.append([
            numbers.get(insp.team_id, ""), _iso(insp.inspected_at), _yes(insp.passed),
            _yes(insp.size_ok), _yes(insp.weight_ok), _yes(insp.microbit_present),
            _yes(insp.team_number_displayed), _yes(insp.ref_start_stop_test),
            insp.inspector_name or "", insp.notes or "",
        ])
    return rows


def _csv_series():
    numbers = _team_numbers()
    rows = [[
        "match_id", "match_number", "division", "phase", "bracket_position", "arena",
        "scheduled_time", "red_team_number", "blue_team_number", "status",
        "red_game_wins", "blue_game_wins", "series_winner_team_number",
    ]]
    for match in Match.query.order_by(Match.division, Match.match_number).all():
        tally = series_tally(match)
        winner = {"red": match.red_team_id, "blue": match.blue_team_id}.get(tally.winner)
        position = ""
        if match.phase == "elimination":
            position = f"{match.bracket_side or 'W'}{match.bracket_round}-{match.bracket_slot}"
        rows.append([
            match.id, match.match_number, match.division, match.phase, position,
            match.arena, _iso(match.scheduled_time), numbers.get(match.red_team_id, ""),
            numbers.get(match.blue_team_id, ""), match.status, tally.red_wins,
            tally.blue_wins, numbers.get(winner, "") if winner else "",
        ])
    return rows


def _csv_games():
    numbers = _team_numbers()
    matches = {m.id: m for m in Match.query.all()}
    rows = [[
        "match_id", "match_number", "phase", "game_number", "red_team_number",
        "blue_team_number", "outcome", "win_time_seconds", "red_final_zone",
        "blue_final_zone", "voided", "submitted_by", "submitted_at",
    ]]
    games = MatchResult.query.order_by(MatchResult.match_id, MatchResult.game_number).all()
    for game in games:
        match = matches.get(game.match_id)
        rows.append([
            game.match_id, match.match_number if match else "", match.phase if match else "",
            game.game_number,
            numbers.get(match.red_team_id, "") if match else "",
            numbers.get(match.blue_team_id, "") if match else "",
            game.outcome,
            "" if game.win_time_seconds is None else game.win_time_seconds,
            game.red_final_zone, game.blue_final_zone, _yes(game.voided),
            game.submitted_by, _iso(game.submitted_at),
        ])
    return rows


def _csv_audit():
    numbers = {m.id: m.match_number for m in Match.query.all()}
    rows = [["changed_at", "changed_by", "match_number", "match_id", "field", "old_value", "new_value"]]
    for entry in AuditEntry.query.order_by(AuditEntry.changed_at).all():
        rows.append([
            _iso(entry.changed_at), entry.changed_by, numbers.get(entry.match_id, ""),
            entry.match_id, entry.field, entry.old_value or "", entry.new_value or "",
        ])
    return rows


def _csv_rankings():
    from app.rankings.logic import get_division_rankings

    rows = [[
        "division", "rank", "team_number", "team_name", "qual_points", "series_wins",
        "series_losses", "match_wins", "match_losses", "match_diff", "strength_of_schedule",
        "placed_by_draw",
    ]]
    divisions = sorted({d for (d,) in db.session.query(Team.division).distinct()})
    for division in divisions:
        for row in get_division_rankings(division):
            rows.append([
                division, row["rank"], row["team_number"], row["team_name"],
                row["qual_points"], row["series_wins"], row["series_losses"],
                row["match_wins"], row["match_losses"], row["match_diff"], row["sos"],
                _yes(row["decided_by_draw"] and row["series_played"]),
            ])
    return rows


EXPORTS = {
    "teams": ("Teams, check-in and inspection status", _csv_teams),
    "inspections": ("Every inspection attempt", _csv_inspections),
    "matches": ("Every series (qualification and bracket)", _csv_series),
    "games": ("Every game result, including voided ones", _csv_games),
    "rankings": ("Final qualification standings", _csv_rankings),
    "audit": ("Audit log of every result change", _csv_audit),
}


def _csv_text(rows):
    buffer = io.StringIO()
    buffer.write("﻿")
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue()


def _download(body, filename, mimetype):
    return Response(
        body,
        mimetype=mimetype,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@admin_bp.route("/export.csv")
def export_csv():
    """Every series and its result. Kept at its original address."""
    return _download(_csv_text(_csv_series()), "matches.csv", "text/csv")


@admin_bp.route("/export/<name>.csv")
def export_one(name):
    if name not in EXPORTS:
        abort(404)
    return _download(_csv_text(EXPORTS[name][1]()), f"{name}.csv", "text/csv")


@admin_bp.route("/export/all.zip")
def export_all():
    """The global end-of-event export: every CSV above in one file."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, (_, build) in EXPORTS.items():
            archive.writestr(f"{name}.csv", _csv_text(build()).encode("utf-8"))
    stamp = utcnow().strftime("%Y%m%d-%H%M")
    return _download(buffer.getvalue(), f"src-export-{stamp}.zip", "application/zip")
