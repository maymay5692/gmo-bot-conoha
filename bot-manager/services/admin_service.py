"""Admin service for OS-level management operations."""
import os
import platform
import subprocess
from dataclasses import dataclass
from typing import Optional

IS_WINDOWS = platform.system() == "Windows"
BOT_DIR = r"C:\gmo-bot" if IS_WINDOWS else "/home/ubuntu/gmo-bot"
BOT_MANAGER_SERVICE = "bot-manager"
BOT_SERVICE = "gmo-bot"
GMO_CRED_KEYS = ("GMO_API_KEY", "GMO_API_SECRET")


@dataclass(frozen=True)
class CommandResult:
    """Immutable result of a command execution."""

    success: bool
    output: str
    error: Optional[str] = None


def reset_os_password(new_password: str) -> CommandResult:
    """Reset the OS Administrator/root password.

    Windows: net user Administrator <password>
    Linux: chpasswd
    """
    if not new_password or len(new_password) < 8:
        return CommandResult(
            success=False,
            output="",
            error="Password must be at least 8 characters",
        )

    if IS_WINDOWS:
        cmd = ["net", "user", "Administrator", new_password]
    else:
        cmd = ["sudo", "chpasswd"]

    try:
        if IS_WINDOWS:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=False, timeout=30
            )
        else:
            result = subprocess.run(
                cmd,
                input=f"root:{new_password}\n",
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        return CommandResult(
            success=result.returncode == 0,
            output=result.stdout.strip() if result.stdout else "",
            error=result.stderr.strip() if result.stderr else "" if result.returncode != 0 else None,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(success=False, output="", error="Command timed out")
    except OSError as e:
        return CommandResult(success=False, output="", error=str(e))


def self_update() -> CommandResult:
    """Pull latest code and install dependencies.

    Returns the git pull result. The caller is responsible for
    triggering a service restart after confirming the result.
    """
    try:
        git_result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=BOT_DIR,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if git_result.returncode != 0:
            return CommandResult(
                success=False,
                output=git_result.stdout.strip() if git_result.stdout else "",
                error=git_result.stderr.strip() if git_result.stderr else "",
            )

        pip_cmd = (
            ["pip", "install", "-r", "bot-manager/requirements.txt"]
            if IS_WINDOWS
            else ["pip3", "install", "-r", "bot-manager/requirements.txt"]
        )
        pip_result = subprocess.run(
            pip_cmd,
            cwd=BOT_DIR,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

        git_output = git_result.stdout.strip() if git_result.stdout else ""
        if pip_result.returncode != 0:
            pip_err = pip_result.stderr.strip() if pip_result.stderr else ""
            return CommandResult(
                success=False,
                output=f"git pull: {git_output}",
                error=f"pip install failed: {pip_err}",
            )

        return CommandResult(
            success=True,
            output=f"git pull: {git_output}\npip install: OK",
        )
    except subprocess.TimeoutExpired:
        return CommandResult(success=False, output="", error="Command timed out")
    except OSError as e:
        return CommandResult(success=False, output="", error=str(e))


def restart_bot_manager() -> CommandResult:
    """Restart the bot-manager service (delayed to allow response)."""
    if IS_WINDOWS:
        cmd = ["nssm", "restart", BOT_MANAGER_SERVICE]
    else:
        cmd = ["sudo", "systemctl", "restart", BOT_MANAGER_SERVICE]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=30
        )
        return CommandResult(
            success=result.returncode == 0,
            output=result.stdout.strip() if result.stdout else "",
            error=result.stderr.strip() if result.stderr else "" if result.returncode != 0 else None,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(success=False, output="", error="Command timed out")
    except OSError as e:
        return CommandResult(success=False, output="", error=str(e))


def _parse_nssm_env(raw: str) -> dict:
    """Parse nssm AppEnvironmentExtra output into a dict.

    nssm prints each variable as a KEY=VALUE line. Blank lines and
    lines without '=' are ignored.
    """
    result: dict = {}
    for line in (raw or "").splitlines():
        stripped = line.strip()
        if not stripped or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key:
            result[key] = value
    return result


def sync_gmo_credentials() -> CommandResult:
    """Copy GMO_API_KEY/SECRET from the gmo-bot nssm service into
    the bot-manager service and the current Python process.

    - Reads env vars from `nssm get gmo-bot AppEnvironmentExtra`.
    - Updates os.environ so /api/pnl/* starts working immediately.
    - Persists into bot-manager via `nssm set bot-manager AppEnvironmentExtra
      +GMO_API_KEY=... +GMO_API_SECRET=...` so the creds survive restarts.
      The `+` prefix adds/replaces individual entries without clobbering
      unrelated variables already set on the service.
    """
    if not IS_WINDOWS:
        return CommandResult(
            success=False, output="", error="sync_gmo_credentials is Windows-only"
        )

    try:
        get_result = subprocess.run(
            ["nssm", "get", BOT_SERVICE, "AppEnvironmentExtra"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            success=False, output="", error="nssm get gmo-bot timed out"
        )
    except OSError as e:
        return CommandResult(success=False, output="", error=f"nssm not available: {e}")

    if get_result.returncode != 0:
        return CommandResult(
            success=False,
            output=get_result.stdout.strip() if get_result.stdout else "",
            error=(
                f"nssm get {BOT_SERVICE} failed: "
                f"{get_result.stderr.strip() if get_result.stderr else ''}"
            ),
        )

    env_map = _parse_nssm_env(get_result.stdout or "")
    missing = [k for k in GMO_CRED_KEYS if not env_map.get(k)]
    if missing:
        return CommandResult(
            success=False,
            output=f"Keys seen in gmo-bot env: {sorted(env_map.keys())}",
            error=f"Missing credentials in gmo-bot service: {missing}",
        )

    # Runtime update (takes effect immediately, no restart needed).
    for key in GMO_CRED_KEYS:
        os.environ[key] = env_map[key]

    # Persist into bot-manager service env using '+' prefix which
    # adds/replaces individual entries without clearing the rest.
    set_cmd = ["nssm", "set", BOT_MANAGER_SERVICE, "AppEnvironmentExtra"]
    for key in GMO_CRED_KEYS:
        set_cmd.append(f"+{key}={env_map[key]}")

    try:
        set_result = subprocess.run(
            set_cmd, capture_output=True, text=True, check=False, timeout=30
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            success=False,
            output="Runtime env updated but nssm set timed out",
            error="nssm set bot-manager timed out",
        )
    except OSError as e:
        return CommandResult(
            success=False,
            output="Runtime env updated but nssm set failed",
            error=str(e),
        )

    if set_result.returncode != 0:
        return CommandResult(
            success=False,
            output="Runtime env updated but nssm set failed",
            error=(
                f"nssm set bot-manager failed: "
                f"{set_result.stderr.strip() if set_result.stderr else ''}"
            ),
        )

    return CommandResult(
        success=True,
        output=(
            "GMO credentials synced: runtime os.environ updated and "
            "bot-manager AppEnvironmentExtra persisted for future restarts"
        ),
    )


def run_deploy() -> CommandResult:
    """Execute the deploy script (download-release.ps1 or equivalent)."""
    if IS_WINDOWS:
        script = os.path.join(BOT_DIR, "deploy", "download-release.ps1")
        cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", script]
    else:
        script = os.path.join(BOT_DIR, "deploy", "download-release.sh")
        cmd = ["bash", script]

    if not os.path.exists(script):
        return CommandResult(
            success=False,
            output="",
            error=f"Deploy script not found: {script}",
        )

    try:
        result = subprocess.run(
            cmd,
            cwd=BOT_DIR,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        return CommandResult(
            success=result.returncode == 0,
            output=result.stdout.strip() if result.stdout else "",
            error=result.stderr.strip() if result.stderr else "" if result.returncode != 0 else None,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            success=False, output="", error="Deploy script timed out (5 min)"
        )
    except OSError as e:
        return CommandResult(success=False, output="", error=str(e))
