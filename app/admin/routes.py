# owner: Yueyue
# Head ref panel: edit any result (writing an AuditEntry every time), pause
# and resume the schedule, insert a replay match, global CSV export.

from flask import render_template

from app.fake_data import MATCHES, RESULTS_BY_MATCH_ID, AUDIT_ENTRIES, MATCHES_BY_ID
from app.admin import admin_bp


@admin_bp.route("/")
def dashboard():
    return render_template("admin/dashboard.html", matches=MATCHES)


@admin_bp.route("/edit/<int:match_id>", methods=["GET", "POST"])
def edit_result(match_id):
    # TODO(Yueyue): on POST, save the changed fields and write an
    # AuditEntry for each one (see logic.py:edit_result_with_audit). A
    # MatchResult may only be changed through this page.
    match = MATCHES_BY_ID.get(match_id)
    result = RESULTS_BY_MATCH_ID.get(match_id)
    return render_template("admin/edit_result.html", match=match, result=result)


@admin_bp.route("/audit-log")
def audit_log():
    return render_template("admin/audit_log.html", entries=AUDIT_ENTRIES)
