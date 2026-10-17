"""The official ranking order, game manual T4, on hand-built cases.

Each case builds plain dicts, the same shape logic.py hands tiebreak.py, so
these run without the app or a database.
"""

from app.rankings.tiebreak import draw_value, rank_division
from app.series import tally


def teams(*numbers):
    return [{"team_number": n, "team_name": f"Team {n}", "division": "HS"} for n in numbers]


class Event:
    """Build series one at a time: series(red, blue, "red", "blue", ...)."""

    def __init__(self):
        self.matches = []
        self.games = []

    def series(self, red, blue, *outcomes, phase="qualification", voided=()):
        match_id = len(self.matches) + 1
        self.matches.append({
            "id": match_id, "division": "HS", "phase": phase,
            "red_team_number": red, "blue_team_number": blue,
        })
        for number, outcome in enumerate(outcomes, start=1):
            self.games.append({
                "match_id": match_id, "game_number": number,
                "outcome": outcome, "voided": number in voided,
            })

    def rank(self, *numbers, seed="test"):
        return {r["team_number"]: r for r in rank_division(teams(*numbers), self.matches, self.games, seed)}


def test_tally_first_to_two_and_ties_replay():
    assert tally(["red", "red"]).winner == "red"
    assert tally(["red", "tie", "blue", "tie", "blue"]).winner == "blue"
    assert tally(["red", "double_dq"]).winner is None
    # Games after the deciding one are not trusted.
    assert tally(["blue", "blue", "red", "red", "red"]).winner == "blue"


def test_points_come_first():
    e = Event()
    e.series(1, 2, "red", "red")          # 1 beats 2
    e.series(3, 4, "red", "blue", "red")  # 3 beats 4
    e.series(1, 3, "blue", "blue")        # 3 beats 1
    ranks = e.rank(1, 2, 3, 4)
    assert ranks[3]["qual_points"] == 6
    assert ranks[3]["rank"] == 1


def test_match_differential_breaks_equal_points():
    e = Event()
    e.series(1, 2, "red", "red")              # 1: +2
    e.series(3, 4, "red", "blue", "red")      # 3: +1
    ranks = e.rank(1, 2, 3, 4)
    assert ranks[1]["qual_points"] == ranks[3]["qual_points"] == 3
    assert (ranks[1]["match_diff"], ranks[3]["match_diff"]) == (2, 1)
    assert ranks[1]["rank"] < ranks[3]["rank"]
    assert not ranks[1]["decided_by_draw"]


def test_ties_are_not_counted_in_differential_but_double_dq_is_a_loss_for_both():
    e = Event()
    e.series(1, 2, "tie", "double_dq", "red", "red")
    ranks = e.rank(1, 2)
    assert (ranks[1]["match_wins"], ranks[1]["match_losses"], ranks[1]["match_ties"]) == (2, 1, 1)
    assert (ranks[2]["match_wins"], ranks[2]["match_losses"]) == (0, 3)


def test_strength_of_schedule_breaks_equal_points_and_differential():
    # 1 and 3 each win one series 2-0. 1 beat team 2, who went on to win a
    # series; 3 beat team 4, who won nothing. 1 played the stronger schedule.
    e = Event()
    e.series(1, 2, "red", "red")
    e.series(3, 4, "red", "red")
    e.series(2, 5, "red", "red")
    ranks = e.rank(1, 2, 3, 4, 5)
    assert ranks[1]["qual_points"] == ranks[3]["qual_points"] == 3
    assert ranks[1]["match_diff"] == ranks[3]["match_diff"] == 2
    assert (ranks[1]["sos"], ranks[3]["sos"]) == (3, 0)
    assert ranks[1]["rank"] < ranks[3]["rank"]


def test_strength_of_schedule_counts_an_opponent_once_per_series():
    e = Event()
    e.series(1, 2, "red", "red")
    e.series(2, 1, "red", "red")
    e.series(2, 3, "red", "red")
    ranks = e.rank(1, 2, 3)
    # Team 2 finished with 6 points and 1 played them twice.
    assert ranks[1]["sos"] == 12


def test_random_draw_is_stable_and_marked():
    e = Event()
    e.series(1, 2, "red", "red")
    e.series(3, 4, "red", "red")
    first = e.rank(1, 2, 3, 4)
    again = e.rank(1, 2, 3, 4)
    assert [first[n]["rank"] for n in (1, 3)] == [again[n]["rank"] for n in (1, 3)]
    assert first[1]["decided_by_draw"] and first[3]["decided_by_draw"]
    lower_draw = 1 if draw_value(1, "test") < draw_value(3, "test") else 3
    assert first[lower_draw]["rank"] == 1


def test_unfinished_series_voided_games_and_bracket_series_do_not_count():
    e = Event()
    e.series(1, 2, "red")                                   # undecided
    e.series(3, 4, "red", "red", "blue", "blue", voided=(2,))  # game 2 replayed: 4 wins 2-1
    e.series(1, 3, "red", "red", phase="elimination")       # bracket, not ranking
    ranks = e.rank(1, 2, 3, 4)
    assert ranks[1]["series_played"] == 0
    assert ranks[4]["qual_points"] == 3
    assert (ranks[4]["match_wins"], ranks[4]["match_losses"]) == (2, 1)
