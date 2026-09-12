# owner: Yueyue
# Head ref panel: edit any result (writing an AuditEntry every time), pause
# and resume the schedule, insert a replay match, global CSV export.

import csv
import io
from datetime import datetime

from flask import render_template, request, redirect, url_for, abort, Response

from app.db import db
from app.models import AuditEntry, Match, MatchResult, ScheduleState
from app.admin import admin_bp


def _match_rows_with_results():
    rows = []
    matches = Match.query.order_by(Match.division, Match.match_number).all()
    for match in matches:
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
    match = Match.query.filter_by(id=match_id).first()
    result = MatchResult.query.filter_by(match_id=match_id).first()

    if request.method == "POST":
        if result is None:
            return render_template(
                "admin/edit_result.html",
                match=match,
                result=None,
                error_message="No result found for this match.",
            )

        if match is None:
            return render_template(
                "admin/edit_result.html",
                match=None,
                result=result,
                error_message="No match found for this result.",
            )

        updated_values = {
            "outcome": request.form.get("outcome"),
            "win_time_seconds": request.form.get("win_time_seconds"),
            "red_final_zone": request.form.get("red_final_zone"),
            "blue_final_zone": request.form.get("blue_final_zone"),
        }

        try:
            changed_fields = []
            for field_name, new_value in updated_values.items():
                old_value = getattr(result, field_name)

                if field_name == "win_time_seconds":
                    if new_value in (None, ""):
                        converted_value = None
                    else:
                        converted_value = float(new_value)
                    new_value = converted_value

                if old_value != new_value:
                    changed_fields.append((field_name, old_value, new_value))
                    setattr(result, field_name, new_value)

            for field_name, old_value, new_value in changed_fields:
                audit_entry = AuditEntry(
                    match_id=match_id,
                    changed_by=_current_admin_name(),
                    field=field_name,
                    old_value=str(old_value) if old_value is not None else None,
                    new_value=str(new_value) if new_value is not None else None,
                )
                db.session.add(audit_entry)

            if changed_fields:
                db.session.add(result)
                db.session.commit()
            return redirect(url_for("admin.edit_result", match_id=match_id))
        except Exception:
            db.session.rollback()
            return render_template(
                "admin/edit_result.html",
                match=match,
                result=result,
                error_message="Could not save the result change. No database changes were committed.",
            )

    return render_template("admin/edit_result.html", match=match, result=result)


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
    original_match_id = request.form.get("original_match_id")

    if not original_match_id:
        abort(400)

    original_match = Match.query.filter_by(id=original_match_id).first()
    if original_match is None:
        abort(404)

    # Get the next available match_number for this division
    next_match_number = _get_next_match_number_for_division(original_match.division)

    # Create the replay match
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
