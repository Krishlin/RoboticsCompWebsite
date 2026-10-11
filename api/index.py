"""Vercel entrypoint.

This used to point DATABASE_URL at a SQLite file under /tmp when nothing else
had set it. /tmp is the only writable path in a serverless function, and it is
per-instance and wiped between cold starts — so that file accepted writes,
reported success, and lost them. That was survivable when the only casualty
was a registration somebody could re-enter. It is not survivable now that the
same request can take someone's money.

There is no fallback any more. config.py refuses to build a Config at all when
a deployment has no DATABASE_URL, so a misconfigured deploy fails loudly on its
first preview instead of quietly dropping rows for a fortnight.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402  (must follow the sys.path setup)

app = create_app()
