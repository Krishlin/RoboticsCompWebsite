# owner: Yueyue
# Blueprint definition for the head-ref admin panel: editing results (with
# an audit trail), pausing/resuming the schedule, inserting replays, and
# the global CSV export.

from flask import Blueprint

admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
    template_folder="templates",
)

from app.admin import routes  # noqa: E402,F401
