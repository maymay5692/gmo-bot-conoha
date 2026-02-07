"""Bot service control via nssm (Windows) or systemd (Linux)."""
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

SERVICE_NAME = "gmo-bot"
IS_WINDOWS = platform.system() == "Windows"


@dataclass
class BotStatus:
    """Bot service status."""

    is_running: bool
    pid: Optional[int] = None
    memory: Optional[str] = None
    uptime: Optional[str] = None
    error: Optional[str] = None


def get_status() -> BotStatus:
    """Get the current status of the bot service."""
    if IS_WINDOWS:
        return _get_status_windows()
    return _get_status_linux()


def _get_status_windows() -> BotStatus:
    """Get bot status using nssm on Windows."""
    result = subprocess.run(
        ["nssm", "status", SERVICE_NAME],
        capture_output=True,
        text=True,
        check=False,
    )

    output = result.stdout.strip()

    if "SERVICE_RUNNING" in output:
        pid = _get_pid_windows()
        return BotStatus(is_running=True, pid=pid)

    if "SERVICE_STOPPED" in output:
        return BotStatus(is_running=False)

    if "Can't open service" in (result.stdout + result.stderr):
        return BotStatus(is_running=False, error="Service not found")

    return BotStatus(is_running=False, error=output or "Unknown status")


def _get_pid_windows() -> Optional[int]:
    """Get PID of the service process on Windows."""
    result = subprocess.run(
        ["tasklist", "/FI", f"SERVICES eq {SERVICE_NAME}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    for line in result.stdout.strip().split("\n"):
        parts = line.replace('"', '').split(",")
        if len(parts) >= 2:
            try:
                return int(parts[1])
            except ValueError:
                pass
    return None


def _get_status_linux() -> BotStatus:
    """Get bot status using systemctl on Linux."""
    result = subprocess.run(
        ["sudo", "systemctl", "status", SERVICE_NAME],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode == 4 or "could not be found" in result.stderr:
        return BotStatus(is_running=False, error="Service not found")

    if result.returncode == 3 or "inactive" in result.stdout:
        return BotStatus(is_running=False)

    stdout = result.stdout

    pid = None
    pid_match = re.search(r"Main PID:\s*(\d+)", stdout)
    if pid_match:
        pid = int(pid_match.group(1))

    memory = None
    memory_match = re.search(r"Memory:\s*(\S+)", stdout)
    if memory_match:
        memory = memory_match.group(1)

    uptime = None
    uptime_match = re.search(r"Active:.*since\s+(.+)", stdout)
    if uptime_match:
        uptime = uptime_match.group(1).strip()

    return BotStatus(
        is_running=True,
        pid=pid,
        memory=memory,
        uptime=uptime,
    )


def _run_service_command(action: str) -> bool:
    """Run a service control command."""
    if IS_WINDOWS:
        cmd = ["nssm", action, SERVICE_NAME]
    else:
        cmd = ["sudo", "systemctl", action, SERVICE_NAME]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def start_bot() -> bool:
    """Start the bot service."""
    return _run_service_command("start")


def stop_bot() -> bool:
    """Stop the bot service."""
    return _run_service_command("stop")


def restart_bot() -> bool:
    """Restart the bot service."""
    return _run_service_command("restart")
