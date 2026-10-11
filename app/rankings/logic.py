# owner: Jon
#
# Bridges the real database (app/models.py) to the pure functions in
# tiebreak.py, and answers the other display queries: current match, next
# few matches, and "what's my next match" for the pit lookup page.
#
# This file only reads. It never writes match/result data — that's the
# referee blueprint's job to create and the admin blueprint's job to edit.

from app.db import db
from app.models import Team, Match, MatchResult
from app.rankings.tiebreak import rank_division


def _team_to_dict(team):
    return {
        "team_number": team.team_number,
        "team_name": team.name,
        "division": team.division,
    }


def _match_to_dict(match):
    return {
        "id": match.id,
        "division": match.division,
        "phase": match.phase,
        "status": match.status,
        "red_team_number": _team_number_for(match.red_team_id),
        "blue_team_number": _team_number_for(match.blue_team_id),
    }


_team_number_cache = {}


def _team_number_for(team_id):
    """Small helper/cache so we don't issue a query per team per match."""
    if team_id is None:
        return None
    if team_id not in _team_number_cache:
        team = db.session.get(Team, team_id)
        _team_number_cache[team_id] = team.team_number if team else None
    return _team_number_cache[team_id]


def get_division_rankings(division):
    """Real replacement for fake_data.fake_rankings(division)."""
    _team_number_cache.clear()

    teams = Team.query.filter_by(division=division).all()
    matches = Match.query.filter_by(division=division, phase="qualification").all()

    # A replayed match keeps its row and its result so the audit trail still
    # resolves, but only one of the two counts toward standings — otherwise
    # the pairing pays out twice.
    #
    # The handover happens when the replay is COMPLETE, not when it is
    # scheduled. Voiding the original the moment a replay is ordered would
    # leave the pairing worth nothing until the replay actually runs, which
    # drops a team's points on the big screen and then puts them back. This
    # also matches the existing rule in tiebreak.py that only complete
    # matches count at all.
    # OPEN: whether a voided result should stop counting immediately instead
    # is Rio's call, not ours — see the note in the PR.
    superseded_ids = {
        m.replaces_match_id
        for m in matches
        if m.replaces_match_id is not None and m.status == "complete"
    }
    matches = [m for m in matches if m.id not in superseded_ids]

    match_ids = [m.id for m in matches]
    results = (
        MatchResult.query.filter(MatchResult.match_id.in_(match_ids)).all()
        if match_ids else []
    )

    team_dicts = [_team_to_dict(t) for t in teams]
    match_dicts = [_match_to_dict(m) for m in matches]
    result_dicts = [
        {
            "match_id": r.match_id,
            "outcome": r.outcome,
            "win_time_seconds": r.win_time_seconds,
            "red_final_zone": r.red_final_zone,
            "blue_final_zone": r.blue_final_zone,
        }
        for r in results
    ]

    return rank_division(team_dicts, match_dicts, result_dicts)


def _enrich_match(match):
    """Attach team names/numbers to a Match row for template display."""
    if match is None:
        return None
    red = db.session.get(Team, match.red_team_id) if match.red_team_id else None
    blue = db.session.get(Team, match.blue_team_id) if match.blue_team_id else None
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
    }


def get_current_match(division=None):
    """The match currently in progress, optionally filtered by division."""
    query = Match.query.filter_by(status="in_progress")
    if division:
        query = query.filter_by(division=division)
    match = query.order_by(Match.id.desc()).first()
    return _enrich_match(match)


def get_upcoming_matches(division=None, limit=3):
    """Real replacement for fake_data.upcoming_matches()."""
    query = Match.query.filter_by(status="scheduled")
    if division:
        query = query.filter_by(division=division)
    matches = (
        query.order_by(Match.scheduled_time.asc().nullslast(), Match.match_number.asc())
        .limit(limit)
        .all()
    )
    return [_enrich_match(m) for m in matches]


def get_team_next_match(team_number):
    """For the pit display: a team's next scheduled match, or None."""
    team = Team.query.filter_by(team_number=team_number).first()
    if team is None:
        return None, None

    match = (
        Match.query.filter(
            Match.status == "scheduled",
            db.or_(Match.red_team_id == team.id, Match.blue_team_id == team.id),
        )
        .order_by(Match.scheduled_time.asc().nullslast(), Match.match_number.asc())
        .first()
    )
    return team, _enrich_match(match)
