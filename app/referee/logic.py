# owner: Serena
# Pure functions for the referee flow: no Flask, no database.


def start_match(match, start_time):
    """Return an updated copy of `match` marked in_progress, with a
    recorded start_time.

    This is also the point that would trigger the referee micro:bit over
    whatever start signal it uses — that trigger itself doesn't belong in
    this pure function, only the state change does.
    """
    pass


def submit_result(match, outcome, start_time, winner_tap_time, red_final_zone, blue_final_zone, submitted_by):
    """Build a MatchResult dict from the raw inputs collected on screen.

    win_time_seconds should be computed as winner_tap_time - start_time.
    outcome must be one of "red", "blue", "tie", "double_dq".
    """
    pass


def lock_match(match):
    """Return an updated copy of `match` marked complete and no longer
    editable from the referee page (further edits go through admin).
    """
    pass
