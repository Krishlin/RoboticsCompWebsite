# owner: Yueyue
# Head ref panel: edit any result (writing an AuditEntry every time), pause
# and resume the schedule, insert a replay match, global CSV export.

import csv
import io
import math
from datetime import datetime

from flask import render_template, request, redirect, url_for, abort, Response

from app.db import db
from app.models import AuditEntry, Match, MatchResult, ScheduleState
from app.admin import admin_bp


def _match_rows_with_results():
    # Keep the dashboard template contract the same: each row is a dict with
    # "match" and "result" so the template can remain simple and unchanged.
    rows = []
    matches = Match.query.order_by(Match.division, Match.match_number).all()
    for match in matches:
        # A match may or may not have a corresponding result record.
        result = MatchResult.query.filter_by(match_id=match.id).first()
        rows.append({
            "match": match,
            "result": result,
        })
    return rows


def _current_admin_name():
    # No auth layer exists in this repo yet. This is a temporary placeholder.
    # Replace this with the authenticated user once the app adds real login.
    return "admin"


def _get_or_create_schedule_state():
    """Get the global schedule state. Create it if it doesn't exist."""
    state = ScheduleState.query.filter_by(id=1).first()
    if state is None:
        state = ScheduleState(id=1, is_paused=False, changed_by=None)
        db.session.add(state)
        db.session.commit()
    return state


def _get_next_match_number_for_division(division):
    """Get the next available match_number for a given division."""
    # Match numbers appear to restart per division rather than being globally unique.
    # This helper finds the highest existing value in the target division and uses
    # the next number so replay matches do not collide with existing schedule entries.
    max_match = Match.query.filter_by(division=division).order_by(Match.match_number.desc()).first()
    if max_match is None:
        return 1
    return max_match.match_number + 1


@admin_bp.route("/")
def dashboard():
    match_rows = _match_rows_with_results()
    schedule_state = _get_or_create_schedule_state()
    return render_template("admin/dashboard.html", match_rows=match_rows, schedule_state=schedule_state)


@admin_bp.route("/edit/<int:match_id>", methods=["GET", "POST"])
def edit_result(match_id):
    # Fetch the match and its associated result separately, since a result is not
    # guaranteed to exist for every match in the database.
    match = Match.query.filter_by(id=match_id).first()
    result = MatchResult.query.filter_by(match_id=match_id).first()
    # Keep the create path distinct so existing edits never reset match status.
    is_new_result = result is None

    if request.method == "POST":
        if match is None:
            return render_template(
                "admin/edit_result.html",
                match=None,
                result=result,
                is_new_result=is_new_result,
                error_message="No match found for this result.",
            )

        updated_values = {
            "outcome": request.form.get("outcome"),
            "win_time_seconds": request.form.get("win_time_seconds"),
            "red_final_zone": request.form.get("red_final_zone"),
            "blue_final_zone": request.form.get("blue_final_zone"),
        }

        try:
            # Validate server-side because form controls can be bypassed by direct requests.
            allowed_outcomes = {"red", "blue", "tie", "double_dq"}
            allowed_zones = {"Center", "Red Zone", "Blue Zone", "Off Arena"}

            if updated_values["outcome"] not in allowed_outcomes:
                raise ValueError("Invalid outcome")
            if updated_values["red_final_zone"] not in allowed_zones:
                raise ValueError("Invalid red final zone")
            if updated_values["blue_final_zone"] not in allowed_zones:
                raise ValueError("Invalid blue final zone")

            raw_win_time = updated_values["win_time_seconds"]
            if raw_win_time is None or raw_win_time.strip() == "":
                updated_values["win_time_seconds"] = None
            else:
                win_time = float(raw_win_time)
                if not math.isfinite(win_time) or win_time < 0:
                    raise ValueError("Invalid win time")
                updated_values["win_time_seconds"] = win_time

            # Track only the fields that actually changed so we only write the
            # necessary audit entries and do not create noisy history for unchanged data.
            changed_fields = []
            if is_new_result:
                # A first result needs its own row; an edit reuses the existing row below.
                result = MatchResult(
                    match_id=match_id,
                    submitted_by=_current_admin_name(),
                )

            for field_name, new_value in updated_values.items():
                old_value = getattr(result, field_name)

                if old_value != new_value:
                    changed_fields.append((field_name, old_value, new_value))
                    setattr(result, field_name, new_value)

            for field_name, old_value, new_value in changed_fields:
                # Every modified field writes an AuditEntry so admin changes are
                # trackable in the audit log and match history views.
                audit_entry = AuditEntry(
                    match_id=match_id,
                    changed_by=_current_admin_name(),
                    field=field_name,
                    # Store the before/after values as text for the audit table.
                    old_value=str(old_value) if old_value is not None else None,
                    new_value=str(new_value) if new_value is not None else None,
                )
                db.session.add(audit_entry)

            if changed_fields or is_new_result:
                db.session.add(result)
                if is_new_result:
                    # The first submitted result means this scheduled match has been played.
                    match.status = "complete"
                db.session.commit()
            return redirect(url_for("admin.edit_result", match_id=match_id))
        except Exception as e:
            db.session.rollback()
            return render_template(
                "admin/edit_result.html",
                match=match,
                result=result,
                is_new_result=is_new_result,
                error_message="Could not save the result change. No database changes were committed.",
            )

    return render_template(
        "admin/edit_result.html",
        match=match,
        result=result,
        is_new_result=is_new_result,
    )


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
    state.changed_at = datetime.utcnow()
    db.session.commit()
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/resume", methods=["POST"])
def resume_schedule():
    """Resume the schedule."""
    state = _get_or_create_schedule_state()
    state.is_paused = False
    state.changed_by = _current_admin_name()
    state.changed_at = datetime.utcnow()
    db.session.commit()
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/replay", methods=["POST"])
def insert_replay_match():
    """Create a replay of an existing match."""
    # The form posts the original match id, and the server clones that match into a
    # new record while preserving the original match unchanged.
    original_match_id = request.form.get("original_match_id")

    if not original_match_id:
        abort(400)

    original_match = Match.query.filter_by(id=original_match_id).first()
    if original_match is None:
        abort(404)

    # Replays should not collide with an existing match number in the same division.
    next_match_number = _get_next_match_number_for_division(original_match.division)

    # Create the replay match.
    # We intentionally copy only the scheduling/bracket data and teams; no result is
    # copied because the replay starts fresh and must be scored separately.
    # This link lets rankings replace the original with this replay's result.
    replay_match = Match(
        match_number=next_match_number,
        phase=original_match.phase,
        division=original_match.division,
        arena=original_match.arena,
        scheduled_time=original_match.scheduled_time,
        red_team_id=original_match.red_team_id,
        blue_team_id=original_match.blue_team_id,
        status="scheduled",
        is_replay=True,
        replay_of_match_id=original_match.id,
        bracket_round=original_match.bracket_round,
        bracket_slot=original_match.bracket_slot,
    )

    try:
        db.session.add(replay_match)
        db.session.commit()
    except Exception:
        db.session.rollback()
        abort(500)

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/export.csv", methods=["GET"])
def export_csv():
    """Export all matches and results to CSV."""
    # Export the live database records instead of the fake in-memory data used by
    # other parts of the app. The order is kept predictable by division, then match.
    matches = Match.query.order_by(Match.division, Match.match_number).all()

    # These columns match the live Match + MatchResult shape and are written in a
    # consistent order so spreadsheet import is straightforward.
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

        # Leave result columns blank when the match has not been scored yet.
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
