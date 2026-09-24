# owner: Calvinpy
#
# Standalone tiebreak / standings logic. On purpose, nothing in this file
# imports Flask or the database — it only works with plain dicts, so it can
# be unit tested with made-up data and reused by anyone (seed script,
# scripts/, tests) without spinning up the app.

import re

WIN_POINTS = {"win": 3, "tie": 1, "loss": 0, "double_dq": 0}

ZONE_POINTS = {
    "out": 0,
    "band": 1,
    "plateau": 7,
}


def zone_points(zone_label):
    """Convert a final-zone string into its point value.

    Handles "Ring 2".."Ring 6" via regex so small formatting differences
    ("ring2", "Ring 3", "RING 4") all still work. Falls back to 0 for
    anything unrecognized rather than raising.
    """
    if zone_label is None:
        return 0
    key = zone_label.strip().lower()
    if key in ZONE_POINTS:
        return ZONE_POINTS[key]
    match = re.match(r"^ring\s*([2-6])$", key)
    if match:
        return int(match.group(1))
    return 0


def compute_team_records(teams, matches, results):
    """Build one record per team from plain-dict teams/matches/results.

    teams:   iterable of {"team_number", "team_name", "division"}
    matches: iterable of {"id", "division", "phase", "status",
                         "red_team_number", "blue_team_number"}
    results: iterable of {"match_id", "outcome", "win_time_seconds",
                         "red_final_zone", "blue_final_zone"}
                         outcome is one of "red", "blue", "tie", "double_dq"
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
            "win_points": 0,
            "ring_points": 0,
            "sp": 0,
            "_win_times": [],       # scratch, dropped before return
            "_opponents": [],       # scratch, dropped before return
        }
        for t in teams
    }

    qual_matches = [
        m for m in matches
        if m["phase"] == "qualification" and m["status"] == "complete"
    ]

    # Pass 1: Tally wins/losses/ties, win points, ring points, win times,
    # and remember who each team faced (needed for SP in pass 2).
    for match in qual_matches:
        result = results_by_match.get(match["id"])
        if result is None:
            continue  # marked complete but no result yet

        red_number = match["red_team_number"]
        blue_number = match["blue_team_number"]
        outcome = result["outcome"]
        win_time = result.get("win_time_seconds")
        red_zone = zone_points(result.get("red_final_zone"))
        blue_zone = zone_points(result.get("blue_final_zone"))

        for team_number, opponent_number, is_red, own_zone in (
            (red_number, blue_number, True, red_zone),
            (blue_number, red_number, False, blue_zone),
        ):
            record = records.get(team_number)
            if record is None:
                continue
            record["matches_played"] += 1
            record["ring_points"] += own_zone
            record["_opponents"].append(opponent_number)

            if outcome == "tie":
                record["ties"] += 1
                record["win_points"] += WIN_POINTS["tie"]
            elif outcome == "double_dq":
                record["losses"] += 1
                record["win_points"] += WIN_POINTS["double_dq"]
            elif (outcome == "red" and is_red) or (outcome == "blue" and not is_red):
                record["wins"] += 1
                record["win_points"] += WIN_POINTS["win"]
                if win_time is not None:
                    record["_win_times"].append(win_time)
            else:
                record["losses"] += 1
                record["win_points"] += WIN_POINTS["loss"]

    # Pass 2: SP needs every opponent's final win count
    for record in records.values():
        record["sp"] = sum(
            records[opp]["wins"] for opp in record["_opponents"] if opp in records
        )
        win_times = record.pop("_win_times")
        record["fastest_win_time"] = min(win_times) if win_times else None
        record.pop("_opponents")

    return list(records.values())


def _sort_key(record):
    """Sort key matching Rio's official tiebreak order."""
    fastest = record["fastest_win_time"] if record["fastest_win_time"] is not None else float("inf")
    return (
        -record["win_points"],
        -record["sp"],
        -record["ring_points"],
        fastest,
        record["team_number"],
    )


def tiebreak_sort(records):
    """Sort team records into official standings order and assign rank."""
    ordered = sorted(records, key=_sort_key)
    return [
        {**record, "rank": i}
        for i, record in enumerate(ordered, start=1)
    ]


def rank_division(teams, matches, results):
    """Convenience: compute records and sort them in one call."""
    records = compute_team_records(teams, matches, results)
    return tiebreak_sort(records)