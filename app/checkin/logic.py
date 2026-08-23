# owner: Shivani
# Pure functions for check-in and inspection: no Flask, no database.


def mark_checked_in(team, checked_in=True):
    """Return an updated copy of `team` with checked_in set.

    team: dict shaped like a Team (see app/fake_data.py)
    """
    pass


def record_inspection(team_id, checklist, inspector_name, notes=""):
    """Build a new inspection record from checklist answers.

    checklist: dict with keys size_ok, weight_ok, microbit_present,
    team_number_displayed, ref_start_stop_test (all bool)

    Should return a dict shaped like an Inspection, with `passed` computed
    from whether every checklist item is True. Does not save it — that's
    the route's job, once the database is wired up.
    """
    pass


def get_current_inspection(inspections_for_team):
    """Given all Inspection rows for one team, return the most recent one.

    inspections_for_team: list of dicts, each with an `inspected_at` value.
    Returns None if the list is empty.
    """
    pass
