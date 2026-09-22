# owner: Yueyue
# Head ref panel: edit any result (writing an AuditEntry every time), pause
# and resume the schedule, insert a replay match, global CSV export.

import csv
import io
import math
from datetime import timedelta

from flask import render_template, request, redirect, url_for, abort, Response
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.db import db
from app.models import utcnow, AuditEntry, Match, MatchResult, ScheduleState
from app.admin import admin_bp

# How far after the end of a division's schedule a replay is slotted. The
# replay used to inherit the original's scheduled_time, which put it in the
# past and pinned it to the top of "Up Next" for the rest of the event.
REPLAY_GAP_MINUTES = 15


def _match_rows_with_results():
    """Every match with its result and whether it can still be replayed.

    Results and replay links are fetched in one query each rather than per
    row: adding a per-row replay lookup to the old loop would have made the
    dashboard issue three queries per match instead of one.
    """
    matches = Match.query.order_by(Match.division, Match.match_number).all()

    results_by_match = {
        r.match_id: r
        for r in MatchResult.query.filter(
            MatchResult.match_id.in_([m.id for m in matches])
        ).all()
    } if matches else {}

    already_replayed = {
        m.replaces_match_id for m in matches if m.replaces_match_id is not None
    }

    return [
        {
            "match": match,
            "result": results_by_match.get(match.id),
            # What insert_replay_match will actually accept, so the dropdown
            # doesn't offer choices that come back as a 400.
            "replayable": match.status == "complete" and match.id not in already_replayed,
        }
        for match in matches
    ]


def _current_admin_name():
    # No auth layer exists in this repo yet. This is a temporary placeholder.
    # Replace this with the authenticated user once the app adds real login.
    return "admin"


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


def _get_next_match_number_for_division(division):
    """Get the next available match_number for a given division."""
    max_match = Match.query.filter_by(division=division).order_by(Match.match_number.desc()).first()
    if max_match is None:
        return 1
    return max_match.match_number + 1


@admin_bp.route("/")
def dashboard():
    match_rows = _match_rows_with_results()
    schedule_state = _read_schedule_state()
    return render_template("admin/dashboard.html", match_rows=match_rows, schedule_state=schedule_state)


