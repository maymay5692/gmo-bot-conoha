"""Flask application entry point for Bot Manager."""
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

    flask_app.register_blueprint(dashboard_bp)
    flask_app.register_blueprint(bot_control_bp, url_prefix="/api")
    flask_app.register_blueprint(config_bp)
    flask_app.register_blueprint(logs_bp)
    flask_app.register_blueprint(pnl_bp)

    # Initialize P&L service
    from services import pnl_service
    pnl_service.init(app_config.PNL_DATA_DIR)

    return flask_app


# Application instance for gunicorn
app = create_app()


if __name__ == "__main__":
    config = get_config()
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
