# owner: Krish S
# Pure functions for the bracket: no Flask, no database. This is the other
# algorithm-heavy module — double-elimination losers'-bracket routing is
# the hard part, so get single elimination working and tested first.


def seed_bracket(final_rankings, bracket_size):
    """Turn a sorted rankings list into first-round bracket matchups.

    final_rankings: list of team dicts in final qualification order
    bracket_size: int, a power of two (byes fill any gap)

    Should return a list of first-round match dicts (see app/models.py
    Match: bracket_round=1, bracket_slot set, red/blue team ids set).
    """
    pass


def advance_winner(match, result):
    """Given a completed bracket Match and its MatchResult, figure out
    which bracket_round/bracket_slot the winner moves into next.

    A tie (result.outcome == "tie") should NOT advance anyone — instead
    the caller should insert a replay match in the same slot.
    """
    pass


def route_losers_bracket(match, result, is_double_elimination):
    """For double elimination only: figure out where the loser of `match`
    goes in the losers' bracket.

    Returns None if is_double_elimination is False, or if `match` is
    already a losers'-bracket match. This is the hardest part of the
    bracket module — get single elimination solid before starting this.
    """
    pass
