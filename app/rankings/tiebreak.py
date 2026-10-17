# owner: Calvinpy
#
# Standalone tiebreak / standings logic. On purpose, nothing in this file
# imports Flask or the database — it only works with plain dicts, so it can
# be unit tested with made-up data and reused by anyone (seed script,
# scripts/, tests) without spinning up the app.
#
# The official order is the game manual's T4 (Summit manual v1.0):
#   1. qualification points  — 3 per series won, 0 per series lost
#   2. match differential    — qualification matches won minus lost
#   3. strength of schedule  — the final qualification points of every
#                              opponent, counted once per series played
#   4. random draw
# Each qualification pairing is a best-of-three series (T3), so a "match" in
# T4 is one game of a series here — one MatchResult row.

import hashlib

from app.series import game_result_for, tally

SERIES_WIN_POINTS = 3
SERIES_LOSS_POINTS = 0

DEFAULT_DRAW_SEED = "SRC Summit 2026"


def draw_value(team_number, draw_seed=DEFAULT_DRAW_SEED):
    """This team's ticket in the T4 random draw. Lower draws rank higher.

    A hash rather than random.random(): the draw must give the same order on
    every page load, every server, and after a restart, or tied teams would
    swap places on the big screen every refresh.
    """
    digest = hashlib.sha256(f"{draw_seed}:{team_number}".encode()).hexdigest()
    return int(digest[:16], 16)


def compute_team_records(teams, matches, games, draw_seed=DEFAULT_DRAW_SEED):
    """Build one record per team from plain-dict teams/matches/games.

    teams:   iterable of {"team_number", "team_name", "division"}
    matches: iterable of {"id", "division", "phase",
                          "red_team_number", "blue_team_number"}
             — one per series
    games:   iterable of {"match_id", "game_number", "outcome", "voided"}
             — one per game; outcome is "red", "blue", "tie" or "double_dq"

    Only a decided series counts: until someone has two wins, neither its
    points, its games nor its opponent appear in anybody's record. Counting a
    half-played series would rank a team on a result that does not exist yet.
    """
    games_by_match = {}
    for game in games:
        if game.get("voided"):
            continue
        games_by_match.setdefault(game["match_id"], []).append(game)

    records = {
        t["team_number"]: {
            "team_number": t["team_number"],
            "team_name": t["team_name"],
            "division": t["division"],
            "series_played": 0,
            "series_wins": 0,
            "series_losses": 0,
            "qual_points": 0,
            "match_wins": 0,
            "match_losses": 0,
            "match_ties": 0,
            "match_diff": 0,
            "sos": 0,
            "draw": draw_value(t["team_number"], draw_seed),
            "_opponents": [],  # scratch, dropped before return
        }
        for t in teams
    }

    for match in matches:
        if match["phase"] != "qualification":
            continue
        series_games = sorted(
            games_by_match.get(match["id"], []), key=lambda g: g["game_number"]
        )
        result = tally(g["outcome"] for g in series_games)
        if result.winner is None:
            continue
        counted_games = series_games[: result.games_counted]

        for side, team_number, opponent_number in (
            ("red", match["red_team_number"], match["blue_team_number"]),
            ("blue", match["blue_team_number"], match["red_team_number"]),
        ):
            record = records.get(team_number)
            if record is None:
                continue
            record["series_played"] += 1
            if result.winner == side:
                record["series_wins"] += 1
                record["qual_points"] += SERIES_WIN_POINTS
            else:
                record["series_losses"] += 1
                record["qual_points"] += SERIES_LOSS_POINTS
            record["_opponents"].append(opponent_number)

            for game in counted_games:
                outcome = game_result_for(side, game["outcome"])
                if outcome == "win":
                    record["match_wins"] += 1
                elif outcome == "loss":
                    record["match_losses"] += 1
                else:
                    record["match_ties"] += 1

    # Strength of schedule needs every opponent's FINAL points, so it waits
    # until every series has been tallied.
    for record in records.values():
        record["match_diff"] = record["match_wins"] - record["match_losses"]
        record["sos"] = sum(
            records[opp]["qual_points"] for opp in record.pop("_opponents") if opp in records
        )

    return list(records.values())


def _sort_key(record):
    """Sort key for the official T4 order."""
    return (
        -record["qual_points"],
        -record["match_diff"],
        -record["sos"],
        record["draw"],
    )


def tiebreak_sort(records):
    """Sort team records into official standings order and assign rank.

    decided_by_draw marks a team whose place against a neighbour came down to
    the random draw, so a standings page can say so instead of implying the
    draw was a result.
    """
    ordered = sorted(records, key=_sort_key)
    ranked = []
    for i, record in enumerate(ordered):
        tied = _sort_key(record)[:3]
        before = _sort_key(ordered[i - 1])[:3] if i > 0 else None
        after = _sort_key(ordered[i + 1])[:3] if i + 1 < len(ordered) else None
        ranked.append(
            {**record, "rank": i + 1, "decided_by_draw": tied in (before, after)}
        )
    return ranked


def rank_division(teams, matches, games, draw_seed=DEFAULT_DRAW_SEED):
    """Convenience: compute records and sort them in one call."""
    records = compute_team_records(teams, matches, games, draw_seed)
    return tiebreak_sort(records)
