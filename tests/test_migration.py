"""migrate_add_series_columns.py upgrades a database made before the series
model, keeps its rows, and is safe to run twice."""

import sqlite3

from app.db import db
from app.models import Match, MatchResult
from migrate_add_series_columns import main as migrate
from tests.conftest import _build

# The three tables as they were before this change, trimmed to what matters.
OLD_SCHEMA = """
CREATE TABLE team (
    id INTEGER PRIMARY KEY, team_number INTEGER NOT NULL UNIQUE, name VARCHAR(120) NOT NULL,
    affiliation VARCHAR(120) NOT NULL, division VARCHAR(50) NOT NULL, students TEXT NOT NULL,
    adult_name VARCHAR(120) NOT NULL, adult_email VARCHAR(200) NOT NULL UNIQUE,
    adult_phone VARCHAR(30), kit_ordered BOOLEAN NOT NULL, checked_in BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL
);
CREATE TABLE "match" (
    id INTEGER PRIMARY KEY, match_number INTEGER NOT NULL, phase VARCHAR(20) NOT NULL,
    division VARCHAR(50) NOT NULL, arena VARCHAR(50) NOT NULL, scheduled_time DATETIME,
    red_team_id INTEGER REFERENCES team(id), blue_team_id INTEGER REFERENCES team(id),
    status VARCHAR(20) NOT NULL, is_replay BOOLEAN NOT NULL,
    replaces_match_id INTEGER REFERENCES "match"(id),
    bracket_round INTEGER, bracket_slot INTEGER
);
CREATE TABLE match_result (
    id INTEGER PRIMARY KEY, match_id INTEGER NOT NULL REFERENCES "match"(id),
    outcome VARCHAR(20) NOT NULL, win_time_seconds FLOAT,
    red_final_zone VARCHAR(50) NOT NULL, blue_final_zone VARCHAR(50) NOT NULL,
    submitted_at DATETIME NOT NULL, submitted_by VARCHAR(120) NOT NULL
);
INSERT INTO team VALUES
    (1, 101, 'A', 'x', 'High School', 's', 'c', 'a@x.org', NULL, 0, 0, '2026-10-01 00:00:00'),
    (2, 102, 'B', 'x', 'High School', 's', 'c', 'b@x.org', NULL, 0, 0, '2026-10-01 00:00:00');
INSERT INTO "match" VALUES (1, 1, 'qualification', 'High School', 'Arena 1', NULL, 1, 2,
    'complete', 0, NULL, NULL, NULL);
INSERT INTO match_result VALUES (1, 1, 'red', 12.5, 'Center', 'Off Arena',
    '2026-10-01 10:00:00', 'ref');
"""


def test_migration_upgrades_an_old_database_and_is_idempotent(tmp_path):
    path = tmp_path / "test.db"  # the file _build points the app at
    with sqlite3.connect(path) as conn:
        conn.executescript(OLD_SCHEMA)

    app = _build(tmp_path, REGISTRATION_ONLY=False)
    assert migrate(app) == 0
    assert migrate(app) == 0  # second run: nothing to do, nothing broken

    with app.app_context():
        result = db.session.get(MatchResult, 1)
        assert (result.game_number, result.voided, result.outcome) == (1, False, "red")
        match = db.session.get(Match, 1)
        # One game won is not a best-of-three series won any more.
        assert match.status == "in_progress"
        assert match.game_started_at is None and match.bracket_side is None

    with sqlite3.connect(path) as conn:
        indexes = [row[1] for row in conn.execute("PRAGMA index_list('match_result')")]
        assert "uq_match_result_game" in indexes
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "bracket_config" in tables
