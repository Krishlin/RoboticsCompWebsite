# One-off migration: add the columns the best-of-three series model needs
# to a database that already exists. Run once, from the project root, after
# pulling this change:
#
#     python migrate_add_series_columns.py
#
# Same reason as migrate_add_replaces_match_id.py: db.create_all() creates
# missing tables (so bracket_config appears on its own) but never adds a
# column to a table that is already there.
#
# Adds, all nullable or defaulted, so existing rows keep their meaning:
#   match.game_started_at        the running game's start time (referee timer)
#   match.game_paused_at         when the referee paused that timer, if it is paused
#   match.bracket_side           W / L / GF for bracket series
#   match_result.game_number     which game of the series; existing rows -> 1
#   match_result.voided          replay ordered by the head ref; existing -> false
# plus a unique index on (match_id, game_number), so one game can never be
# recorded twice.
#
# It never drops or rewrites anything, and running it twice is a no-op.
# Works on SQLite and Postgres. Afterwards it re-derives every match's status
# from its games, because a match that was "complete" after one game under
# the old one-match rules is a series still in progress under the new ones.

import sys

from sqlalchemy import inspect, text

from app import create_app
from app.db import db

COLUMNS = [
    # (table, column, SQLite type, Postgres type)
    ("match", "game_started_at", "DATETIME", "TIMESTAMP WITHOUT TIME ZONE"),
    ("match", "game_paused_at", "DATETIME", "TIMESTAMP WITHOUT TIME ZONE"),
    ("match", "bracket_side", "VARCHAR(2)", "VARCHAR(2)"),
    ("match_result", "game_number", "INTEGER NOT NULL DEFAULT 1", "INTEGER NOT NULL DEFAULT 1"),
    ("match_result", "voided", "BOOLEAN NOT NULL DEFAULT 0", "BOOLEAN NOT NULL DEFAULT FALSE"),
]

INDEX = (
    'CREATE UNIQUE INDEX IF NOT EXISTS uq_match_result_game '
    'ON "match_result" (match_id, game_number)'
)


def main(app=None):
    app = app or create_app()
    with app.app_context():
        engine = db.engine
        postgres = engine.dialect.name == "postgresql"
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        for table, column, sqlite_type, pg_type in COLUMNS:
            if table not in tables:
                print(f"No '{table}' table in {engine.url}. Skipping {column}.")
                continue
            existing = [c["name"] for c in inspector.get_columns(table)]
            if column in existing:
                print(f"'{table}.{column}' already exists. Nothing to do.")
                continue
            print(f"Adding '{table}.{column}' to {engine.url} ...")
            with engine.begin() as connection:
                connection.execute(
                    text(f'ALTER TABLE "{table}" ADD COLUMN {column} '
                         f'{pg_type if postgres else sqlite_type}')
                )

        if "match_result" in tables:
            print("Ensuring the one-row-per-game unique index ...")
            with engine.begin() as connection:
                connection.execute(text(INDEX))

        missing = [
            f"{table}.{column}"
            for table, column, _, _ in COLUMNS
            if table in tables and column not in [c["name"] for c in inspect(engine).get_columns(table)]
        ]
        if missing:
            print("ALTER TABLE ran but these are still not present: " + ", ".join(missing)
                  + ". Nothing was lost, but the migration did not take - check by hand.")
            return 1

        if "match" in tables:
            from app.match_state import refresh_series_status
            from app.models import Match

            changed = 0
            for match in Match.query.all():
                before = match.status
                refresh_series_status(match)
                changed += match.status != before
            db.session.commit()
            print(f"Re-derived match status from games: {changed} match(es) changed.")

        print("Done.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
