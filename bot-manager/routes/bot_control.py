"""Bot control API routes."""
import os
import re

from flask import Blueprint, current_app, jsonify, Response

from auth import requires_auth
from services.bot_service import get_status, start_bot, stop_bot, restart_bot

bot_control_bp = Blueprint("bot_control", __name__)

_TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


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


@bot_control_bp.route("/tunnel-url")
@requires_auth
def api_tunnel_url() -> Response:
    """Get the current Cloudflare Quick Tunnel URL from cloudflared logs."""
    log_dir = current_app.config.get("APP_CONFIG", object()).BOT_LOG_DIR
    stderr_log = os.path.join(log_dir, "cloudflared-stderr.log")

    if not os.path.isfile(stderr_log):
        return jsonify({"tunnel_url": None, "error": "cloudflared log not found"})

    # Read last 200 lines (URL may be near start, but log rotates)
    try:
        with open(stderr_log, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        return jsonify({"tunnel_url": None, "error": str(e)})

    # Search from end to find most recent URL
    for line in reversed(lines):
        match = _TUNNEL_URL_RE.search(line)
        if match:
            return jsonify({"tunnel_url": match.group(0)})

    return jsonify({"tunnel_url": None, "error": "URL not found in log"})


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
