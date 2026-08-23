# owner: Jon
# Pure functions for rankings: no Flask, no database.
#
# Official tiebreak order isn't defined yet — see the "Open questions"
# section of CLAUDE.md. tiebreak_sort() below is the one function that
# depends on that decision.


def tiebreak_sort(teams_with_records):
    """Sort teams into the official standings order.

    teams_with_records: list of dicts, one per team, with whatever fields
    the tiebreak needs (wins, losses, ties, average win time, etc).

    Waiting on the official tiebreak order before this can be written for
    real — see CLAUDE.md open questions.
    """
    pass


def compute_standings(matches, results):
    """Turn a list of Match + MatchResult data into one row per team:
    wins, losses, ties, and whatever else tiebreak_sort() will need.

    matches: list of Match dicts
    results: list of MatchResult dicts, keyed by match_id

    Ties are legal in qualification. In elimination a tie forces a replay
    instead of counting toward a team's record.
    """
    pass
