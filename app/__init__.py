# owner: shared / lead
# The app factory. Creates the Flask app, connects the database, and
# registers every blueprint so its routes become reachable.

import logging

from flask import Flask
from flask_wtf.csrf import CSRFProtect

from app.db import db

logger = logging.getLogger(__name__)

# Module-level so the Stripe webhook can exempt itself with @csrf.exempt once
# it exists. Stripe signs its requests and cannot carry a CSRF token, so that
# one route has to opt out - and it is safe to, because the signature check
# proves far more than a CSRF token would.
csrf = CSRFProtect()


def create_app(config_object="config.Config", **overrides):
    """Build the app.

    *overrides* are applied on top of *config_object* and win, so a test can
    ask for an in-memory database without touching the environment or the real
    Config class. Everything is applied before db.init_app, because the engine
    is built from the config as it stands at that moment.
    """
    app = Flask(__name__)
    app.config.from_object(config_object)
    app.config.update(overrides)

    # SQLALCHEMY_ENGINE_OPTIONS in config.Config is chosen for whichever URI
    # that class computed. An override that swaps Postgres for SQLite would
    # otherwise inherit Postgres-only options like connect_timeout, and SQLite's
    # pool raises on those rather than ignoring them.
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {}

    db.init_app(app)

    # Protects every POST in the app at once, including the ones in blueprints
    # that are still switched off. Each form needs {{ csrf_token() }} in a
    # hidden field or its POST starts returning 400.
    csrf.init_app(app)

    @app.after_request
    def _security_headers(response):
        # nosniff stops a browser from second-guessing a Content-Type, which is
        # what turns an uploaded or reflected file into executable script.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        # Referrer-Policy keeps the full URL from leaking to third parties.
        # It matters more than usual here: once confirmation pages are keyed by
        # a secret token, the URL *is* the credential, and a default policy
        # would hand it to every external host the page links out to.
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        return response

    with app.app_context():
        from app import models  # noqa: F401  (import so SQLAlchemy sees the models)
        try:
            db.create_all()
        except Exception:
            # create_all needs the database reachable, and on a serverless host
            # this runs during import on every cold start. An unreachable
            # database used to take the whole app down with it — including the
            # public landing page, which reads no database at all. Log it and
            # carry on: pages that need tables will fail on their own and say
            # so, and pages that don't keep working.
            logger.exception("create_all failed - database-backed pages will error")

    from app.routes import main_bp
    from app.registration import registration_bp
    from app.store import store_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(registration_bp)
    # Always registered, never behind REGISTRATION_ONLY: the Stripe webhook
    # lives here, and Stripe must be able to reach it whatever else is
    # switched off. An unreachable webhook means orders that are paid for and
    # never fulfilled.
    app.register_blueprint(store_bp)

    # The unfinished modules are not imported at all when REGISTRATION_ONLY is
    # on: an unregistered blueprint has no routes, so its paths 404 instead of
    # being merely unlinked from the nav.
    if not app.config["REGISTRATION_ONLY"]:
        from app.checkin import checkin_bp
        from app.scheduler import scheduler_bp
        from app.referee import referee_bp
        from app.rankings import rankings_bp
        from app.bracket import bracket_bp
        from app.admin import admin_bp

        app.register_blueprint(checkin_bp)
        app.register_blueprint(scheduler_bp)
        app.register_blueprint(referee_bp)
        app.register_blueprint(rankings_bp)
        app.register_blueprint(bracket_bp)
        app.register_blueprint(admin_bp)

    return app
