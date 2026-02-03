"""Flask application entry point for Bot Manager."""
from functools import wraps

from flask import Flask, Response, request
from flask_wtf.csrf import CSRFProtect

from config import get_config

# CSRF protection instance
csrf = CSRFProtect()


def check_auth(username: str, password: str, app_config) -> bool:
    """Check if username/password combination is valid."""
    expected_user = app_config.BASIC_AUTH_USERNAME
    expected_pass = app_config.BASIC_AUTH_PASSWORD

    # If no password set, skip auth (development mode)
    if not expected_pass:
        return True

    return username == expected_user and password == expected_pass


def requires_auth(f):
    """Decorator that requires HTTP Basic Auth."""
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask import current_app
        app_config = current_app.config.get("APP_CONFIG")

        # Skip auth if no password configured
        if not app_config or not app_config.BASIC_AUTH_PASSWORD:
            return f(*args, **kwargs)

        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password, app_config):
            return Response(
                "Authentication required",
                401,
                {"WWW-Authenticate": 'Basic realm="Bot Manager"'}
            )
        return f(*args, **kwargs)
    return decorated


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

    flask_app.register_blueprint(dashboard_bp)
    flask_app.register_blueprint(bot_control_bp, url_prefix="/api")
    flask_app.register_blueprint(config_bp)
    flask_app.register_blueprint(logs_bp)

    return flask_app


# Application instance for gunicorn
app = create_app()


if __name__ == "__main__":
    config = get_config()
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
