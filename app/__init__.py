# owner: shared / lead
# The app factory. Creates the Flask app, connects the database, and
# registers every blueprint so its routes become reachable.

import logging

from flask import Flask

from app.db import db

logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    db.init_app(app)

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

    app.register_blueprint(main_bp)
    app.register_blueprint(registration_bp)

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
