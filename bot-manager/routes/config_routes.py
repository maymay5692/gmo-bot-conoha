"""Configuration routes."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response

from auth import requires_auth
from config import get_config
from services.config_service import read_config, write_config, validate_config, ConfigError

config_bp = Blueprint("config", __name__)


@config_bp.route("/config")
@requires_auth
def config_page() -> Response:
    """Configuration edit page."""
    app_config = get_config()

    try:
        bot_config = read_config(app_config.CONFIG_PATH)
    except ConfigError as e:
        bot_config = {}
        flash(f"Failed to read config: {e}", "error")

    return render_template("config.html", config=bot_config)


@config_bp.route("/config", methods=["POST"])
@requires_auth
def config_save() -> Response:
    """Save configuration."""
    app_config = get_config()

    # Parse form data into config dict
    new_config = {}

    # Get all form fields
    for key in request.form:
        # Skip CSRF token
        if key == "csrf_token":
            continue

        value = request.form[key]

        # Try to convert to appropriate type
        if value.lower() in ("true", "false"):
            new_config[key] = value.lower() == "true"
        else:
            try:
                # Try float first (handles integers too)
                new_config[key] = float(value)
                # Convert to int if it's a whole number
                if new_config[key] == int(new_config[key]):
                    new_config[key] = int(new_config[key])
            except ValueError:
                # Keep as string
                new_config[key] = value

    # Validate config
    is_valid, error = validate_config(new_config)
    if not is_valid:
        flash(f"Validation error: {error}", "error")
        return redirect(url_for("config.config_page"))

    # Write config
    try:
        write_config(app_config.CONFIG_PATH, new_config)
        flash("Configuration saved successfully", "success")
    except ConfigError as e:
        flash(f"Failed to save config: {e}", "error")

    return redirect(url_for("config.config_page"))
