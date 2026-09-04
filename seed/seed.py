# owner: Shivani
#
# Local development seed data only. This creates a small set of real
# database-backed Team / Match / MatchResult rows so the Week 3 admin flow
# can be tested without touching production data or altering the app models.
#
# Run with: python seed/seed.py

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from app.db import db
from app.models import Match, MatchResult, Team


def _team_specs():
    return [
        {
            "team_number": 101,
            "name": "Team 101",
            "affiliation": "Lincoln Elementary",
            "division": "Elementary",
            "students": "Ava\nLiam\nNoah",
            "adult_name": "Coach Diaz",
            "adult_email": "coach101@example.com",
            "adult_phone": "555-0101",
            "kit_ordered": True,
            "checked_in": True,
        },
        {
            "team_number": 102,
            "name": "Team 102",
            "affiliation": "Oakwood Middle School",
            "division": "Middle School",
            "students": "Emma\nLucas\nMia",
            "adult_name": "Coach Patel",
            "adult_email": "coach102@example.com",
            "adult_phone": "555-0102",
            "kit_ordered": True,
            "checked_in": True,
        },
        {
            "team_number": 103,
            "name": "Team 103",
            "affiliation": "Riverside STEM Academy",
            "division": "Elementary",
            "students": "Leo\nRuby\nZoe",
            "adult_name": "Coach Nguyen",
            "adult_email": "coach103@example.com",
            "adult_phone": "555-0103",
            "kit_ordered": False,
            "checked_in": True,
        },
        {
            "team_number": 201,
            "name": "Team 201",
            "affiliation": "Central Middle School",
            "division": "Middle School",
            "students": "Theo\nIsla\nKai",
            "adult_name": "Coach Smith",
            "adult_email": "coach201@example.com",
            "adult_phone": "555-0201",
            "kit_ordered": True,
            "checked_in": True,
        },
    ]


def _match_specs():
    return [
        {
            "match_number": 1,
            "phase": "qualification",
            "division": "Elementary",
            "arena": "Arena 1",
            "scheduled_time": datetime(2026, 9, 12, 9, 0),
            "red_team_number": 101,
            "blue_team_number": 103,
            "status": "complete",
            "is_replay": False,
            "bracket_round": None,
            "bracket_slot": None,
        },
        {
            "match_number": 2,
            "phase": "qualification",
            "division": "Middle School",
            "arena": "Arena 2",
            "scheduled_time": datetime(2026, 9, 12, 10, 30),
            "red_team_number": 102,
            "blue_team_number": 201,
            "status": "complete",
            "is_replay": False,
            "bracket_round": None,
            "bracket_slot": None,
        },
        {
            "match_number": 3,
            "phase": "qualification",
            "division": "Elementary",
            "arena": "Arena 1",
            "scheduled_time": datetime(2026, 9, 12, 11, 0),
            "red_team_number": 103,
            "blue_team_number": 101,
            "status": "scheduled",
            "is_replay": False,
            "bracket_round": None,
            "bracket_slot": None,
        },
    ]


def _result_specs():
    return [
        {
            "match_number": 1,
            "division": "Elementary",
            "arena": "Arena 1",
            "outcome": "red",
            "win_time_seconds": 18.5,
            "red_final_zone": "Center",
            "blue_final_zone": "Blue Zone",
            "submitted_by": "Referee A",
        },
        {
            "match_number": 2,
            "division": "Middle School",
            "arena": "Arena 2",
            "outcome": "double_dq",
            "win_time_seconds": 22.0,
            "red_final_zone": "Red Zone",
            "blue_final_zone": "Blue Zone",
            "submitted_by": "Referee B",
        },
    ]


def seed_database():
    """Create a small, repeatable set of local test records."""
    app = create_app()

    with app.app_context():
        db.create_all()

        # Ensure Teams exist without duplicating them across repeated runs.
        team_by_number = {}
        for spec in _team_specs():
            team = Team.query.filter_by(team_number=spec["team_number"]).first()
            if team is None:
                team = Team(
                    team_number=spec["team_number"],
                    name=spec["name"],
                    affiliation=spec["affiliation"],
                    division=spec["division"],
                    students=spec["students"],
                    adult_name=spec["adult_name"],
                    adult_email=spec["adult_email"],
                    adult_phone=spec["adult_phone"],
                    kit_ordered=spec["kit_ordered"],
                    checked_in=spec["checked_in"],
                )
                db.session.add(team)
            team_by_number[spec["team_number"]] = team
        db.session.commit()

        # Create a few Match rows, deduping by match_number + division + arena.
        match_by_key = {}
        for spec in _match_specs():
            existing = Match.query.filter_by(
                match_number=spec["match_number"],
                division=spec["division"],
                arena=spec["arena"],
            ).first()
            if existing is None:
                match = Match(
                    match_number=spec["match_number"],
                    phase=spec["phase"],
                    division=spec["division"],
                    arena=spec["arena"],
                    scheduled_time=spec["scheduled_time"],
                    red_team_id=team_by_number[spec["red_team_number"]].id,
                    blue_team_id=team_by_number[spec["blue_team_number"]].id,
                    status=spec["status"],
                    is_replay=spec["is_replay"],
                    bracket_round=spec["bracket_round"],
                    bracket_slot=spec["bracket_slot"],
                )
                db.session.add(match)
                db.session.flush()
                existing = match
            match_by_key[(spec["match_number"], spec["division"], spec["arena"])] = existing
        db.session.commit()

        # Seed MatchResults for selected matches only when they are missing.
        for spec in _result_specs():
            match = Match.query.filter_by(
                match_number=spec["match_number"],
                division=spec["division"],
                arena=spec["arena"],
            ).first()
            if match is None:
                continue
            if MatchResult.query.filter_by(match_id=match.id).first() is None:
                result = MatchResult(
                    match_id=match.id,
                    outcome=spec["outcome"],
                    win_time_seconds=spec["win_time_seconds"],
                    red_final_zone=spec["red_final_zone"],
                    blue_final_zone=spec["blue_final_zone"],
                    submitted_at=datetime.utcnow(),
                    submitted_by=spec["submitted_by"],
                )
                db.session.add(result)
        db.session.commit()

        print(
            "Seeded local test data: "
            f"{Team.query.count()} teams, "
            f"{Match.query.count()} matches, "
            f"{MatchResult.query.count()} match results."
        )


if __name__ == "__main__":
    seed_database()
