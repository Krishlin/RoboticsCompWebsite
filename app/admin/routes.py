# owner: Yueyue
# Head ref panel: edit any result (writing an AuditEntry every time), pause
# and resume the schedule, insert a replay match, global CSV export.

from flask import render_template, request, redirect, url_for, abort

from app.db import db
from app.fake_data import MATCHES, RESULTS_BY_MATCH_ID
from app.models import AuditEntry, Match, MatchResult
from app.admin import admin_bp


def _match_rows_with_results():
    rows = []
    for match in MATCHES:
        result = RESULTS_BY_MATCH_ID.get(match["id"])
        rows.append({
            "match": match,
            "result": result,
        })
    return rows


def _current_admin_name():
    # No auth layer exists in this repo yet. This is a temporary placeholder.
    # Replace this with the authenticated user once the app adds real login.
    return "admin"


@admin_bp.route("/")
def dashboard():
    match_rows = _match_rows_with_results()
    return render_template("admin/dashboard.html", match_rows=match_rows)


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
