"""Authentication helpers for Bot Manager."""
import hmac
from functools import wraps

from flask import Response, request


def check_auth(username: str, password: str, app_config) -> bool:
    """Check if username/password combination is valid."""
    expected_user = app_config.BASIC_AUTH_USERNAME
    expected_pass = app_config.BASIC_AUTH_PASSWORD

    if not expected_pass:
        return True

    return hmac.compare_digest(username, expected_user) and hmac.compare_digest(password, expected_pass)


def requires_auth(f):
    """Decorator that requires HTTP Basic Auth."""
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask import current_app
        app_config = current_app.config.get("APP_CONFIG")

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
