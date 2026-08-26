# owner: Jon
#
# Standalone tiebreak / standings logic. On purpose, nothing in this file
# imports Flask or the database — it only works with plain dicts, so it can
# be unit tested with made-up data and reused by anyone (seed script,
# scripts/, tests) without spinning up the app.
#
# ASSUMPTION (no official tiebreak sheet existed for this event as of this
# writing — confirm with the head ref / STEMsters rules doc and adjust
# RANKING_POINTS / _sort_key below if the real rule differs):
#
#   Only QUALIFICATION-phase, COMPLETE matches count toward standings.
#   Elimination matches never affect rank — ties are legal in quals (they
#   just split ranking points) but trigger a replay in elimination instead
#   of ever being "recorded" as a tie. That's the bracket module's job, not
#   this file's; by only reading phase == "qualification" here, elimination
#   replays can never leak into a team's official record.
#
#   Standings order, highest priority first:
#     1. Ranking points  (win = 2, tie = 1, loss = 0, double_dq = 0 for both)
#     2. Total wins
#     3. Average win time, ascending, counting only matches this team WON
#        (teams with zero wins sort after teams with at least one, since
#        there's no win time to compare)
#     4. Team number, ascending — deterministic, arbitrary-but-stable final
#        tiebreak so the ordering never depends on dict/insert order.

RANKING_POINTS = {"win": 2, "tie": 1, "loss": 0, "double_dq": 0}


def compute_team_records(teams, matches, results):
    """Build one record per team from plain-dict teams/matches/results.

    teams:   iterable of {"team_number", "team_name", "division"}
    matches: iterable of {"id", "division", "phase", "status",
                           "red_team_number", "blue_team_number"}
    results: iterable of {"match_id", "outcome", "win_time_seconds"}
             outcome is one of "red", "blue", "tie", "double_dq"

    Returns one dict per team (unsorted) with wins/losses/ties/ranking_points
    /avg_win_time/matches_played filled in. Teams that haven't played yet
    still get a record, all zeros.
    """
    results_by_match = {r["match_id"]: r for r in results}

    records = {
        t["team_number"]: {
            "team_number": t["team_number"],
            "team_name": t["team_name"],
            "division": t["division"],
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "matches_played": 0,
            "ranking_points": 0,
            "_win_times": [],  # private scratch field, dropped before return
        }
        for t in teams
    }

    qual_matches = [
        m for m in matches
        if m["phase"] == "qualification" and m["status"] == "complete"
    ]

    for match in qual_matches:
        result = results_by_match.get(match["id"])
        if result is None:
            continue  # marked complete but no result yet — shouldn't happen, skip defensively

        red_number = match["red_team_number"]
        blue_number = match["blue_team_number"]
        outcome = result["outcome"]
        win_time = result.get("win_time_seconds")

        for team_number, is_red in ((red_number, True), (blue_number, False)):
            record = records.get(team_number)
            if record is None:
                continue  # team not in this division's roster, ignore
            record["matches_played"] += 1

            if outcome == "tie":
                record["ties"] += 1
            elif outcome == "double_dq":
                record["losses"] += 1
            elif (outcome == "red" and is_red) or (outcome == "blue" and not is_red):
                record["wins"] += 1
                if win_time is not None:
                    record["_win_times"].append(win_time)
            else:
                record["losses"] += 1

    for record in records.values():
        record["ranking_points"] = (
            record["wins"] * RANKING_POINTS["win"] + record["ties"] * RANKING_POINTS["tie"]
        )
        win_times = record.pop("_win_times")
        record["avg_win_time"] = round(sum(win_times) / len(win_times), 2) if win_times else None

    return list(records.values())


def _sort_key(record):
    # Lower sorts first, so negate the "higher is better" fields.
    # A team with no wins has avg_win_time == None; push it to the back of
    # that particular comparison with float("inf").
    avg_win_time = record["avg_win_time"] if record["avg_win_time"] is not None else float("inf")
    return (
        -record["ranking_points"],
        -record["wins"],
        avg_win_time,
        record["team_number"],
    )


def tiebreak_sort(records):
    """Sort team records into official standings order and assign rank.

    Ties on every field above (including team number, which can't actually
    tie) get sequential ranks in a stable, deterministic order — this is a
    display ranking, not a bracket seed with co-champions.
    """
    ordered = sorted(records, key=_sort_key)
    return [
        {**record, "rank": i}
        for i, record in enumerate(ordered, start=1)
    ]


def rank_division(teams, matches, results):
    """Convenience: compute records and sort them in one call."""
    records = compute_team_records(teams, matches, results)
    return tiebreak_sort(records)
