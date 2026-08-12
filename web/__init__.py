"""Flask application factory for the 15-Minute Neighborhood Score web UI."""

from flask import Flask

from web.icons import CATEGORY_ACCENTS, CATEGORY_ICONS, ICON_HOME, ICON_PIN


def create_app():
    app = Flask(__name__)
    # Local single-user dev app only -- never deployed, so a static key is fine.
    app.secret_key = "dev-only-secret-key-not-for-production"

    app.jinja_env.globals["category_icons"] = CATEGORY_ICONS
    app.jinja_env.globals["category_accents"] = CATEGORY_ACCENTS
    app.jinja_env.globals["icon_home"] = ICON_HOME
    app.jinja_env.globals["icon_pin"] = ICON_PIN

    from web.routes import bp
    app.register_blueprint(bp)

    return app
