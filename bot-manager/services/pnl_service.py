"""P&L tracking service with JSON file persistence."""
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

from services.gmo_api_service import get_account_margin, GmoApiError

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

SNAPSHOT_INTERVAL_SEC = 300  # 5 minutes
MAX_SNAPSHOTS = 2880  # ~10 days at 5-min intervals

_data_dir: str = ""
_last_snapshot_time: float = 0.0


def init(data_dir: str) -> None:
    """Initialize P&L service with data directory."""
    global _data_dir
    _data_dir = data_dir


def _ensure_data_dir() -> None:
    """Create data directory if it doesn't exist."""
    if _data_dir:
        os.makedirs(_data_dir, exist_ok=True)


def _get_data_path() -> str:
    """Get path to the P&L data JSON file."""
    return os.path.join(_data_dir, "pnl_history.json")


def _load_snapshots() -> list:
    """Load snapshots from JSON file."""
    path = _get_data_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load P&L data: %s", e)
        return []


def _save_snapshots(snapshots: list) -> None:
    """Save snapshots to JSON file, trimming to MAX_SNAPSHOTS."""
    _ensure_data_dir()
    path = _get_data_path()
    trimmed = snapshots[-MAX_SNAPSHOTS:]
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(trimmed, f, ensure_ascii=False)
    except OSError as e:
        logger.error("Failed to save P&L data: %s", e)


def take_snapshot() -> Optional[dict]:
    """Take a P&L snapshot from GMO API if interval has passed.

    Returns the snapshot dict if taken, None if skipped or failed.
    """
    global _last_snapshot_time

    now = time.time()
    if now - _last_snapshot_time < SNAPSHOT_INTERVAL_SEC:
        return None

    try:
        margin = get_account_margin()
    except (GmoApiError, requests.RequestException, OSError) as e:
        logger.warning("Failed to fetch margin for P&L snapshot: %s", e)
        return None

    _last_snapshot_time = now
    timestamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")

    snapshot = {
        "timestamp": timestamp,
        "actual_profit_loss": margin.get("actualProfitLoss", "0"),
        "available_amount": margin.get("availableAmount", "0"),
        "profit_loss": margin.get("profitLoss", "0"),
        "margin": margin.get("margin", "0"),
    }

    snapshots = _load_snapshots()
    snapshots.append(snapshot)
    _save_snapshots(snapshots)

    return snapshot


def get_current_pnl() -> Optional[dict]:
    """Get current P&L data from GMO API (without saving snapshot)."""
    try:
        margin = get_account_margin()
        return {
            "actual_profit_loss": margin.get("actualProfitLoss", "0"),
            "available_amount": margin.get("availableAmount", "0"),
            "profit_loss": margin.get("profitLoss", "0"),
            "margin": margin.get("margin", "0"),
        }
    except (GmoApiError, requests.RequestException, OSError) as e:
        logger.warning("Failed to fetch current P&L: %s", e)
        return None


def get_chart_data(hours: int = 24) -> dict:
    """Get chart data for the specified time range.

    Returns dict with 'labels' (timestamps) and 'datasets' for Chart.js.
    """
    snapshots = _load_snapshots()

    if hours > 0:
        cutoff = datetime.now(JST) - timedelta(hours=hours)
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
        snapshots = [s for s in snapshots if s.get("timestamp", "") >= cutoff_str]

    labels = [s.get("timestamp", "") for s in snapshots]
    actual_pnl = [float(s.get("actual_profit_loss", 0)) for s in snapshots]
    unrealized_pnl = [float(s.get("profit_loss", 0)) for s in snapshots]

    return {
        "labels": labels,
        "actual_profit_loss": actual_pnl,
        "unrealized_profit_loss": unrealized_pnl,
    }
