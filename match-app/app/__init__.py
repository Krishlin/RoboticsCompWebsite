from flask import Flask

def create_app():
    app = Flask(__name__)

    # Register the referee blueprint
    from app.referee import referee_bp
    app.register_blueprint(referee_bp)

    return app

