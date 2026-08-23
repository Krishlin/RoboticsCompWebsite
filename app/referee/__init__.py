# owner: Serena
# Blueprint definition for the referee-facing match control page. Phone
# sized, one of these open per arena, in use all day.

from flask import Blueprint

referee_bp = Blueprint(
    "referee",
    __name__,
    url_prefix="/referee",
    template_folder="templates",
)

from app.referee import routes  # noqa: E402,F401
