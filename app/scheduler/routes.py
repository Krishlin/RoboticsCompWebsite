# owner: Shaurya
# Generates and displays the qualification schedule: full list, per-arena,
# and per-team views. Each scheduled match is one best-of-three series.

from datetime import datetime

from flask import current_app, jsonify, render_template, request
from sqlalchemy.exc import SQLAlchemyError

from app.formatting import clock
from app.match_state import arena_names
from app.models import Match, Team
from app.scheduler import scheduler_bp
from app.scheduler.generator import (
    DEFAULT_SERIES_PER_TEAM,
    DEFAULT_SLOT_MINUTES,
    format_violations,
    generate_advanced_schedule,
    generate_balanced_schedule,
    generate_random_schedule,
    validate_schedule,
)
from app.scheduler.service import played_qualification_count, save_schedule
from app.security import head_ref_required

# The event runs on one field.
DEFAULT_ARENA_COUNT = 1


def _enrich_matches(matches):
    """Attach red/blue team names to each match for display."""
    teams_by_id = {t.id: t for t in Team.query.all()}

    enriched = []
    for match in matches:
        red_team = teams_by_id.get(match.red_team_id)
        blue_team = teams_by_id.get(match.blue_team_id)

        enriched.append({
            "match_number": match.match_number,
            "division": match.division,
            "arena": match.arena,
            "scheduled_time": clock(match.scheduled_time),
            "red_team_number": red_team.team_number if red_team else None,
            "blue_team_number": blue_team.team_number if blue_team else None,
            "red_team_name": red_team.name if red_team else "TBD",
            "blue_team_name": blue_team.name if blue_team else "TBD",
            "status": match.status,
        })
    return enriched


@scheduler_bp.route("/")
def schedule_full():
    """Display the full qualification schedule for all divisions."""
    matches = Match.query.filter_by(phase="qualification").order_by(Match.match_number).all()
    enriched = _enrich_matches(matches)
    return render_template("scheduler/schedule_full.html", matches=enriched, arenas=arena_names())


@scheduler_bp.route("/arena/<arena>")
def schedule_by_arena(arena):
    """Display the qualification schedule for a specific arena (printable)."""
    arena_name = arena.replace("_", " ")
    matches = Match.query.filter_by(phase="qualification", arena=arena_name).order_by(
        Match.scheduled_time, Match.match_number
    ).all()
    enriched = _enrich_matches(matches)
    return render_template(
        "scheduler/schedule_by_arena.html",
        arena=arena_name,
        matches=enriched,
    )


@scheduler_bp.route("/team/<int:team_number>")
def schedule_by_team(team_number):
    """Display the qualification schedule for a specific team (printable)."""
    team = Team.query.filter_by(team_number=team_number).first()
    if not team:
        return render_template(
            "scheduler/schedule_by_team.html", team_number=team_number, team=None, matches=[]
        )

    matches = Match.query.filter_by(phase="qualification").filter(
        (Match.red_team_id == team.id) | (Match.blue_team_id == team.id)
    ).order_by(Match.scheduled_time, Match.match_number).all()

    enriched = _enrich_matches(matches)
    return render_template(
        "scheduler/schedule_by_team.html",
        team_number=team_number,
        team=team,
        matches=enriched,
    )


def _configured_start():
    raw = current_app.config.get("EVENT_QUAL_START") or ""
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M")
    except ValueError:
        return datetime(2026, 10, 24, 10, 0)


@scheduler_bp.route("/admin")
@head_ref_required
def admin():
    """Admin page for schedule generation and validation."""
    return render_template(
        "scheduler/admin.html",
        team_count=Team.query.count(),
        checked_in_count=Team.query.filter_by(checked_in=True).count(),
        existing_count=Match.query.filter_by(phase="qualification").count(),
        default_start=_configured_start().strftime("%Y-%m-%dT%H:%M"),
        default_series=DEFAULT_SERIES_PER_TEAM,
        default_arenas=DEFAULT_ARENA_COUNT,
        default_slot=DEFAULT_SLOT_MINUTES,
    )


def _int_option(data, name, default, low, high):
    raw = data.get(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a whole number, got {raw!r}.") from None
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}, got {value}.")
    return value


def _start_option(data):
    raw = (data.get("start_time") or "").strip()
    if not raw:
        return _configured_start()
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ValueError(f"start_time must look like 2026-10-24T10:00, got {raw!r}.")


