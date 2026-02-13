"""Flask application entry point for Bot Manager."""
import os

from flask import Flask
from flask_wtf.csrf import CSRFProtect

from config import get_config

# CSRF protection instance
csrf = CSRFProtect()


def create_app(app_config=None):
    """Create and configure the Flask application."""
    flask_app = Flask(__name__)

    # Load configuration
    if app_config is None:
        app_config = get_config()

    # Require ADMIN_PASS when binding to external interfaces
    if app_config.HOST != "127.0.0.1" and not app_config.BASIC_AUTH_PASSWORD:
        raise RuntimeError(
            "ADMIN_PASS environment variable must be set when HOST is not 127.0.0.1"
        )

    flask_app.config.from_object(app_config)
    flask_app.config["APP_CONFIG"] = app_config

    # Initialize CSRF protection
    csrf.init_app(flask_app)

    # Register blueprints
    from routes.dashboard import dashboard_bp
    from routes.bot_control import bot_control_bp
    from routes.config_routes import config_bp
    from routes.logs import logs_bp
    from routes.pnl import pnl_bp
    from routes.admin import admin_bp

    flask_app.register_blueprint(dashboard_bp)
    flask_app.register_blueprint(bot_control_bp, url_prefix="/api")
    flask_app.register_blueprint(config_bp)
    flask_app.register_blueprint(logs_bp)
    flask_app.register_blueprint(pnl_bp)
    flask_app.register_blueprint(admin_bp, url_prefix="/api")

    # Exempt admin API from CSRF (called via curl, not browser forms)
    csrf.exempt(admin_bp)

    # Initialize P&L service
    from services import pnl_service
    pnl_service.init(app_config.PNL_DATA_DIR)

    # Initialize Discord webhook notifications
    from services.discord_notify import init_discord
    init_discord(os.environ.get("DISCORD_WEBHOOK_URL"))

    return flask_app


def _get_app():
    """Lazy application factory for WSGI servers (gunicorn/waitress)."""
    return create_app()


# Application instance for gunicorn/waitress (evaluated at import time)
# In test environments, tests create their own app via create_app(TestConfig())
if os.environ.get("FLASK_ENV") != "testing":
    app = _get_app()


if __name__ == "__main__":
    config = get_config()
    if "app" not in globals():
        app = _get_app()
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
