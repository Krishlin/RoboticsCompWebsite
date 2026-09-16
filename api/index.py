"""Vercel entrypoint.

Vercel runs each request in a serverless function whose bundle directory is
read-only, so the app's default SQLite path (next to config.py) cannot be
created there. /tmp is the one writable location, and it is per-instance and
wiped between cold starts.

That is fine for a preview link — the landing page reads no database at all —
but it means anything written through the registration form on a Vercel
deployment disappears. A real deployment sets DATABASE_URL to a Postgres URL,
and setdefault below steps aside when it does.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# gettempdir() rather than a literal /tmp so this entrypoint can be imported
# and tested on a developer's machine, where /tmp is not a real path.
_scratch_db = Path(tempfile.gettempdir()) / "src.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_scratch_db.as_posix()}")

from app import create_app  # noqa: E402  (must follow the sys.path setup)

app = create_app()
