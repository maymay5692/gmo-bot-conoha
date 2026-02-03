"""Log viewing routes."""
from flask import Blueprint, render_template, request, jsonify, Response

from app import requires_auth
from services.log_service import get_recent_logs

logs_bp = Blueprint("logs", __name__)


@logs_bp.route("/logs")
@requires_auth
def logs_page() -> Response:
    """Log viewing page."""
    lines = request.args.get("lines", 100, type=int)
    # Ensure positive and cap at 1000 lines
    lines = max(1, min(lines, 1000))

    logs = get_recent_logs(lines=lines)

    return render_template("logs.html", logs=logs, lines=lines)


@logs_bp.route("/api/logs")
@requires_auth
def api_logs() -> Response:
    """Get logs as JSON."""
    lines = request.args.get("lines", 100, type=int)
    # Ensure positive and cap at 1000 lines
    lines = max(1, min(lines, 1000))

    logs = get_recent_logs(lines=lines)

    return jsonify({"logs": logs, "count": len(logs)})
