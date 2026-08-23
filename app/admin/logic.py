# owner: Yueyue
# Pure functions for admin: no Flask, no database.


def edit_result_with_audit(result, changes, changed_by):
    """Apply `changes` to a MatchResult dict and return both the updated
    result and the list of AuditEntry dicts describing what changed.

    result: dict shaped like a MatchResult
    changes: dict of field -> new_value
    changed_by: str, the admin's name

    Every field in `changes` must produce one AuditEntry with the field
    name, old_value, and new_value — a result may only be edited through
    this function so nothing changes silently.
    """
    pass


def pause_schedule(matches):
    """Return a copy of `matches` with all still-scheduled matches marked
    paused, so the schedule can be resumed later without losing state.
    """
    pass


def insert_replay_match(original_match, matches):
    """Build a new replay Match dict for `original_match` (same teams,
    same arena, is_replay=True) and return it inserted into `matches` right
    after the original.
    """
    pass
