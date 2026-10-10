# owner: Shaurya
# Generates and displays the qualification schedule: full list, per-arena,
# and per-team views.

from datetime import datetime
from flask import render_template, jsonify, request

from app.db import db
from app.models import Match, Team
from app.scheduler import scheduler_bp
from app.scheduler.generator import (
    generate_random_schedule,
    generate_balanced_schedule,
    generate_advanced_schedule,
    validate_schedule,
    format_violations,
)


def _enrich_matches(matches):
    """Attach red/blue team names to each match for display."""
    # Preload all teams
    all_teams = Team.query.all()
    teams_by_id = {t.id: t for t in all_teams}
    
    enriched = []
    for match in matches:
        red_team = teams_by_id.get(match.red_team_id)
        blue_team = teams_by_id.get(match.blue_team_id)
        
        enriched.append({
            "match_number": match.match_number,
            "division": match.division,
            "arena": match.arena,
            "scheduled_time": match.scheduled_time.strftime("%Y-%m-%d %H:%M") if match.scheduled_time else "TBD",
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
    return render_template("scheduler/schedule_full.html", matches=enriched)


@scheduler_bp.route("/arena/<arena>")
def schedule_by_arena(arena):
    """Display the qualification schedule for a specific arena (printable)."""
    arena_name = arena.replace("_", " ")
    matches = Match.query.filter_by(phase="qualification", arena=arena_name).order_by(
        Match.scheduled_time
    ).all()
    enriched = _enrich_matches(matches)
    return render_template(
        "scheduler/schedule_by_arena.html",
        arena=arena_name,
        matches=enriched,
    )


@scheduler_bp.route("/team/<int:team_number>")
def schedule_by_team(team_number):
    """Display the qualification schedule for a specific team (pit lookup)."""
    team = Team.query.filter_by(team_number=team_number).first()
    if not team:
        return render_template("scheduler/schedule_by_team.html", team_number=team_number, matches=[])
    
    matches = Match.query.filter_by(phase="qualification").filter(
        (Match.red_team_id == team.id) | (Match.blue_team_id == team.id)
    ).order_by(Match.scheduled_time).all()
    
    enriched = _enrich_matches(matches)
    return render_template(
        "scheduler/schedule_by_team.html",
        team_number=team_number,
        matches=enriched,
    )


@scheduler_bp.route("/admin")
def admin():
    """Admin page for schedule generation and validation."""
    return render_template("scheduler/admin.html")


@scheduler_bp.route("/api/generate", methods=["POST"])
def api_generate_schedule():
    """Generate a new schedule and save to database (for admin)."""
    try:
        # Get request parameters
        data = request.get_json() or {}
        use_random = data.get("use_random", False)
        use_balanced = data.get("use_balanced", False)
        use_advanced = data.get("use_advanced", False)
        matches_per_team = data.get("matches_per_team", 5)
        clear_existing = data.get("clear_existing", True)
        
        # Clear existing qualification matches if requested
        if clear_existing:
            Match.query.filter_by(phase="qualification").delete()
        
        # Get all teams
        teams = Team.query.all()
        if not teams:
            return jsonify({"error": "No teams registered"}), 400
        
        # Convert teams to the format expected by the generator
        team_dicts = [
            {
                "team_number": t.team_number,
                "division": t.division,
            }
            for t in teams
        ]
        
        # Generate schedule using appropriate algorithm
        if use_random:
            matches_data = generate_random_schedule(team_dicts, matches_per_team=matches_per_team)
            algorithm = "random"
        elif use_advanced:
            matches_data = generate_advanced_schedule(team_dicts, matches_per_team=matches_per_team)
            algorithm = "advanced"
        elif use_balanced or not use_random:
            matches_data = generate_balanced_schedule(team_dicts, matches_per_team=matches_per_team)
            algorithm = "balanced"
        
        # Validate (skip for random, which has violations by design)
        if not use_random:
            violations = validate_schedule(matches_data)
            if algorithm == "balanced":
                allowed_rules = {"invalid_matches", "equal_match_counts", "balanced_colors"}
                violations = {
                    rule: issues
                    for rule, issues in violations.items()
                    if rule in allowed_rules
                }
            if violations:
                return jsonify({
                    "error": "Generated schedule has violations",
                    "violations": violations,
                }), 400
        
        # Save to database
        team_by_number = {t.team_number: t for t in teams}
        arenas_seen = set()
        
        for match_data in matches_data:
            red_team = team_by_number.get(match_data["red_team_number"])
            blue_team = team_by_number.get(match_data["blue_team_number"])
            
            if not red_team or not blue_team:
                continue
            
            # Parse scheduled time
            scheduled_time = datetime.strptime(
                match_data["scheduled_time"],
                "%Y-%m-%d %H:%M"
            )
            
            match = Match(
                match_number=match_data["match_number"],
                phase="qualification",
                division=match_data["division"],
                arena=match_data["arena"],
                scheduled_time=scheduled_time,
                red_team_id=red_team.id,
                blue_team_id=blue_team.id,
                status="scheduled",
                is_replay=False,
            )
            db.session.add(match)
            arenas_seen.add(match_data["arena"])
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "matches_generated": len(matches_data),
            "arenas": sorted(list(arenas_seen)),
            "algorithm": algorithm,
            "statistics": None,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@scheduler_bp.route("/api/validate", methods=["POST"])
def api_validate_current_schedule():
    """Validate the current schedule (for admin preview)."""
    try:
        matches = Match.query.filter_by(phase="qualification").all()
        
        # Get all teams for lookup
        teams_by_id = {t.id: t for t in Team.query.all()}
        
        # Convert to the format expected by the validator
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
    except Exception as e:
        return jsonify({"error": str(e)}), 500