@scheduler_bp.route("/api/generate", methods=["POST"])
@head_ref_required
def api_generate_schedule():
    """Generate a new qualification schedule and save it (head ref only)."""
    data = request.get_json(silent=True) or {}
    use_random = bool(data.get("use_random", False))
    use_advanced = bool(data.get("use_advanced", False))
    clear_existing = data.get("clear_existing", True)
    checked_in_only = bool(data.get("checked_in_only", False))
    # Everyone plays everyone once: series per team is the number of other
    # teams, so it follows however many teams are being scheduled.
    round_robin = bool(data.get("round_robin", False))

    try:
        matches_per_team = _int_option(data, "matches_per_team", DEFAULT_SERIES_PER_TEAM, 1, 30)
        arena_count = _int_option(data, "arena_count", DEFAULT_ARENA_COUNT, 1, 30)
        slot_minutes = _int_option(data, "slot_minutes", DEFAULT_SLOT_MINUTES, 1, 120)
        start_time = _start_option(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    # Regenerating after the event has started is refused, not attempted.
    # Clearing deletes the qualification matches but not their results,
    # audit entries or replays, which all point at match ids: on SQLite the
    # ids get reused and old results silently attach to new, different
    # pairings; on Postgres the foreign keys make the delete fail. A partial
    # regenerate (keep played series, reschedule the rest) can't keep series
    # counts equal in general, so the head ref has to decide by hand instead.
    if clear_existing:
        started = played_qualification_count()
        if started:
            return jsonify({
                "error": (
                    f"{started} qualification match(es) have already been played "
                    "or started, so the schedule can't be regenerated without "
                    "losing or misattributing results. Use the admin page to "
                    "order replays instead."
                ),
            }), 409

    query = Team.query
    if checked_in_only:
        query = query.filter_by(checked_in=True)
    teams = query.all()
    if len(teams) < 2:
        return jsonify({
            "error": "Need at least two teams" + (" checked in" if checked_in_only else "") + "."
        }), 400

    if round_robin:
        matches_per_team = len(teams) - 1

    team_dicts = [{"team_number": t.team_number, "division": t.division} for t in teams]
    arenas = [f"Arena {i}" for i in range(1, arena_count + 1)]
    options = {
        "arenas": arenas,
        "matches_per_team": matches_per_team,
        "start_time": start_time,
        "slot_minutes": slot_minutes,
    }

    if use_random:
        matches_data = generate_random_schedule(team_dicts, **options)
        algorithm = "random"
    elif use_advanced or not data.get("use_balanced"):
        matches_data = generate_advanced_schedule(team_dicts, **options)
        algorithm = "advanced"
    else:
        matches_data = generate_balanced_schedule(team_dicts, **options)
        algorithm = "balanced"

    # Validate (skip for random, which has violations by design). Nothing has
    # been deleted yet, so a refused schedule leaves the old one in place.
    if not use_random:
        violations = validate_schedule(matches_data)
        if algorithm == "balanced":
            allowed_rules = {"invalid_matches", "equal_match_counts", "balanced_colors"}
            violations = {
                rule: issues for rule, issues in violations.items() if rule in allowed_rules
            }
        if violations:
            return jsonify({
                "error": (
                    "Could not build a schedule that meets every rule with these "
                    "settings. Fewer arenas or more teams usually fixes back-to-back "
                    "matches. The current schedule was left as it was."
                ),
                "violations": violations,
            }), 400

    try:
        save_schedule(matches_data, teams, clear_existing=bool(clear_existing))
    except SQLAlchemyError as exc:
        return jsonify({"error": f"Could not save the schedule: {exc.__class__.__name__}."}), 500

    names = {t.team_number: t.name for t in teams}
    counts = {}
    for match_data in matches_data:
        for key in ("red_team_number", "blue_team_number"):
            counts[match_data[key]] = counts.get(match_data[key], 0) + 1
    last = max((m["scheduled_time"] for m in matches_data), default=None)

    return jsonify({
        "success": True,
        "matches_generated": len(matches_data),
        "arenas": sorted({m["arena"] for m in matches_data}),
        "algorithm": algorithm,
        "teams_scheduled": len(counts),
        "series_per_team": sorted(set(counts.values())),
        "last_slot": clock(datetime.strptime(last, "%Y-%m-%d %H:%M")) if last else None,
        "matches": [
            {
                "match_number": m["match_number"],
                "arena": m["arena"],
                "time": clock(datetime.strptime(m["scheduled_time"], "%Y-%m-%d %H:%M")),
                "red": f"{m['red_team_number']} {names.get(m['red_team_number'], '')}",
                "blue": f"{m['blue_team_number']} {names.get(m['blue_team_number'], '')}",
            }
            for m in matches_data
        ],
    })


@scheduler_bp.route("/api/validate", methods=["POST"])
@head_ref_required
def api_validate_current_schedule():
    """Validate the current schedule (for admin preview)."""
    matches = Match.query.filter_by(phase="qualification").all()
    teams_by_id = {t.id: t for t in Team.query.all()}

    matches_data = []
    for match in matches:
        red_team = teams_by_id.get(match.red_team_id)
        blue_team = teams_by_id.get(match.blue_team_id)
        matches_data.append({
            "match_number": match.match_number,
            "division": match.division,
            "scheduled_time": match.scheduled_time.strftime("%Y-%m-%d %H:%M") if match.scheduled_time else None,
            "red_team_number": red_team.team_number if red_team else None,
            "blue_team_number": blue_team.team_number if blue_team else None,
        })

    violations = validate_schedule(matches_data)
    return jsonify({
        "violations": violations,
        "valid": len(violations) == 0,
        "details": format_violations(violations),
    })
