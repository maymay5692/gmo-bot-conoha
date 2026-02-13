"""Admin service for OS-level management operations."""
import os
import platform
import subprocess
from dataclasses import dataclass
from typing import Optional

IS_WINDOWS = platform.system() == "Windows"
BOT_DIR = r"C:\gmo-bot" if IS_WINDOWS else "/home/ubuntu/gmo-bot"
BOT_MANAGER_SERVICE = "bot-manager"


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
