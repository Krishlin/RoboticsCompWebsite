# owner: Shaurya
#
# The database side of the schedule generator: whether the schedule can still
# be replaced, and saving a generated schedule as Match rows. Shared by the
# head ref's "Generate" button (routes.py) and the pre-made schedule script
# (seed/schedule.py), so both refuse and save in exactly the same way.

from datetime import datetime
from typing import Any

from app.db import db
from app.models import Match, MatchResult, Team


def played_qualification_count() -> int:
    """How many qualification series have been started or have a result.

    Regenerating is refused once this is above zero. Clearing deletes the
    qualification matches but not their results, audit entries or replays,
    which all point at match ids: on SQLite the ids get reused and old results
    silently attach to new, different pairings; on Postgres the foreign keys
    make the delete fail.
    """
    return Match.query.filter(
        Match.phase == "qualification",
        db.or_(
            Match.status != "scheduled",
            Match.id.in_(db.session.query(MatchResult.match_id)),
        ),
    ).count()


def save_schedule(
    matches_data: list[dict[str, Any]], teams: list[Team], clear_existing: bool = True
) -> None:
    """Write a generated schedule, replacing the unplayed one. Commits.

    Raises SQLAlchemyError on a failed write, after rolling back, so the old
    schedule is left as it was.
    """
    try:
        if clear_existing:
            Match.query.filter_by(phase="qualification").delete()

        team_by_number = {t.team_number: t for t in teams}
        for match_data in matches_data:
            red_team = team_by_number.get(match_data["red_team_number"])
            blue_team = team_by_number.get(match_data["blue_team_number"])
            if not red_team or not blue_team:
                continue
            db.session.add(
                Match(
                    match_number=match_data["match_number"],
                    phase="qualification",
                    division=match_data["division"],
                    arena=match_data["arena"],
                    scheduled_time=datetime.strptime(
                        match_data["scheduled_time"], "%Y-%m-%d %H:%M"
                    ),
                    red_team_id=red_team.id,
                    blue_team_id=blue_team.id,
                    status="scheduled",
                    is_replay=False,
                )
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
