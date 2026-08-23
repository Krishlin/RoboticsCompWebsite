# owner: Jon
# Blueprint definition for standings/rankings, the big-screen display, and
# the pit lookup page.

from flask import Blueprint

rankings_bp = Blueprint(
    "rankings",
    __name__,
    url_prefix="/rankings",
    template_folder="templates",
)

from app.rankings import routes  # noqa: E402,F401
