# owner: shared / lead
# The store blueprint: catalog, checkout, and the Stripe webhook.

from flask import Blueprint

store_bp = Blueprint("store", __name__, url_prefix="/store", template_folder="templates")

from app.store import routes  # noqa: E402,F401  (registers routes on the blueprint)
