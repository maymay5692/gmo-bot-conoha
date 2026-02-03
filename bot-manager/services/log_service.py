"""Log service for viewing bot logs via journalctl."""
import re
import subprocess
from typing import List

# Service name for journalctl
SERVICE_NAME = "gmo-bot"

# Valid timestamp pattern (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?$")


def get_recent_logs(lines: int = 100) -> List[str]:
    """Get recent log entries from journalctl.

    Args:
        lines: Number of log lines to retrieve (default: 100).

    Returns:
        List of log lines. Empty list if error occurs.
    """
    # Ensure lines is positive
    lines = max(1, lines)

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

    # Split output and filter empty lines
    log_lines = [
        line for line in result.stdout.split("\n")
        if line.strip()
    ]

    return log_lines


def get_logs_since(timestamp: str) -> List[str]:
    """Get log entries since a specific timestamp.

    Args:
        timestamp: Timestamp in format "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS".

    Returns:
        List of log lines since the timestamp.
        Empty list if timestamp is invalid or error occurs.
    """
    # Validate timestamp format to prevent command injection
    if not TIMESTAMP_PATTERN.match(timestamp):
        return []

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
