"""Admin API routes for OS-level management."""
import hmac
import logging
import re
import secrets
import threading
import time
from typing import Optional, Tuple, Union

from flask import Blueprint, Response, jsonify, request

from auth import requires_auth
from services.admin_service import (
    ENV_FILE_PATH,
    load_env_file,
    reset_os_password,
    self_update,
    restart_bot_manager,
    run_deploy,
    sync_gmo_credentials,
)
from services.discord_notify import send_alert

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
    send_alert(
        "Admin: Password Reset",
        f"Result: {'Success' if result.success else 'Failed'}\n"
        f"From: {request.remote_addr}",
        color=0x00FF00 if result.success else 0xFF0000,
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
    send_alert(
        "Admin: Self-Update",
        f"Result: {'Success' if result.success else 'Failed'}\n"
        f"Output: {result.output[:200] if result.output else 'N/A'}",
        color=0x00FF00 if result.success else 0xFF0000,
    )
    response_data = {
        "success": result.success,
        "output": result.output,
        "error": result.error,
    }

    if result.success and should_restart:
        # restart_bot_manager() now spawns a fully detached cmd.exe with
        # an internal 3-second delay, so the HTTP response below is sent
        # before the actual nssm restart fires. No threading.Timer needed.
        restart_result = restart_bot_manager()
        response_data["restart_scheduled"] = restart_result.success
        if not restart_result.success:
            response_data["restart_error"] = restart_result.error

    status_code = 200 if result.success else 500
    return jsonify(response_data), status_code


@admin_bp.route("/admin/env-status", methods=["GET"])
@requires_auth
def api_env_status() -> FlaskResponse:
    """Diagnostic: show env file state and whether GMO creds are loaded.

    Safe to call — does not reveal secret values, only presence and length.
    Triggers a one-shot load_env_file() attempt so the response also
    reflects whether the file can be read from disk right now.
    """
    import os as _os
    env_file_exists = _os.path.isfile(ENV_FILE_PATH)
    env_file_size: Optional[int] = None
    if env_file_exists:
        try:
            env_file_size = _os.path.getsize(ENV_FILE_PATH)
        except OSError:
            env_file_size = -1

    loaded_before = {
        "GMO_API_KEY_set": bool(_os.environ.get("GMO_API_KEY")),
        "GMO_API_SECRET_set": bool(_os.environ.get("GMO_API_SECRET")),
    }
    try:
        loaded_count = load_env_file()
    except Exception as e:  # pragma: no cover - defensive
        loaded_count = -1

    loaded_after = {
        "GMO_API_KEY_set": bool(_os.environ.get("GMO_API_KEY")),
        "GMO_API_SECRET_set": bool(_os.environ.get("GMO_API_SECRET")),
    }

    return jsonify({
        "env_file_path": ENV_FILE_PATH,
        "env_file_exists": env_file_exists,
        "env_file_size": env_file_size,
        "keys_before_reload": loaded_before,
        "keys_after_reload": loaded_after,
        "reload_loaded_count": loaded_count,
    })


@admin_bp.route("/admin/sync-gmo-creds", methods=["POST"])
@requires_auth
def api_sync_gmo_creds() -> FlaskResponse:
    """Copy GMO_API_KEY/SECRET from the gmo-bot service env into bot-manager.

    Step 1: POST {} -> returns confirm_token
    Step 2: POST {"confirm_token": "..."} -> executes
    """
    data = request.get_json(silent=True) or {}
    confirm_token = data.get("confirm_token")

    if not confirm_token:
        token = _generate_confirm_token("sync-gmo-creds")
        return jsonify({
            "success": True,
            "confirm_required": True,
            "confirm_token": token,
            "message": "Send again with confirm_token to execute",
        })

    if not _verify_confirm_token("sync-gmo-creds", confirm_token):
        audit_log.warning(
            "Failed sync-gmo-creds attempt from %s",
            request.remote_addr,
        )
        return jsonify({
            "success": False,
            "error": "Invalid or expired confirm_token",
        }), 403

    result = sync_gmo_credentials()
    audit_log.info(
        "Sync GMO credentials %s from %s",
        "succeeded" if result.success else "failed",
        request.remote_addr,
    )
    send_alert(
        "Admin: Sync GMO Credentials",
        f"Result: {'Success' if result.success else 'Failed'}\n"
        f"Output: {result.output[:200] if result.output else 'N/A'}",
        color=0x00FF00 if result.success else 0xFF0000,
    )
    status_code = 200 if result.success else 500
    return jsonify({
        "success": result.success,
        "output": result.output,
        "error": result.error,
    }), status_code


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
    send_alert(
        "Admin: Deploy",
        f"Result: {'Success' if result.success else 'Failed'}\n"
        f"Output: {result.output[:200] if result.output else 'N/A'}",
        color=0x00FF00 if result.success else 0xFF0000,
    )
    status_code = 200 if result.success else 500
    return jsonify({
        "success": result.success,
        "output": result.output,
        "error": result.error,
    }), status_code


@admin_bp.route("/admin/system-info", methods=["GET"])
@requires_auth
def api_system_info() -> FlaskResponse:
    """Return VPS resource state for capacity planning (軸1 VPS 基盤監視).

    Returns: CPU usage %, memory (total/used/percent), disk usage per drive,
    uptime (boot_time + days), process count, and presence of key services
    (gmo-bot, bot-manager, cloudflared). Safe: no secret exposure.

    Used by mentor's 5/22 中間レビュー and 6月以降の各プロジェクト統合計画.
    """
    import os as _os
    import platform
    import time as _time
    import shutil

    info: dict = {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "node": platform.node(),
        },
        "cpu_count_logical": _os.cpu_count(),
    }

    try:
        import psutil  # type: ignore
        info["psutil_available"] = True

        info["cpu_percent"] = psutil.cpu_percent(interval=0.5)
        info["cpu_count_physical"] = psutil.cpu_count(logical=False)

        vm = psutil.virtual_memory()
        info["memory"] = {
            "total_mb": round(vm.total / (1024 * 1024), 1),
            "used_mb": round(vm.used / (1024 * 1024), 1),
            "available_mb": round(vm.available / (1024 * 1024), 1),
            "percent": vm.percent,
        }

        boot_time = psutil.boot_time()
        now = _time.time()
        uptime_seconds = now - boot_time
        info["uptime"] = {
            "boot_time_epoch": boot_time,
            "uptime_seconds": int(uptime_seconds),
            "uptime_days": round(uptime_seconds / 86400, 2),
        }

        info["process_count"] = len(psutil.pids())

        target_names = {"gmo-bot", "gmo-bot.exe", "bot-manager",
                        "cloudflared", "cloudflared.exe", "python.exe",
                        "gunicorn"}
        target_procs: dict = {n: [] for n in target_names}
        for p in psutil.process_iter(attrs=["pid", "name", "cpu_percent",
                                            "memory_info"]):
            try:
                pname = (p.info.get("name") or "").lower()
                for tn in target_names:
                    if tn in pname:
                        mem = p.info.get("memory_info")
                        target_procs[tn].append({
                            "pid": p.info.get("pid"),
                            "rss_mb": round(mem.rss / (1024 * 1024), 1)
                                       if mem else None,
                        })
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        info["target_processes"] = {
            k: v for k, v in target_procs.items() if v
        }
    except ImportError:
        info["psutil_available"] = False
        info["psutil_note"] = (
            "psutil not installed — run /api/admin/self-update with restart "
            "to install requirements.txt and re-call this endpoint"
        )

    disks: list = []
    if platform.system() == "Windows":
        candidate_drives = [f"{chr(c)}:\\" for c in range(ord("C"),
                                                          ord("Z") + 1)]
    else:
        candidate_drives = ["/"]
    for drive in candidate_drives:
        try:
            usage = shutil.disk_usage(drive)
            disks.append({
                "mount": drive,
                "total_gb": round(usage.total / (1024 ** 3), 2),
                "used_gb": round(usage.used / (1024 ** 3), 2),
                "free_gb": round(usage.free / (1024 ** 3), 2),
                "percent": round(usage.used / usage.total * 100, 1)
                          if usage.total > 0 else 0,
            })
        except (FileNotFoundError, PermissionError, OSError):
            continue
    info["disks"] = disks

    return jsonify(info)
