# owner: shared / lead
#
# Fake data for every blueprint to build against, before the real database
# is wired up. Everyone's routes.py imports from here and hands these plain
# Python dicts straight to their templates.
#
# This is NOT the real database. It's throwaway data shaped like the models
# in app/models.py, so templates can look correct before any real logic
# exists. When a module's real logic is ready, it should start reading from
# the database instead of this file.

# The competition runs a single division, so DIVISION is the canonical name
# and nothing asks anyone to pick one. DIVISIONS stays a list because the
# schedule, rankings and bracket pages loop over it.
DIVISION = "High School"
DIVISIONS = [DIVISION]

_SCHOOLS = [
    "Lincoln Elementary", "Oakwood Middle School", "Riverside STEM Academy",
    "Independent", "Maple Grove Elementary", "Central Middle School",
    "Independent", "Hillcrest Elementary", "Westview Middle School",
    "Independent", "Sunnydale Elementary", "Independent",
]

_STUDENT_POOL = [
    "Ava", "Liam", "Noah", "Emma", "Mia", "Ethan", "Sofia", "Lucas",
    "Zoe", "Mason", "Ella", "Owen", "Grace", "Leo", "Nora", "Kai",
    "Ruby", "Sam", "Ivy", "Theo", "Luna", "Max", "Isla", "Finn",
]

TEAMS = []


def _make_teams():
    team_id = 1
    for division_index, division in enumerate(DIVISIONS):
        # Middle School teams start at 200, Elementary teams start at 100
        base_number = 100 + division_index * 100
        for i in range(12):
            team_number = base_number + i + 1
            school = _SCHOOLS[i % len(_SCHOOLS)]
            student_count = 1 + (team_id % 4)  # varies 1-4
            students = [
                _STUDENT_POOL[(team_id * 3 + j) % len(_STUDENT_POOL)]
                for j in range(student_count)
            ]
            TEAMS.append({
                "id": team_id,
                "team_number": team_number,
                "name": f"Team {team_number}",
                "affiliation": school,
                "division": division,
                "students": students,
                "adult_name": f"Adult of Team {team_number}",
                "adult_email": f"adult{team_number}@example.com",
                "adult_phone": "555-010" + str(team_id % 10),
                "kit_ordered": team_id % 3 != 0,
                "checked_in": team_id % 4 != 0,
            })
            team_id += 1


_make_teams()

TEAMS_BY_NUMBER = {team["team_number"]: team for team in TEAMS}


def get_team(team_number):
    """Look up a fake team by its team number. Returns None if not found."""
    return TEAMS_BY_NUMBER.get(team_number)


# --- Inspections -----------------------------------------------------------
# One entry per inspected team. A couple of teams have two entries to show
# what a re-inspection looks like.

INSPECTIONS = [
    {
        "id": 1, "team_number": 101, "passed": True, "size_ok": True,
        "weight_ok": True, "microbit_present": True,
        "team_number_displayed": True, "ref_start_stop_test": True,
        "notes": "", "inspector_name": "Coach Diaz",
    },
    {
        "id": 2, "team_number": 102, "passed": False, "size_ok": True,
        "weight_ok": False, "microbit_present": True,
        "team_number_displayed": True, "ref_start_stop_test": True,
        "notes": "Over weight limit by 40g", "inspector_name": "Coach Diaz",
    },
    {
        "id": 3, "team_number": 102, "passed": True, "size_ok": True,
        "weight_ok": True, "microbit_present": True,
        "team_number_displayed": True, "ref_start_stop_test": True,
        "notes": "Trimmed base plate, re-weighed OK", "inspector_name": "Coach Diaz",
    },
    {
        "id": 4, "team_number": 201, "passed": True, "size_ok": True,
        "weight_ok": True, "microbit_present": True,
        "team_number_displayed": True, "ref_start_stop_test": True,
        "notes": "", "inspector_name": "Coach Patel",
    },
]


# --- Matches + results -------------------------------------------------------
# Qualification matches for both divisions. Some are "complete" with a
# result, some are still "scheduled".

MATCHES = []
RESULTS = []

_ZONES = ["Center", "Red Zone", "Blue Zone", "Off Arena"]
_OUTCOMES = ["red", "blue", "tie", "double_dq"]


