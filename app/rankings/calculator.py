# owner: Jon
# Calculates real rankings from MatchResult database records.
# Replaces the fake_rankings() function for production use.

from app.db import db
from app.models import Team, Match, MatchResult


def calculate_rankings(division):
    """
    Calculate real rankings for a division based on actual MatchResult database records.

    For each team in the division:
    - Count wins: matches where the team's outcome matches their position (red won and they're red, etc.)
    - Count losses: matches where the team did not win (includes double_dq)
    - Count ties: matches with outcome "tie"
    - Calculate average win time: mean of win_time_seconds from their won matches

    Results are sorted by:
    1. wins (descending — higher wins rank higher)
    2. losses (ascending — fewer losses rank higher, ties with same wins)
    3. ties (descending — more ties rank higher, ties with same wins/losses)
    4. avg_win_time (ascending — faster average time ranks higher, ties with all above)

    Args:
        division (str): Division name (e.g., "Elementary", "Middle School")

    Returns:
        list: Ranking rows, each with keys:
            rank, team_number, team_name, wins, losses, ties, avg_win_time
    """
    # Get all teams in this division
    teams = Team.query.filter_by(division=division).all()

    rankings = []

    for team in teams:
        # Find all completed matches for this team in this division
        matches = Match.query.filter(
            Match.division == division,
            Match.status == "complete",
            ((Match.red_team_id == team.id) | (Match.blue_team_id == team.id))
        ).all()

        wins = 0
        losses = 0
        ties = 0
        win_times = []

        for match in matches:
            # Get the result for this match
            result = MatchResult.query.filter_by(match_id=match.id).first()
            if result is None:
                continue

            # Determine if this team is red or blue
            is_red = match.red_team_id == team.id

            # Tally win/loss/tie based on outcome and team position
            if result.outcome == "red":
                if is_red:
                    wins += 1
                    if result.win_time_seconds is not None:
                        win_times.append(result.win_time_seconds)
                else:
                    losses += 1
            elif result.outcome == "blue":
                if not is_red:
                    wins += 1
                    if result.win_time_seconds is not None:
                        win_times.append(result.win_time_seconds)
                else:
                    losses += 1
            elif result.outcome == "tie":
                ties += 1
            elif result.outcome == "double_dq":
                # Both teams disqualified: count as loss for both
                losses += 1

        # Calculate average win time from this team's won matches
        avg_win_time = round(sum(win_times) / len(win_times), 2) if win_times else 0.0

        rankings.append({
            "team_number": team.team_number,
            "team_name": team.name,
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "avg_win_time": avg_win_time,
        })

    # Sort deterministically: wins DESC, losses ASC, ties DESC, avg_win_time ASC
    rankings.sort(
        key=lambda r: (-r["wins"], r["losses"], -r["ties"], r["avg_win_time"])
    )

    # Assign rank numbers after sorting
    for rank, row in enumerate(rankings, start=1):
        row["rank"] = rank

    return rankings
