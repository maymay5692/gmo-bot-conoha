"""Dashboard routes."""
from flask import Blueprint, render_template, Response

from app import requires_auth
from services.bot_service import get_status
from services.log_service import get_recent_logs

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@requires_auth
def index() -> Response:
    """Main dashboard page."""
    status = get_status()
    logs = get_recent_logs(lines=20)

    return render_template(
        "dashboard.html",
        status=status,
        logs=logs,
    )


@dashboard_bp.route("/partials/status")
@requires_auth
def status_partial() -> Response:
    """Status card partial for HTMX updates."""
    status = get_status()
    return render_template("partials/status_card.html", status=status)


@dashboard_bp.route("/partials/logs")
@requires_auth
def logs_partial() -> Response:
    """Logs partial for HTMX updates."""
    logs = get_recent_logs(lines=20)
    return render_template("partials/log_entries.html", logs=logs)
