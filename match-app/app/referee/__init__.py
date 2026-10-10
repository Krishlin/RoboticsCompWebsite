# owner: Serena
# Blueprint definition for the referee-facing match control page.

from flask import Blueprint

referee_bp = Blueprint(
    "referee",
    __name__,
    url_prefix="/referee",
    template_folder="templates",
)

from . import routes  # noqa: E402,F401
