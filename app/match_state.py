# owner: shared / lead
#
# The database side of app/series.py: reading a series' games, keeping
# Match.status in step with them, and the event-wide pause flag. Every
# blueprint that writes a game result (referee, admin) goes through
# refresh_series_status, so status can never disagree with the games.

from app.db import db
from app.models import Match, MatchResult, ScheduleState
from app.series import SeriesTally, tally


def games_for(match_id: int, include_voided: bool = True) -> list[MatchResult]:
    query = MatchResult.query.filter_by(match_id=match_id)
    if not include_voided:
        query = query.filter_by(voided=False)
    return query.order_by(MatchResult.game_number, MatchResult.id).all()


def series_tally(match: Match) -> SeriesTally:
    return tally(g.outcome for g in games_for(match.id, include_voided=False))


def next_game_number(match: Match) -> int:
    """The number the next game of this series will be recorded under.

    Counts voided games too: a replayed game 2 is followed by game 3, so the
    audit log never has two different games both called "game 2".
    """
    highest = (
        db.session.query(db.func.max(MatchResult.game_number))
        .filter(MatchResult.match_id == match.id)
        .scalar()
    )
    return (highest or 0) + 1


def refresh_series_status(match: Match) -> SeriesTally:
    """Recompute match.status from its games. Does not commit.

    Called after every write to a series' games, so an edit that un-decides a
    series (the head ref changes game 2's winner) puts it back in progress
    instead of leaving it marked complete.
    """
    result = series_tally(match)
    if result.winner is not None:
        match.status = "complete"
        match.game_started_at = None
    elif match.game_started_at is not None or games_for(match.id):
        match.status = "in_progress"
    else:
        match.status = "scheduled"
    return result


def series_winner_team_id(match: Match) -> int | None:
    winner = series_tally(match).winner
    if winner == "red":
        return match.red_team_id
    if winner == "blue":
        return match.blue_team_id
    return None


def is_paused() -> bool:
    """See ScheduleState in models.py for what paused means."""
    state = db.session.get(ScheduleState, 1)
    return bool(state and state.is_paused)


def arena_names() -> list[str]:
    """Every arena that has a match, in a stable order ("Arena 2" before "Arena 10")."""
    rows = db.session.query(Match.arena).distinct().all()
    names = [arena for (arena,) in rows if arena]

    def natural(name: str) -> tuple:
        head, _, tail = name.rpartition(" ")
        return (head, int(tail)) if tail.isdigit() else (name, 0)

    return sorted(names, key=natural)


def current_match_for_arena(arena: str) -> Match | None:
    """What the referee at `arena` should be running now.

    The series already in progress there, or failing that the next scheduled
    one whose two teams are both known. A bracket series waiting on an earlier
    result has a TBD side and is skipped until the bracket fills it in.
    """
    running = (
        Match.query.filter_by(arena=arena, status="in_progress")
        .order_by(Match.match_number)
        .first()
    )
    if running is not None:
        return running
    return (
        Match.query.filter(
            Match.arena == arena,
            Match.status == "scheduled",
            Match.red_team_id.isnot(None),
            Match.blue_team_id.isnot(None),
        )
        .order_by(Match.scheduled_time.asc().nullslast(), Match.match_number)
        .first()
    )
