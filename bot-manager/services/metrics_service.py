"""Metrics and trades CSV reading service for analysis."""
import csv
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CSV_DATE_EXTRACT = re.compile(r"(?:metrics|trades)-(\d{4}-\d{2}-\d{2})\.csv$")

_log_dir: str = ""


def init(log_dir: str) -> None:
    """Initialize metrics service with bot log directory."""
    global _log_dir
    _log_dir = log_dir


def _read_csv(file_path: str) -> Optional[list[dict]]:
    """Read a CSV file and return rows as list of dicts."""
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except (OSError, csv.Error) as e:
        logger.warning("Failed to read CSV %s: %s", file_path, e)
        return None


def get_metrics_csv(date: str) -> Optional[list[dict]]:
    """Read metrics CSV for a given date and return as list of dicts.

    Args:
        date: Date string in YYYY-MM-DD format.

    Returns:
        List of dicts (one per row), or None if file not found or invalid date.
    """
    if not DATE_PATTERN.match(date):
        return None
    file_path = os.path.join(_log_dir, "metrics", f"metrics-{date}.csv")
    return _read_csv(file_path)


def get_trades_csv(date: str) -> Optional[list[dict]]:
    """Read trades CSV for a given date and return as list of dicts.

    Args:
        date: Date string in YYYY-MM-DD format.

    Returns:
        List of dicts (one per row), or None if file not found or invalid date.
    """
    if not DATE_PATTERN.match(date):
        return None
    file_path = os.path.join(_log_dir, "trades", f"trades-{date}.csv")
    return _read_csv(file_path)


def list_available_dates(csv_type: str = "metrics") -> list[str]:
    """List available CSV dates for a given type.

    Args:
        csv_type: Either "metrics" or "trades".

    Returns:
        Sorted list of date strings (YYYY-MM-DD).
    """
    if csv_type not in ("metrics", "trades"):
        return []

    target_dir = os.path.join(_log_dir, csv_type)
    if not os.path.isdir(target_dir):
        return []

    dates = []
    for filename in os.listdir(target_dir):
        match = CSV_DATE_EXTRACT.match(filename)
        if match:
            dates.append(match.group(1))

    return sorted(dates)
