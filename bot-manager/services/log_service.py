"""Log service for viewing bot logs via log files (Windows) or journalctl (Linux)."""
import os
import platform
import re
import subprocess
from collections import deque
from typing import List

SERVICE_NAME = "gmo-bot"
IS_WINDOWS = platform.system() == "Windows"

TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?$")

# Windows log file paths
LOG_DIR = os.environ.get("BOT_LOG_DIR", r"C:\gmo-bot\logs")
STDOUT_LOG = os.path.join(LOG_DIR, "gmo-bot-stdout.log")
STDERR_LOG = os.path.join(LOG_DIR, "gmo-bot-stderr.log")


def get_recent_logs(lines: int = 100) -> List[str]:
    """Get recent log entries.

    Args:
        lines: Number of log lines to retrieve (default: 100).

    Returns:
        List of log lines. Empty list if error occurs.
    """
    lines = max(1, lines)

    if IS_WINDOWS:
        return _get_logs_from_file(lines)
    return _get_logs_journalctl(lines)


def _get_logs_from_file(lines: int) -> List[str]:
    """Read recent log lines from log files on Windows."""
    all_lines: List[str] = []

    for log_path in [STDOUT_LOG, STDERR_LOG]:
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    recent = deque(f, maxlen=lines)
                    all_lines.extend(line.rstrip() for line in recent if line.strip())
            except OSError:
                pass

    return all_lines[-lines:]


def _get_logs_journalctl(lines: int) -> List[str]:
    """Read recent logs from journalctl on Linux."""
    result = subprocess.run(
        [
            "journalctl",
            "-u", SERVICE_NAME,
            "-n", str(lines),
            "--no-pager",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return []

    return [line for line in result.stdout.split("\n") if line.strip()]


def get_logs_since(timestamp: str) -> List[str]:
    """Get log entries since a specific timestamp.

    Args:
        timestamp: Timestamp in format "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS".

    Returns:
        List of log lines since the timestamp.
        Empty list if timestamp is invalid or error occurs.
    """
    if not TIMESTAMP_PATTERN.match(timestamp):
        return []

    if IS_WINDOWS:
        return get_recent_logs(lines=500)

    result = subprocess.run(
        [
            "journalctl",
            "-u", SERVICE_NAME,
            "--since", timestamp,
            "--no-pager",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return []

    return [line for line in result.stdout.split("\n") if line.strip()]
