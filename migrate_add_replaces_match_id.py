# One-off migration: add match.replaces_match_id to a database that already
# exists. Run once, from the project root, after pulling this change:
#
#     python migrate_add_replaces_match_id.py
#
# Why this exists: app/__init__.py calls db.create_all(), which only creates
# tables that are missing — it never adds a column to a table that is already
# there. So a database created before this change has no replaces_match_id,
# and every page that queries Match dies with
# "no such column: match.replaces_match_id". Reseeding also fixes it, but
# throws away whatever is in your local database; this doesn't.
#
# It only ADDs a nullable column. It never drops or rewrites anything, and
# running it twice is a no-op. Works on SQLite and Postgres.
#
# The project has no migration tooling (no Flask-Migrate/Alembic in
# requirements.txt), which is why this is a hand-written script. If the
# schema changes again — the outcome/zone enum work will change it — that
# decision is worth making properly rather than adding a second one of these.

import sys

from sqlalchemy import inspect, text

from app import create_app
from app.db import db

TABLE = "match"
COLUMN = "replaces_match_id"


def main():
    app = create_app()
    with app.app_context():
        engine = db.engine
        inspector = inspect(engine)

        if TABLE not in inspector.get_table_names():
            print(f"No '{TABLE}' table in {engine.url}. Nothing to migrate.")
            return 0

        columns = [c["name"] for c in inspector.get_columns(TABLE)]
        if COLUMN in columns:
            print(f"'{TABLE}.{COLUMN}' already exists in {engine.url}. Nothing to do.")
            return 0

        print(f"Adding '{TABLE}.{COLUMN}' to {engine.url} ...")
        with engine.begin() as connection:
            connection.execute(
                text(f'ALTER TABLE "{TABLE}" ADD COLUMN {COLUMN} INTEGER REFERENCES "{TABLE}"(id)')
            )

        columns = [c["name"] for c in inspect(engine).get_columns(TABLE)]
        if COLUMN not in columns:
            print(f"ALTER TABLE ran but '{COLUMN}' is still not present. Nothing was lost, "
                  f"but the migration did not take - check the database by hand.")
            return 1

        print("Done. Existing rows have replaces_match_id = NULL, which means "
              "'not a replay' - the same thing they meant before.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