def _parse_win_time(raw_value):
    """Validate the win_time_seconds form field.

    Returns (value, error_message); exactly one of the two is None. float()
    accepts "nan" and "inf", and SQLite stores a NaN as NULL — so an audit
    entry would record a new_value the database does not contain, and on
    Postgres a stored NaN makes the standings sort non-deterministic because
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


@admin_bp.route("/edit/<int:match_id>", methods=["GET", "POST"])
def edit_result(match_id):
    match = Match.query.filter_by(id=match_id).first()
    if match is None:
        abort(404)
    result = MatchResult.query.filter_by(match_id=match_id).first()

    def _render(error_message=None):
        return render_template(
            "admin/edit_result.html",
            match=match,
            result=result,
            error_message=error_message,
        )

    if request.method == "POST":
        if result is None:
            return _render("No result found for this match.")

        text_fields = ("outcome", "red_final_zone", "blue_final_zone")
        missing = [name for name in text_fields if request.form.get(name) is None]
        if missing:
            return _render("Missing form field(s): " + ", ".join(missing) + ".")

        win_time, win_time_error = _parse_win_time(request.form.get("win_time_seconds"))
        if win_time_error:
            return _render(win_time_error)

        updated_values = {
            "outcome": request.form.get("outcome"),
            "win_time_seconds": win_time,
            "red_final_zone": request.form.get("red_final_zone"),
            "blue_final_zone": request.form.get("blue_final_zone"),
        }

        changed_fields = []
        for field_name, new_value in updated_values.items():
            old_value = getattr(result, field_name)
            if old_value != new_value:
                changed_fields.append((field_name, old_value, new_value))
                setattr(result, field_name, new_value)

        if not changed_fields:
            return redirect(url_for("admin.edit_result", match_id=match_id))

        for field_name, old_value, new_value in changed_fields:
            audit_entry = AuditEntry(
                match_id=match_id,
                changed_by=_current_admin_name(),
                field=field_name,
                old_value=str(old_value) if old_value is not None else None,
                new_value=str(new_value) if new_value is not None else None,
            )
            db.session.add(audit_entry)

        db.session.add(result)
        try:
            db.session.commit()
        except SQLAlchemyError as exc:
            db.session.rollback()
            return _render(
                "Could not save the result change, so nothing was committed: "
                f"{exc.__class__.__name__}."
            )
        return redirect(url_for("admin.edit_result", match_id=match_id))

    return _render()


@admin_bp.route("/audit-log")
def audit_log():
    entries = AuditEntry.query.order_by(AuditEntry.changed_at.desc()).all()
    return render_template("admin/audit_log.html", entries=entries)


@admin_bp.route("/match/<int:match_id>/history")
def match_history(match_id):
    match = Match.query.filter_by(id=match_id).first()
    if match is None:
        abort(404)
    entries = AuditEntry.query.filter_by(match_id=match_id).order_by(AuditEntry.changed_at.desc()).all()
    return render_template("admin/match_history.html", match=match, entries=entries)


@admin_bp.route("/pause", methods=["POST"])
def pause_schedule():
    """Pause the schedule."""
    state = _get_or_create_schedule_state()
    state.is_paused = True
    state.changed_by = _current_admin_name()
    state.changed_at = utcnow()
    db.session.commit()
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/resume", methods=["POST"])
def resume_schedule():
    """Resume the schedule."""
    state = _get_or_create_schedule_state()
    state.is_paused = False
    state.changed_by = _current_admin_name()
    state.changed_at = utcnow()
    db.session.commit()
    return redirect(url_for("admin.dashboard"))


def _next_replay_time(original_match):
    """When to run a replay: after everything else in that division.

    Derived from the existing schedule rather than the clock on purpose —
    seed.py writes local event times and seed_for_testing.py writes UTC into
    the same column, so anchoring to now() would land the replay hours away
    from the rest of the schedule depending on which seeder ran.
    """
    last_time = (
        db.session.query(db.func.max(Match.scheduled_time))
        .filter(Match.division == original_match.division)
        .scalar()
    )
    anchor = last_time or original_match.scheduled_time or utcnow()
    return anchor + timedelta(minutes=REPLAY_GAP_MINUTES)


@admin_bp.route("/replay", methods=["POST"])
def insert_replay_match():
    """Create a replay that supersedes an existing match."""
    original_match_id = request.form.get("original_match_id")

    if not original_match_id:
        abort(400)

    original_match = Match.query.filter_by(id=original_match_id).first()
    if original_match is None:
        abort(404)

    # A replay overwrites a result, so there has to be a result to overwrite.
    # Replaying a match that hasn't run yet used to be accepted and just
    # duplicated the fixture.
    if original_match.status != "complete":
        abort(
            400,
            description=(
                f"Match {original_match.match_number} is '{original_match.status}', "
                "not complete — there is no result to replay."
            ),
        )

    # Two live replays of one match would both score, which is exactly the
    # double count replaces_match_id exists to prevent. Replaying a replay is
    # fine: the chain supersedes one link at a time.
    existing_replay = Match.query.filter_by(replaces_match_id=original_match.id).first()
    if existing_replay is not None:
        abort(
            400,
            description=(
                f"Match {original_match.match_number} has already been replayed as "
                f"match {existing_replay.match_number}. Replay that one instead."
            ),
        )

    replay_match = Match(
        match_number=_get_next_match_number_for_division(original_match.division),
        phase=original_match.phase,
        division=original_match.division,
        arena=original_match.arena,
        scheduled_time=_next_replay_time(original_match),
        red_team_id=original_match.red_team_id,
        blue_team_id=original_match.blue_team_id,
        status="scheduled",
        is_replay=True,
        replaces_match_id=original_match.id,
        # The replay inherits the bracket slot because it takes the original's
        # place in it; replaces_match_id is what tells the bracket which of the
        # two is live.
        bracket_round=original_match.bracket_round,
        bracket_slot=original_match.bracket_slot,
    )
    db.session.add(replay_match)
    db.session.flush()  # assign replay_match.id for the audit entry below

    # The original silently stops counting toward standings from here, so it
    # has to be visible in the audit log.
    db.session.add(
        AuditEntry(
            match_id=original_match.id,
            changed_by=_current_admin_name(),
            field="superseded_by_match_id",
            old_value=None,
            new_value=str(replay_match.id),
        )
    )

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        abort(500)

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/export.csv", methods=["GET"])
def export_csv():
    """Export all matches and results to CSV."""
    # Query all matches ordered by division and match_number
    matches = Match.query.order_by(Match.division, Match.match_number).all()

    # Define CSV columns
    columns = [
        "match_id",
        "match_number",
        "division",
        "phase",
        "arena",
        "scheduled_time",
        "red_team_id",
        "blue_team_id",
        "status",
        "is_replay",
        "bracket_round",
        "bracket_slot",
        "outcome",
        "win_time_seconds",
        "red_final_zone",
        "blue_final_zone",
        "submitted_at",
        "submitted_by",
    ]

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, restval="")
    writer.writeheader()

    # Write each match row
    for match in matches:
        result = MatchResult.query.filter_by(match_id=match.id).first()

        row = {
            "match_id": match.id,
            "match_number": match.match_number,
            "division": match.division,
            "phase": match.phase,
            "arena": match.arena,
            "scheduled_time": match.scheduled_time.isoformat() if match.scheduled_time else "",
            "red_team_id": match.red_team_id,
            "blue_team_id": match.blue_team_id,
            "status": match.status,
            "is_replay": match.is_replay,
            "bracket_round": match.bracket_round,
            "bracket_slot": match.bracket_slot,
        }

        # Add result columns if result exists
        if result:
            row["outcome"] = result.outcome
            row["win_time_seconds"] = result.win_time_seconds
            row["red_final_zone"] = result.red_final_zone
            row["blue_final_zone"] = result.blue_final_zone
            row["submitted_at"] = result.submitted_at.isoformat() if result.submitted_at else ""
            row["submitted_by"] = result.submitted_by

        writer.writerow(row)

    # Prepare response
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=matches.csv"},
    )
