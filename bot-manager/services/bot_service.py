"""Bot service control via systemd."""
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

# Service name constant
SERVICE_NAME = "gmo-bot"


@dataclass
class BotStatus:
    """Bot service status."""

    is_running: bool
    pid: Optional[int] = None
    memory: Optional[str] = None
    uptime: Optional[str] = None
    error: Optional[str] = None


def get_status() -> BotStatus:
    """Get the current status of the bot service.

    Returns:
        BotStatus: Current status of the bot service.
    """
    result = subprocess.run(
        ["sudo", "systemctl", "status", SERVICE_NAME],
        capture_output=True,
        text=True,
        check=False,
    )

    # Service not found
    if result.returncode == 4 or "could not be found" in result.stderr:
        return BotStatus(is_running=False, error="Service not found")

    # Service inactive
    if result.returncode == 3 or "inactive" in result.stdout:
        return BotStatus(is_running=False)

    # Service active - parse details
    stdout = result.stdout

    # Extract PID
    pid = None
    pid_match = re.search(r"Main PID:\s*(\d+)", stdout)
    if pid_match:
        pid = int(pid_match.group(1))

    # Extract memory
    memory = None
    memory_match = re.search(r"Memory:\s*(\S+)", stdout)
    if memory_match:
        memory = memory_match.group(1)

    # Extract uptime from Active line
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


def start_bot() -> bool:
    """Start the bot service.

    Returns:
        bool: True if successful, False otherwise.
    """
    result = subprocess.run(
        ["sudo", "systemctl", "start", SERVICE_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def stop_bot() -> bool:
    """Stop the bot service.

    Returns:
        bool: True if successful, False otherwise.
    """
    result = subprocess.run(
        ["sudo", "systemctl", "stop", SERVICE_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def restart_bot() -> bool:
    """Restart the bot service.

    Returns:
        bool: True if successful, False otherwise.
    """
    result = subprocess.run(
        ["sudo", "systemctl", "restart", SERVICE_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0
