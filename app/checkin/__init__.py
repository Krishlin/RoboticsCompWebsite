# owner: Shivani
# Blueprint definition for check-in and robot inspection.

from flask import Blueprint

checkin_bp = Blueprint(
    "checkin",
    __name__,
    url_prefix="/checkin",
    template_folder="templates",
)

from app.checkin import routes  # noqa: E402,F401
