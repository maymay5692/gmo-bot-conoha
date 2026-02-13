"""Admin API routes for OS-level management."""
import hmac
import logging
import re
import secrets
import threading
import time
from typing import Tuple, Union

from flask import Blueprint, Response, jsonify, request

from auth import requires_auth
from services.admin_service import (
    reset_os_password,
    self_update,
    restart_bot_manager,
    run_deploy,
)

admin_bp = Blueprint("admin", __name__)
audit_log = logging.getLogger("admin.audit")

# Thread-safe one-time confirmation tokens for dangerous operations
_token_lock = threading.Lock()
_pending_tokens: dict[str, tuple[str, float]] = {}
TOKEN_TTL_SECONDS = 300

# Password must not contain control characters or newlines
_INVALID_PASSWORD_RE = re.compile(r"[\x00-\x1f\x7f]")


def _generate_confirm_token(action: str) -> str:
    """Generate a one-time confirmation token with expiration."""
    token = secrets.token_urlsafe(16)
    with _token_lock:
        _pending_tokens[action] = (token, time.time())
    return token


def _verify_confirm_token(action: str, token: str) -> bool:
    """Verify and consume a one-time confirmation token."""
    with _token_lock:
        entry = _pending_tokens.get(action)
        if not entry:
            return False
        saved_token, created_at = entry
        if time.time() - created_at > TOKEN_TTL_SECONDS:
            del _pending_tokens[action]
            return False
        if not hmac.compare_digest(saved_token, token):
            return False
        del _pending_tokens[action]
        return True


FlaskResponse = Union[Response, Tuple[Response, int]]


@admin_bp.route("/admin/reset-password", methods=["POST"])
@requires_auth
def api_reset_password() -> FlaskResponse:
    """Reset the OS Administrator password.

    Step 1: POST {"new_password": "..."} -> returns confirm_token
    Step 2: POST {"new_password": "...", "confirm_token": "..."} -> executes
    """
    data = request.get_json(silent=True) or {}
    new_password = data.get("new_password", "")
    confirm_token = data.get("confirm_token")

    if not new_password:
        return jsonify({
            "success": False, "error": "new_password is required"
        }), 400

    if len(new_password) < 8:
        return jsonify({
            "success": False,
            "error": "Password must be at least 8 characters",
        }), 400

    if _INVALID_PASSWORD_RE.search(new_password):
        return jsonify({
            "success": False,
            "error": "Password contains invalid characters",
        }), 400

    if not confirm_token:
        token = _generate_confirm_token("reset-password")
        return jsonify({
            "success": True,
            "confirm_required": True,
            "confirm_token": token,
            "message": "Send again with confirm_token to execute",
        })

    if not _verify_confirm_token("reset-password", confirm_token):
        audit_log.warning(
            "Failed password reset attempt from %s",
            request.remote_addr,
        )
        return jsonify({
            "success": False,
            "error": "Invalid or expired confirm_token",
        }), 403

    result = reset_os_password(new_password)
    audit_log.info(
        "Password reset %s from %s",
        "succeeded" if result.success else "failed",
        request.remote_addr,
    )
    status_code = 200 if result.success else 500
    return jsonify({
        "success": result.success,
        "output": result.output,
        "error": result.error,
    }), status_code


@admin_bp.route("/admin/self-update", methods=["POST"])
@requires_auth
def api_self_update() -> FlaskResponse:
    """Pull latest code and optionally restart bot-manager.

    Pass {"restart": true} to also restart the service after update.
    """
    data = request.get_json(silent=True) or {}
    should_restart = data.get("restart", False)

    result = self_update()
    audit_log.info(
        "Self-update %s from %s",
        "succeeded" if result.success else "failed",
        request.remote_addr,
    )
    response_data = {
        "success": result.success,
        "output": result.output,
        "error": result.error,
    }

    if result.success and should_restart:
        response_data["restart_scheduled"] = True
        timer = threading.Timer(2.0, restart_bot_manager)
        timer.daemon = True
        timer.start()

    status_code = 200 if result.success else 500
    return jsonify(response_data), status_code


@admin_bp.route("/admin/deploy", methods=["POST"])
@requires_auth
def api_deploy() -> FlaskResponse:
    """Execute the deploy script (download latest release)."""
    result = run_deploy()
    audit_log.info(
        "Deploy %s from %s",
        "succeeded" if result.success else "failed",
        request.remote_addr,
    )
    status_code = 200 if result.success else 500
    return jsonify({
        "success": result.success,
        "output": result.output,
        "error": result.error,
    }), status_code
