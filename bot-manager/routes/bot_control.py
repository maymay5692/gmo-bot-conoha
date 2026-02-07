"""Bot control API routes."""
from flask import Blueprint, jsonify, Response

from auth import requires_auth
from services.bot_service import get_status, start_bot, stop_bot, restart_bot

bot_control_bp = Blueprint("bot_control", __name__)


@bot_control_bp.route("/status")
@requires_auth
def api_status() -> Response:
    """Get bot status as JSON."""
    status = get_status()
    return jsonify({
        "is_running": status.is_running,
        "pid": status.pid,
        "memory": status.memory,
        "uptime": status.uptime,
        "error": status.error,
    })


@bot_control_bp.route("/bot/start", methods=["POST"])
@requires_auth
def api_start() -> Response:
    """Start the bot service."""
    success = start_bot()
    if success:
        return jsonify({"success": True, "message": "Bot started"})
    return jsonify({"success": False, "message": "Failed to start bot"}), 500


@bot_control_bp.route("/bot/stop", methods=["POST"])
@requires_auth
def api_stop() -> Response:
    """Stop the bot service."""
    success = stop_bot()
    if success:
        return jsonify({"success": True, "message": "Bot stopped"})
    return jsonify({"success": False, "message": "Failed to stop bot"}), 500


@bot_control_bp.route("/bot/restart", methods=["POST"])
@requires_auth
def api_restart() -> Response:
    """Restart the bot service."""
    success = restart_bot()
    if success:
        return jsonify({"success": True, "message": "Bot restarted"})
    return jsonify({"success": False, "message": "Failed to restart bot"}), 500
