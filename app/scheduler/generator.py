# owner: Shaurya
# Match schedule generator and validator for qualification rounds.
#
# Week 2:
# - Random generator that ignores constraints.
#
# Week 3:
# - Equal match counts (when mathematically possible).
# - Rough red/blue balance.
# - Validator for core constraints.
#
# Weeks 4-5:
# - Advanced generator that avoids back-to-back matches.
# - Avoid repeat pairings until they are mathematically necessary.

import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


def _group_teams_by_division(teams: List[Dict[str, Any]]) -> Dict[str, List[int]]:
    grouped: Dict[str, List[int]] = {}
    for team in teams:
        division = team.get("division", "High School")
        grouped.setdefault(division, []).append(team["team_number"])
    return grouped


def _target_matches_per_team(team_count: int, requested_matches_per_team: int) -> int:
    if team_count < 2:
        return 0
    if (team_count * requested_matches_per_team) % 2 == 0:
        return requested_matches_per_team
    return max(0, requested_matches_per_team - 1)


def _build_match(
    match_number: int,
    division: str,
    absolute_slot_index: int,
    arena: str,
    red_team_number: int,
    blue_team_number: int,
    arenas: List[str],
) -> Dict[str, Any]:
    start_time = datetime(2026, 9, 12, 9, 0)
    scheduled_time = start_time + timedelta(minutes=(absolute_slot_index // len(arenas)) * 15)
    return {
        "match_number": match_number,
        "phase": "qualification",
        "division": division,
        "arena": arena,
        "scheduled_time": scheduled_time.strftime("%Y-%m-%d %H:%M"),
        "red_team_number": red_team_number,
        "blue_team_number": blue_team_number,
    }


def generate_random_schedule(
    teams: List[Dict[str, Any]],
    arenas: List[str] = None,
    matches_per_team: int = 5,
) -> List[Dict[str, Any]]:
    """Week 2: random schedule that ignores constraints."""
    if arenas is None:
        arenas = ["Arena 1", "Arena 2"]

    teams_by_division = _group_teams_by_division(teams)
    matches: List[Dict[str, Any]] = []
    match_number = 1
    absolute_slot_index = 0

    for division, team_numbers in teams_by_division.items():
        if len(team_numbers) < 2:
            continue

        target = _target_matches_per_team(len(team_numbers), matches_per_team)
        total_matches = (len(team_numbers) * target) // 2

        for index in range(total_matches):
            red = random.choice(team_numbers)
            blue = random.choice(team_numbers)
            while blue == red:
                blue = random.choice(team_numbers)

            arena = arenas[index % len(arenas)]
            matches.append(
                _build_match(
                    match_number,
                    division,
                    absolute_slot_index,
                    arena,
                    red,
                    blue,
                    arenas,
                )
            )
            match_number += 1

            if (index + 1) % len(arenas) == 0:
                absolute_slot_index += len(arenas)

        if total_matches % len(arenas) != 0:
            absolute_slot_index += len(arenas)

    return matches


def generate_balanced_schedule(
    teams: List[Dict[str, Any]],
    arenas: List[str] = None,
    matches_per_team: int = 5,
    max_attempts: int = 12000,
) -> List[Dict[str, Any]]:
    """
    Week 3: equal matches + rough red/blue balance.
    Does not enforce no-repeat or no-back-to-back yet.
    """
    if arenas is None:
        arenas = ["Arena 1", "Arena 2"]

    teams_by_division = _group_teams_by_division(teams)
    matches: List[Dict[str, Any]] = []
    match_number = 1
    absolute_slot_index = 0

    for division, team_numbers in teams_by_division.items():
        if len(team_numbers) < 2:
            continue

        target = _target_matches_per_team(len(team_numbers), matches_per_team)
        total_matches = (len(team_numbers) * target) // 2

        match_count = {team_number: 0 for team_number in team_numbers}
        red_count = {team_number: 0 for team_number in team_numbers}
        blue_count = {team_number: 0 for team_number in team_numbers}

        made = 0
        attempts = 0
        while made < total_matches and attempts < max_attempts:
            attempts += 1
            need_more = [team for team in team_numbers if match_count[team] < target]
            if len(need_more) < 2:
                break

            need_more.sort(key=lambda team: (match_count[team], random.random()))
            first = need_more[0]
            second_pool = [team for team in need_more[1:] if team != first]
            if not second_pool:
                break
            second = random.choice(second_pool)

            first_red_cost = abs((red_count[first] + 1) - blue_count[first])
            second_blue_cost = abs(red_count[second] - (blue_count[second] + 1))
            option_a_cost = first_red_cost + second_blue_cost

            second_red_cost = abs((red_count[second] + 1) - blue_count[second])
            first_blue_cost = abs(red_count[first] - (blue_count[first] + 1))
            option_b_cost = second_red_cost + first_blue_cost

            if option_a_cost <= option_b_cost:
                red_team, blue_team = first, second
            else:
                red_team, blue_team = second, first

            arena = arenas[made % len(arenas)]
            matches.append(
                _build_match(
                    match_number,
                    division,
                    absolute_slot_index,
                    arena,
                    red_team,
                    blue_team,
                    arenas,
                )
            )

            match_count[red_team] += 1
            match_count[blue_team] += 1
            red_count[red_team] += 1
            blue_count[blue_team] += 1

            made += 1
            match_number += 1

            if made % len(arenas) == 0:
                absolute_slot_index += len(arenas)

        if made % len(arenas) != 0:
            absolute_slot_index += len(arenas)

    return matches


def _choose_advanced_pair(
    available_teams: List[int],
    target: int,
    match_count: Dict[int, int],
    red_count: Dict[int, int],
    blue_count: Dict[int, int],
    pair_count: Dict[Tuple[int, int], int],
    max_existing_pair_count: Optional[int] = None,
) -> Optional[Tuple[int, int]]:
    best_choice: Optional[Tuple[int, int]] = None
    best_signature: Optional[Tuple[int, int, int, int, float]] = None

    for i, team_a in enumerate(available_teams):
        if match_count[team_a] >= target:
            continue

        for team_b in available_teams[i + 1:]:
            if match_count[team_b] >= target:
                continue

            pairing = tuple(sorted((team_a, team_b)))
            repeats = pair_count.get(pairing, 0)
            if max_existing_pair_count is not None and repeats > max_existing_pair_count:
                continue

            remaining_need = (target - match_count[team_a]) + (target - match_count[team_b])

            option_a_color_cost = abs((red_count[team_a] + 1) - blue_count[team_a]) + abs(
                red_count[team_b] - (blue_count[team_b] + 1)
            )
            option_b_color_cost = abs((red_count[team_b] + 1) - blue_count[team_b]) + abs(
                red_count[team_a] - (blue_count[team_a] + 1)
            )
            color_cost = min(option_a_color_cost, option_b_color_cost)

            signature = (repeats, -remaining_need, color_cost, abs(team_a - team_b), random.random())

            if best_signature is None or signature < best_signature:
                if option_a_color_cost <= option_b_color_cost:
                    red_team, blue_team = team_a, team_b
                else:
                    red_team, blue_team = team_b, team_a
                best_choice = (red_team, blue_team)
                best_signature = signature

    return best_choice


def _has_unused_pair_with_demand(
    team_numbers: List[int],
    target: int,
    match_count: Dict[int, int],
    pair_count: Dict[Tuple[int, int], int],
) -> bool:
    candidates = [team for team in team_numbers if match_count[team] < target]
    for index, team_a in enumerate(candidates):
        for team_b in candidates[index + 1:]:
            pairing = tuple(sorted((team_a, team_b)))
            if pair_count.get(pairing, 0) == 0:
                return True
    return False


def generate_advanced_schedule(
    teams: List[Dict[str, Any]],
    arenas: List[str] = None,
    matches_per_team: int = 5,
    max_slot_multiplier: int = 8,
    max_attempts: int = 250,
) -> List[Dict[str, Any]]:
    """
    Weeks 4-5:
    - Equal match counts (when mathematically possible)
    - No back-to-back matches
    - No repeat pairings until necessary
    - Rough red/blue balance
    """
    if arenas is None:
        arenas = ["Arena 1", "Arena 2"]

    best_matches: List[Dict[str, Any]] = []
    best_score = 10**9

    for _ in range(max_attempts):
        teams_by_division = _group_teams_by_division(teams)
        matches: List[Dict[str, Any]] = []
        match_number = 1
        absolute_slot_index = 0

        for division, team_numbers in teams_by_division.items():
            if len(team_numbers) < 2:
                continue

            target = _target_matches_per_team(len(team_numbers), matches_per_team)
            total_matches = (len(team_numbers) * target) // 2
            if total_matches == 0:
                continue

            match_count = {team_number: 0 for team_number in team_numbers}
            red_count = {team_number: 0 for team_number in team_numbers}
            blue_count = {team_number: 0 for team_number in team_numbers}
            last_slot_played = {team_number: -1000 for team_number in team_numbers}
            pair_count: Dict[Tuple[int, int], int] = {}

            made = 0
            slot_index = 0
            max_slots = max(total_matches * max_slot_multiplier, total_matches + 20)

            while made < total_matches and slot_index < max_slots:
                used_this_slot = set()
                matches_in_slot = 0

                while matches_in_slot < len(arenas) and made < total_matches:
                    eligible = [
                        team
                        for team in team_numbers
                        if match_count[team] < target
                        and team not in used_this_slot
                        and last_slot_played[team] != (slot_index - 1)
                    ]

                    if len(eligible) < 2:
                        break

                    fresh_pair = _choose_advanced_pair(
                        eligible,
                        target,
                        match_count,
                        red_count,
                        blue_count,
                        pair_count,
                        max_existing_pair_count=0,
                    )

                    if fresh_pair is not None:
                        red_team, blue_team = fresh_pair
                    elif _has_unused_pair_with_demand(team_numbers, target, match_count, pair_count):
                        break
                    else:
                        fallback_pair = _choose_advanced_pair(
                            eligible,
                            target,
                            match_count,
                            red_count,
                            blue_count,
                            pair_count,
                            max_existing_pair_count=None,
                        )
                        if fallback_pair is None:
                            break
                        red_team, blue_team = fallback_pair

                    if red_team is None or blue_team is None:
                        break

                    arena = arenas[matches_in_slot]
                    absolute_for_slot = absolute_slot_index + (slot_index * len(arenas))
                    matches.append(
                        _build_match(
                            match_number,
                            division,
                            absolute_for_slot,
                            arena,
                            red_team,
                            blue_team,
                            arenas,
                        )
                    )

                    match_count[red_team] += 1
                    match_count[blue_team] += 1
                    red_count[red_team] += 1
                    blue_count[blue_team] += 1

                    pairing = tuple(sorted((red_team, blue_team)))
                    pair_count[pairing] = pair_count.get(pairing, 0) + 1

                    used_this_slot.add(red_team)
                    used_this_slot.add(blue_team)
                    last_slot_played[red_team] = slot_index
                    last_slot_played[blue_team] = slot_index

                    match_number += 1
                    made += 1
                    matches_in_slot += 1

                slot_index += 1

            absolute_slot_index += slot_index * len(arenas)

        violations = validate_schedule(matches)
        score = sum(len(issues) for issues in violations.values())

        if score < best_score:
            best_score = score
            best_matches = matches

        if score == 0 and matches:
            return matches

    return best_matches


def validate_schedule(matches: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Validate schedule through Week 5 constraints.

    Checks:
    - invalid_matches (same team on both sides)
    - equal_match_counts
    - balanced_colors (diff <= 2)
    - no_back_to_back
    - no_repeat_pairings (until mathematically necessary)
    """
    violations: Dict[str, List[str]] = {}

    by_division: Dict[str, List[Dict[str, Any]]] = {}
    for match in matches:
        division = match.get("division", "High School")
        by_division.setdefault(division, []).append(match)

    for division, division_matches in by_division.items():
        ordered = sorted(division_matches, key=lambda entry: entry.get("match_number", 0))

        team_stats: Dict[int, Dict[str, int]] = {}
        team_last_slot: Dict[int, int] = {}
        pairings: Dict[Tuple[int, int], int] = {}

        slot_values = sorted({match.get("scheduled_time") for match in ordered if match.get("scheduled_time")})
        slot_lookup = {slot_value: index for index, slot_value in enumerate(slot_values)}

        for index, match in enumerate(ordered):
            red_team = match.get("red_team_number")
            blue_team = match.get("blue_team_number")
            match_number = match.get("match_number", "?")

            if red_team is None or blue_team is None:
                continue

            if red_team == blue_team:
                violations.setdefault("invalid_matches", []).append(
                    f"Division {division}, match {match_number}: team {red_team} appears on both sides"
                )
                continue

            for team_number in (red_team, blue_team):
                if team_number not in team_stats:
                    team_stats[team_number] = {"total": 0, "red": 0, "blue": 0}

                slot_value = match.get("scheduled_time")
                slot_index = slot_lookup.get(slot_value)

                previous_slot = team_last_slot.get(team_number)
                if previous_slot is not None and slot_index is not None and previous_slot == slot_index - 1:
                    violations.setdefault("no_back_to_back", []).append(
                        f"Division {division}: team {team_number} appears in consecutive time slots"
                    )
                if slot_index is not None:
                    team_last_slot[team_number] = slot_index

            team_stats[red_team]["total"] += 1
            team_stats[red_team]["red"] += 1
            team_stats[blue_team]["total"] += 1
            team_stats[blue_team]["blue"] += 1

            pair = tuple(sorted((red_team, blue_team)))
            pairings[pair] = pairings.get(pair, 0) + 1

        if team_stats:
            totals = [entry["total"] for entry in team_stats.values()]
            if len(set(totals)) > 1:
                violations.setdefault("equal_match_counts", []).append(
                    f"Division {division}: teams do not all have equal match counts"
                )

            for team_number, stats in sorted(team_stats.items()):
                color_diff = abs(stats["red"] - stats["blue"])
                if color_diff > 2:
                    violations.setdefault("balanced_colors", []).append(
                        f"Division {division}: team {team_number} has red/blue diff {color_diff}"
                    )

            team_count = len(team_stats)
            max_unique_pairs = (team_count * (team_count - 1)) // 2
            total_matches = len(ordered)
            minimum_extra_repeats = max(0, total_matches - max_unique_pairs)
            actual_extra_repeats = sum(max(0, count - 1) for count in pairings.values())

            if actual_extra_repeats > minimum_extra_repeats:
                violations.setdefault("no_repeat_pairings", []).append(
                    (
                        f"Division {division}: {actual_extra_repeats} repeated pairings beyond "
                        f"minimum necessary {minimum_extra_repeats}"
                    )
                )

    return violations


def count_violations(violations: Dict[str, List[str]]) -> Dict[str, int]:
    return {rule: len(issues) for rule, issues in violations.items()}


def format_violations(violations: Dict[str, List[str]]) -> str:
    if not violations:
        return "✓ Schedule is valid for Week 5 constraints"

    lines: List[str] = []
    for rule, issues in violations.items():
        lines.append(f"\n{rule}:")
        for issue in issues[:5]:
            lines.append(f"  - {issue}")
        if len(issues) > 5:
            lines.append(f"  ... and {len(issues) - 5} more")
    return "\n".join(lines)
