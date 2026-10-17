# owner: shared / lead
#
# The rules of a best-of-three series, as plain data. No Flask, no database:
# the referee page, the admin panel, rankings and the bracket all need the
# same answer to "who has won this series", and a pure function is the only
# way to be sure they get it. app/match_state.py is the database side.
#
# Source: SRC Summit game manual v1.0, sections 3.2, 4, T3 and T5.

from collections.abc import Iterable
from dataclasses import dataclass

# The four values the data contract (models.py MatchResult.outcome) names.
VALID_OUTCOMES = ("red", "blue", "tie", "double_dq")

# Where each robot's drive wheels finished, judged at time or at a dead stall
# (manual 3.2). The five rings are the manual's names, centre outwards, plus
# a ring-out for a robot that left the Hill. Only the referee's record of the
# game reads these: the manual's ranking (T4) does not use them.
VALID_ZONES = (
    "Plateau",
    "Inner Slope",
    "Outer Slope",
    "Flat Band",
    "Edge Band",
    "Ring-out",
)

# First to two game wins takes the series (T3, T5).
WINS_NEEDED = 2

# A game runs three minutes (manual, "The match"). The referee timer marks it.
GAME_SECONDS = 180


@dataclass(frozen=True)
class SeriesTally:
    red_wins: int
    blue_wins: int
    games_counted: int
    winner: str | None  # "red", "blue", or None while undecided


def tally(outcomes: Iterable[str]) -> SeriesTally:
    """Score a series from its counted (non-voided) game outcomes, in order.

    A tie wins nothing and is replayed by the next game. A double DQ is a loss
    for both teams, so it also wins nothing for either. Games after the
    deciding one are ignored rather than trusted: the referee page refuses to
    record them, so one only exists if somebody edited the database by hand.
    """
    red_wins = 0
    blue_wins = 0
    counted = 0
    winner = None
    for outcome in outcomes:
        if winner is not None:
            break
        counted += 1
        if outcome == "red":
            red_wins += 1
        elif outcome == "blue":
            blue_wins += 1
        if red_wins >= WINS_NEEDED:
            winner = "red"
        elif blue_wins >= WINS_NEEDED:
            winner = "blue"
    return SeriesTally(red_wins, blue_wins, counted, winner)


def game_result_for(side: str, outcome: str) -> str | None:
    """What one game meant for the team on `side`: "win", "loss" or None.

    None is a tie, which is replayed and so is neither a win nor a loss for
    match differential (T4). A double DQ is a loss for both teams.
    """
    if outcome == "tie":
        return None
    if outcome == "double_dq":
        return "loss"
    return "win" if outcome == side else "loss"
