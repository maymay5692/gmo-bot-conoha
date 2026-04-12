"""Bitget FR Episode Analyzer.

Reads fr_snapshots_*.csv files, extracts FR episodes,
calculates corrected P&L, and reports persistence analysis.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data_cache"
FR_PAYMENT_HOURS = (0, 8, 16)
_DATE_RE = re.compile(r"fr_snapshots_(\d{4}-\d{2}-\d{2})\.csv")


@dataclass
class Episode:
    symbol: str
    direction: str
    start_time: datetime
    end_time: datetime
    duration_minutes: float
    peak_fr: float
    mean_fr: float
    fr_windows_crossed: int
    hedge_status: str
    volume_mean: float
    persistence_class: str


def load_snapshots(
    data_dir: Path = DATA_DIR,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Load and merge all fr_snapshots_*.csv files.

    Returns rows sorted by (symbol, timestamp).
    Each row gets '_parsed_time' and '_parsed_fr' fields.
    """
    files = sorted(data_dir.glob("fr_snapshots_*.csv"))

    if start_date or end_date:
        filtered = []
        for p in files:
            m = _DATE_RE.match(p.name)
            if not m:
                continue
            date_str = m.group(1)
            if start_date and date_str < start_date:
                continue
            if end_date and date_str > end_date:
                continue
            filtered.append(p)
        files = filtered

    rows: list[dict] = []
    for path in files:
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["_parsed_time"] = datetime.fromisoformat(row["timestamp"])
                row["_parsed_fr"] = float(row["funding_rate"])
                rows.append(row)

    rows.sort(key=lambda r: (r["symbol"], r["_parsed_time"]))
    return rows
