# owner: Yueyue
# Head ref panel: edit any result (writing an AuditEntry every time), pause
# and resume the schedule, insert a replay match, global CSV export.

from flask import render_template, request, redirect, url_for

from app.db import db
from app.fake_data import MATCHES, RESULTS_BY_MATCH_ID, MATCHES_BY_ID
from app.models import AuditEntry, MatchResult
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
    match = MATCHES_BY_ID.get(match_id)
    result = MatchResult.query.filter_by(match_id=match_id).first()
    if result is None:
        result = RESULTS_BY_MATCH_ID.get(match_id)

    if request.method == "POST":
        if result is None:
            return render_template(
                "admin/edit_result.html",
                match=match,
                result=None,
                error_message="No result found for this match.",
            )

        updated_values = {
            "outcome": request.form.get("outcome"),
            "red_final_zone": request.form.get("red_final_zone"),
            "blue_final_zone": request.form.get("blue_final_zone"),
        }

        if not isinstance(result, MatchResult):
            # The app still has fake-data fallback for GET-only display. Do not
            # try to mutate those placeholder dicts; use the real model when
            # saving changes.
            return render_template(
                "admin/edit_result.html",
                match=match,
                result=result,
                error_message="Result updates must use the real database-backed MatchResult model.",
            )

        try:
            changed_fields = []
            for field_name, new_value in updated_values.items():
                old_value = getattr(result, field_name)
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
            return redirect(url_for("admin.audit_log"))
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
