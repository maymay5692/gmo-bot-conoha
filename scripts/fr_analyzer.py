"""Bitget FR Episode Analyzer.

Reads fr_snapshots_*.csv files, extracts FR episodes,
calculates corrected P&L, and reports persistence analysis.
"""
from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import groupby
from pathlib import Path
from typing import Callable

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


def count_fr_windows(start: datetime, end: datetime) -> int:
    """Count FR payment windows (00:00/08:00/16:00 UTC) in (start, end]."""
    if start >= end:
        return 0
    count = 0
    current_day = start.date()
    end_day = end.date()
    while current_day <= end_day:
        for hour in FR_PAYMENT_HOURS:
            payment = datetime(
                current_day.year, current_day.month, current_day.day,
                hour, 0, 0, tzinfo=timezone.utc,
            )
            if start < payment <= end:
                count += 1
        current_day += timedelta(days=1)
    return count


def _classify_persistence(fr_windows: int) -> str:
    if fr_windows == 0:
        return "spike"
    if fr_windows == 1:
        return "single"
    return "persistent"


def _build_episode(rows: list[dict]) -> Episode:
    frs = [abs(r["_parsed_fr"]) for r in rows]
    times = [r["_parsed_time"] for r in rows]
    volumes = [float(r["volume_24h"]) for r in rows]
    hedge_counts = Counter(r["hedge_status"] for r in rows)

    start = min(times)
    end = max(times)
    fr_windows = count_fr_windows(start, end)

    return Episode(
        symbol=rows[0]["symbol"],
        direction="LONG" if rows[0]["_parsed_fr"] < 0 else "SHORT",
        start_time=start,
        end_time=end,
        duration_minutes=(end - start).total_seconds() / 60,
        peak_fr=max(frs),
        mean_fr=sum(frs) / len(frs),
        fr_windows_crossed=fr_windows,
        hedge_status=hedge_counts.most_common(1)[0][0],
        volume_mean=sum(volumes) / len(volumes),
        persistence_class=_classify_persistence(fr_windows),
    )


def extract_episodes(
    snapshots: list[dict],
    gap_minutes: float = 10.0,
) -> list[Episode]:
    """Group snapshots into episodes per symbol.

    Splits on: time gap > gap_minutes, or FR sign flip.
    """
    episodes: list[Episode] = []
    gap_delta = timedelta(minutes=gap_minutes)

    for _symbol, group_iter in groupby(snapshots, key=lambda r: r["symbol"]):
        group = list(group_iter)
        if not group:
            continue

        current: list[dict] = [group[0]]

        for row in group[1:]:
            prev = current[-1]
            time_gap = row["_parsed_time"] - prev["_parsed_time"]
            sign_flip = (row["_parsed_fr"] > 0) != (prev["_parsed_fr"] > 0)

            if time_gap > gap_delta or sign_flip:
                episodes.append(_build_episode(current))
                current = [row]
            else:
                current.append(row)

        episodes.append(_build_episode(current))

    episodes.sort(key=lambda e: e.start_time)
    return episodes


def calc_episode_pnl(
    episode: Episode,
    position_size: float,
    fee_rate: float,
) -> dict:
    """Calculate theoretical hedged P&L for one episode.

    Assumes delta-neutral (perp+spot) → price_pnl=0.
    FR collected only at payment windows (not per poll).
    """
    fr_income = episode.mean_fr * position_size * episode.fr_windows_crossed
    fee = position_size * fee_rate
    net_pnl = fr_income - fee

    break_even_fr = (
        fee_rate / episode.fr_windows_crossed
        if episode.fr_windows_crossed > 0
        else float("inf")
    )

    return {
        "fr_income": fr_income,
        "fee": fee,
        "net_pnl": net_pnl,
        "profitable": net_pnl > 0,
        "break_even_fr": break_even_fr,
    }


def simulate_scenario(
    episodes: list[Episode],
    capital: float,
    max_positions: int,
    fee_rate: float,
    filter_fn: Callable[[Episode], bool],
) -> dict:
    """Run what-if simulation for a filter scenario.

    Processes episodes in time order, respects max_positions.
    """
    filtered = sorted(
        [e for e in episodes if filter_fn(e)],
        key=lambda e: e.start_time,
    )

    if not filtered:
        return {
            "traded": 0,
            "profitable": 0,
            "total_pnl": 0.0,
            "monthly_pnl": 0.0,
            "annual_return_pct": 0.0,
        }

    position_size = capital / max_positions
    active_ends: list[datetime] = []
    total_pnl = 0.0
    traded = 0
    profitable_count = 0

    for ep in filtered:
        active_ends = [t for t in active_ends if t > ep.start_time]

        if len(active_ends) >= max_positions:
            continue

        active_ends.append(ep.end_time)
        pnl = calc_episode_pnl(ep, position_size, fee_rate)
        total_pnl += pnl["net_pnl"]
        traded += 1
        if pnl["profitable"]:
            profitable_count += 1

    all_times = [e.start_time for e in filtered] + [e.end_time for e in filtered]
    days = max((max(all_times) - min(all_times)).total_seconds() / 86400, 1.0)

    return {
        "traded": traded,
        "profitable": profitable_count,
        "total_pnl": total_pnl,
        "monthly_pnl": total_pnl / days * 30,
        "annual_return_pct": (total_pnl / days * 365) / capital * 100,
    }
