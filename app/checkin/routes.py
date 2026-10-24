# owner: Shivani
# Check-in list (one tap per team), and the inspection checklist
# (pass/fail, timestamped, re-inspection allowed with both attempts kept).


from flask import render_template, redirect, url_for, request
from app.checkin import checkin_bp
from app.db import db
from app.models import Team, Inspection
from app.security import staff_required


# Volunteers only, except the self check-in page below. Gated as a whole,
# because inspection records and the "who has arrived" desk list are not public.
_SELF_SERVICE = {"checkin.self_checkin", "checkin.self_checkin_team"}


@staff_required
def _staff_only():
    return None


@checkin_bp.before_request
def _require_staff():
    if request.endpoint in _SELF_SERVICE:
        return None
    return _staff_only()


@checkin_bp.route("/")
def checkin_list():
    # Get every team from the real database,
    # ordered by team number.
    teams = Team.query.order_by(Team.team_number).all()

    # Each team's most recent inspection, so the list shows where every team
    # stands without opening each one. Later attempts overwrite earlier ones.
    latest = {}
    for inspection in Inspection.query.order_by(Inspection.inspected_at).all():
        latest[inspection.team_id] = inspection

    # Send those teams to the check-in page.
    return render_template(
        "checkin/checkin_list.html",
        teams=teams,
        latest=latest,
        arrived=sum(1 for t in teams if t.checked_in),
    )


@checkin_bp.route("/<int:team_id>/check-in", methods=["POST"])
def check_in_team(team_id):
    # Find the team that matches the ID from the button.
    team = Team.query.get_or_404(team_id)

    # Mark the team as arrived.
    team.checked_in = True

    # Save that change to the database.
    db.session.commit()

    # Send the user back to the check-in list.
    return redirect(url_for("checkin.checkin_list"))

# No passcode: teams check themselves in. Shows only number, name and whether
# they have arrived, never inspection results or contact details. Anyone can
# check in any team, which is accepted; the desk list is the backstop.
@checkin_bp.route("/self")
def self_checkin():
    teams = Team.query.order_by(Team.team_number).all()
    return render_template("checkin/self_checkin.html", teams=teams)


@checkin_bp.route("/self/<int:team_id>", methods=["POST"])
def self_checkin_team(team_id):
    team = db.get_or_404(Team, team_id)
    team.checked_in = True
    db.session.commit()
    return redirect(url_for("checkin.self_checkin"))


@checkin_bp.route("/inspect/<int:team_number>", methods=["GET", "POST"])
def inspection_form(team_number):
    team = Team.query.filter_by(team_number=team_number).first_or_404()

    if request.method == "POST":
        size_ok = "size_ok" in request.form
        weight_ok = "weight_ok" in request.form
        microbit_present = "microbit_present" in request.form
        team_number_displayed = "team_number_displayed" in request.form
        ref_start_stop_test = "ref_start_stop_test" in request.form

        passed = (
            size_ok
            and weight_ok
            and microbit_present
            and team_number_displayed
            and ref_start_stop_test
        )

        inspection = Inspection(
            team_id=team.id,
            passed=passed,
            size_ok=size_ok,
            weight_ok=weight_ok,
            microbit_present=microbit_present,
            team_number_displayed=team_number_displayed,
            ref_start_stop_test=ref_start_stop_test,
            notes=request.form.get("notes", ""),
            inspector_name=request.form.get("inspector_name", ""),
        )

        db.session.add(inspection)
        db.session.commit()

        return redirect(
            url_for(
                "checkin.inspection_history",
                team_number=team.team_number
            )
        )

    return render_template(
        "checkin/inspection_form.html",
        team=team
    )


@checkin_bp.route("/history/<int:team_number>")
def inspection_history(team_number):
    team = Team.query.filter_by(team_number=team_number).first_or_404()

    history = (
        Inspection.query
        .filter_by(team_id=team.id)
        .order_by(Inspection.inspected_at.desc())
        .all()
    )

    current = history[0] if history else None

    return render_template(
        "checkin/inspection_history.html",
        team=team,
        history=history,
        current=current,
    )