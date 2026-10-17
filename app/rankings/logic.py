# owner: Jon
#
# Bridges the real database (app/models.py) to the pure functions in
# tiebreak.py, and answers the other display queries: what is being played
# now, the next few series, and "what's my next match" for the pit page.
#
# This file only reads. It never writes match/result data — that's the
# referee blueprint's job to create and the admin blueprint's job to edit.

from flask import current_app

from app.db import db
from app.match_state import games_for, is_paused, next_game_number, series_tally
from app.models import Match, MatchResult, Team
from app.rankings.tiebreak import DEFAULT_DRAW_SEED, rank_division


def get_division_rankings(division):
    """Official T4 standings for one division, best first."""
    teams = Team.query.filter_by(division=division).all()
    number_by_id = {t.id: t.team_number for t in teams}
    matches = Match.query.filter_by(division=division, phase="qualification").all()

    # Legacy whole-match replays (see Match.replaces_match_id): once the
    # replay is complete, the match it replaced stops counting, so the
    # pairing is never paid out twice. Replays are per game now, through
    # MatchResult.voided, and tiebreak.py already skips voided games.
    superseded_ids = {
        m.replaces_match_id
        for m in matches
        if m.replaces_match_id is not None and m.status == "complete"
    }
    matches = [m for m in matches if m.id not in superseded_ids]

    match_ids = [m.id for m in matches]
    games = (
        MatchResult.query.filter(MatchResult.match_id.in_(match_ids)).all()
        if match_ids else []
    )

    team_dicts = [
        {"team_number": t.team_number, "team_name": t.name, "division": t.division}
        for t in teams
    ]
    match_dicts = [
        {
            "id": m.id,
            "division": m.division,
            "phase": m.phase,
            "red_team_number": number_by_id.get(m.red_team_id),
            "blue_team_number": number_by_id.get(m.blue_team_id),
        }
        for m in matches
    ]
    game_dicts = [
        {
            "match_id": g.match_id,
            "game_number": g.game_number,
            "outcome": g.outcome,
            "voided": g.voided,
        }
        for g in games
    ]

    draw_seed = current_app.config.get("RANKING_DRAW_SEED") or DEFAULT_DRAW_SEED
    return rank_division(team_dicts, match_dicts, game_dicts, draw_seed)


def _enrich_match(match):
    """Attach team names/numbers and the series score to a Match row."""
    if match is None:
        return None
    red = db.session.get(Team, match.red_team_id) if match.red_team_id else None
    blue = db.session.get(Team, match.blue_team_id) if match.blue_team_id else None
    score = series_tally(match)
    return {
        "id": match.id,
        "match_number": match.match_number,
        "phase": match.phase,
        "division": match.division,
        "arena": match.arena,
        "scheduled_time": match.scheduled_time,
        "status": match.status,
        "red_team_number": red.team_number if red else None,
        "red_team_name": red.name if red else "TBD",
        "blue_team_number": blue.team_number if blue else None,
        "blue_team_name": blue.name if blue else "TBD",
        "red_wins": score.red_wins,
        "blue_wins": score.blue_wins,
        "game_number": next_game_number(match),
        "game_running": match.game_started_at is not None,
        "games_played": len(games_for(match.id)),
    }


def get_current_matches(division=None):
    """Every series being played right now, one per arena at most."""
    query = Match.query.filter_by(status="in_progress")
    if division:
        query = query.filter_by(division=division)
    matches = query.order_by(Match.arena, Match.match_number).all()
    return [_enrich_match(m) for m in matches]


def get_current_match(division=None):
    """The first series in progress, for callers that only show one."""
    current = get_current_matches(division)
    return current[0] if current else None


def get_upcoming_matches(division=None, limit=3):
    """The next few series to be played whose teams are both known."""
    query = Match.query.filter(
        Match.status == "scheduled",
        Match.red_team_id.isnot(None),
        Match.blue_team_id.isnot(None),
    )
    if division:
        query = query.filter_by(division=division)
    matches = (
        query.order_by(Match.scheduled_time.asc().nullslast(), Match.match_number.asc())
        .limit(limit)
        .all()
    )
    return [_enrich_match(m) for m in matches]


def get_team_next_match(team_number):
    """For the pit display: the series a team is playing now, else its next one."""
    team = Team.query.filter_by(team_number=team_number).first()
    if team is None:
        return None, None

    match = (
        Match.query.filter(
            Match.status.in_(("in_progress", "scheduled")),
            db.or_(Match.red_team_id == team.id, Match.blue_team_id == team.id),
        )
        .order_by(
            (Match.status == "in_progress").desc(),
            Match.scheduled_time.asc().nullslast(),
            Match.match_number.asc(),
        )
        .first()
    )
    return team, _enrich_match(match)


def event_paused():
    return is_paused()