def _make_matches():
    match_id = 1
    result_id = 1
    for division_index, division in enumerate(DIVISIONS):
        base_number = 100 + division_index * 100
        team_numbers = [base_number + i + 1 for i in range(12)]
        match_number = 1
        # Pair teams up round-robin style for a handful of quals matches.
        for round_offset in range(5):
            for i in range(0, len(team_numbers), 2):
                if i + 1 >= len(team_numbers):
                    continue
                red = team_numbers[(i + round_offset) % len(team_numbers)]
                blue = team_numbers[(i + 1 + round_offset) % len(team_numbers)]
                if red == blue:
                    continue
                arena = "Arena 1" if match_id % 2 == 0 else "Arena 2"
                # First few rounds are complete, later ones still scheduled.
                is_complete = round_offset < 3
                match = {
                    "id": match_id,
                    "match_number": match_number,
                    "phase": "qualification",
                    "division": division,
                    "arena": arena,
                    "scheduled_time": f"2026-09-12 {9 + (match_id % 6)}:{'00' if match_id % 2 else '30'}",
                    "red_team_number": red,
                    "blue_team_number": blue,
                    "status": "complete" if is_complete else "scheduled",
                    "is_replay": False,
                    "bracket_round": None,
                    "bracket_slot": None,
                }
                MATCHES.append(match)

                if is_complete:
                    outcome = _OUTCOMES[match_id % len(_OUTCOMES)]
                    RESULTS.append({
                        "id": result_id,
                        "match_id": match_id,
                        "outcome": outcome,
                        "win_time_seconds": round(3.5 + (match_id % 10) * 0.8, 2),
                        "red_final_zone": _ZONES[match_id % len(_ZONES)],
                        "blue_final_zone": _ZONES[(match_id + 1) % len(_ZONES)],
                        "submitted_by": f"Referee {'A' if match_id % 2 else 'B'}",
                    })
                    result_id += 1

                match_id += 1
                match_number += 1


_make_matches()

MATCHES_BY_ID = {match["id"]: match for match in MATCHES}
RESULTS_BY_MATCH_ID = {result["match_id"]: result for result in RESULTS}

# One match still "in_progress" so the referee current-match page has
# something to show.
if MATCHES:
    MATCHES[-1]["status"] = "in_progress"

CURRENT_MATCH = MATCHES[-1] if MATCHES else None


def upcoming_matches(division=None, limit=3):
    """Return the next few scheduled matches, optionally filtered by division."""
    matches = [m for m in MATCHES if m["status"] == "scheduled"]
    if division:
        matches = [m for m in matches if m["division"] == division]
    return matches[:limit]


# --- Rankings ----------------------------------------------------------------
# Hardcoded standings, shaped like what Jon's real tiebreak_sort() will
# eventually produce: one row per team, ordered by rank.

def fake_rankings(division):
    """Return a fake, already-sorted list of ranking rows for a division."""
    teams = [t for t in TEAMS if t["division"] == division]
    rankings = []
    for rank, team in enumerate(teams, start=1):
        rankings.append({
            "rank": rank,
            "team_number": team["team_number"],
            "team_name": team["name"],
            "wins": max(0, 5 - rank // 2),
            "losses": min(5, rank // 2),
            "ties": 1 if rank % 4 == 0 else 0,
            "avg_win_time": round(4.0 + rank * 0.3, 2),
        })
    return rankings


# --- Bracket -------------------------------------------------------------
# A small single-elimination bracket for one division, fake data only.

BRACKET_ROUNDS = [
    {
        "round_number": 1,
        "round_name": "Quarterfinals",
        "matches": [
            {"slot": 1, "red": "Team 101", "blue": "Team 108", "winner": "Team 101"},
            {"slot": 2, "red": "Team 104", "blue": "Team 105", "winner": "Team 105"},
            {"slot": 3, "red": "Team 102", "blue": "Team 107", "winner": "Team 102"},
            {"slot": 4, "red": "Team 103", "blue": "Team 106", "winner": "Team 103"},
        ],
    },
    {
        "round_number": 2,
        "round_name": "Semifinals",
        "matches": [
            {"slot": 1, "red": "Team 101", "blue": "Team 105", "winner": "Team 101"},
            {"slot": 2, "red": "Team 102", "blue": "Team 103", "winner": None},
        ],
    },
    {
        "round_number": 3,
        "round_name": "Final",
        "matches": [
            {"slot": 1, "red": "Team 101", "blue": "TBD", "winner": None},
        ],
    },
]


# --- Audit log ---------------------------------------------------------------

AUDIT_ENTRIES = [
    {
        "id": 1, "match_id": 3, "changed_by": "Head Ref",
        "changed_at": "2026-09-12 10:15", "field": "outcome",
        "old_value": "tie", "new_value": "red",
    },
]
