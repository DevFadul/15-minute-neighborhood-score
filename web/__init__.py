"""Flask application factory for the 15-Minute Neighborhood Score web UI."""

from flask import Flask


def create_app():
    app = Flask(__name__)
    # Local single-user dev app only -- never deployed, so a static key is fine.
    app.secret_key = "dev-only-secret-key-not-for-production"

    from web.routes import bp
    app.register_blueprint(bp)

    return app
