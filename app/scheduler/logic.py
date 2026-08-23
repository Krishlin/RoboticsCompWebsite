# owner: Shaurya
# Pure functions for the scheduler: no Flask, no database. This is the
# algorithm-heavy module — build and test it as plain Python first.


def generate_schedule(teams, matches_per_team):
    """Build a full qualification schedule from a list of teams.

    teams: list of team dicts
    matches_per_team: int, how many matches each team should get

    Constraints to satisfy:
    - every team gets the same number of matches
    - no repeat pairing until every other pairing has happened once
    - no team plays back-to-back matches
    - red/blue assignments are balanced across each team's matches
    - each match gets an arena and an approximate time

    Should return a list of match dicts (see app/models.py Match for shape).
    """
    pass


def balance_red_blue(matches, team_id):
    """Return True if `team_id` has a roughly equal number of red and blue
    assignments across `matches`.

    Used to check the schedule generator's output, or to decide which side
    a new match should assign a team to.
    """
    pass


def teams_without_back_to_back_conflicts(matches, arena_order):
    """Given a list of matches in the order they'll be played on one arena,
    return the ones where the team also just played the previous match.

    Used to validate a generated schedule doesn't have a team going right
    back into the arena with no break.
    """
    pass
