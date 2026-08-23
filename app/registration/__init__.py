# owner: Emily
# Blueprint definition for the registration module: public signup form,
# team numbering, and the team list / CSV export.

from flask import Blueprint

registration_bp = Blueprint(
    "registration",
    __name__,
    url_prefix="/register",
    template_folder="templates",
)

from app.registration import routes  # noqa: E402,F401
