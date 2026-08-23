# owner: Krish S
# Blueprint definition for the elimination bracket: seeding, advancement,
# and rendering.

from flask import Blueprint

bracket_bp = Blueprint(
    "bracket",
    __name__,
    url_prefix="/bracket",
    template_folder="templates",
    static_folder="static",
)

from app.bracket import routes  # noqa: E402,F401
