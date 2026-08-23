# owner: Shaurya
# Blueprint definition for the qualification match scheduler.

from flask import Blueprint

scheduler_bp = Blueprint(
    "scheduler",
    __name__,
    url_prefix="/schedule",
    template_folder="templates",
)

from app.scheduler import routes  # noqa: E402,F401
