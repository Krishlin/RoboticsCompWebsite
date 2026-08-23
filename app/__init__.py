# owner: shared / lead
# The app factory. Creates the Flask app, connects the database, and
# registers every blueprint so its routes become reachable.

from flask import Flask

from app.db import db


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    db.init_app(app)

    with app.app_context():
        from app import models  # noqa: F401  (import so SQLAlchemy sees the models)
        db.create_all()

    from app.routes import main_bp
    from app.registration import registration_bp
    from app.checkin import checkin_bp
    from app.scheduler import scheduler_bp
    from app.referee import referee_bp
    from app.rankings import rankings_bp
    from app.bracket import bracket_bp
    from app.admin import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(registration_bp)
    app.register_blueprint(checkin_bp)
    app.register_blueprint(scheduler_bp)
    app.register_blueprint(referee_bp)
    app.register_blueprint(rankings_bp)
    app.register_blueprint(bracket_bp)
    app.register_blueprint(admin_bp)

    return app
