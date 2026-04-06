"""DVOL Z-Scoreレジーム分析モジュール。"""
from __future__ import annotations

import bisect
import math
from datetime import datetime

from .data_loader import Trip


def calc_dvol_zscore(dvol_data: list[dict], lookback_hours: int = 720) -> list[dict]:
    if not dvol_data:
        return []
    closes = [d["close"] for d in dvol_data]
    timestamps = [d["timestamp"] for d in dvol_data]
    result = []
    for i in range(len(closes)):
        start_idx = max(0, i - lookback_hours + 1)
        window = closes[start_idx:i + 1]
        if len(window) < 2:
            result.append({"timestamp": timestamps[i], "dvol": closes[i], "z_score": 0.0})
            continue
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / (len(window) - 1)
        std = math.sqrt(variance) if variance > 0 else 0.0
        z_score = (closes[i] - mean) / std if std > 0 else 0.0
        result.append({"timestamp": timestamps[i], "dvol": closes[i], "z_score": z_score})
    return result


def classify_dvol_regime(zscore_data: list[dict], z_threshold: float = 2.0) -> dict:
    if not zscore_data:
        return {"labels": {}, "stats": {"mean": 0.0, "std": 0.0}}
    labels: dict[datetime, str] = {}
    dvol_values = [d["dvol"] for d in zscore_data]
    for d in zscore_data:
        if d["z_score"] >= z_threshold:
            labels[d["timestamp"]] = "high"
        elif d["z_score"] <= -z_threshold:
            labels[d["timestamp"]] = "low"
        else:
            labels[d["timestamp"]] = "normal"
    mean = sum(dvol_values) / len(dvol_values)
    variance = (
        sum((x - mean) ** 2 for x in dvol_values) / (len(dvol_values) - 1)
        if len(dvol_values) > 1
        else 0.0
    )
    std = math.sqrt(variance) if variance > 0 else 0.0
    return {"labels": labels, "stats": {"mean": mean, "std": std}}


def _get_dvol_regime_at(
    timestamp: datetime, zscore_data: list[dict], regime_labels: dict[datetime, str]
) -> str:
    if not zscore_data:
        return "normal"
    ts_list = [d["timestamp"] for d in zscore_data]
    idx = bisect.bisect_right(ts_list, timestamp) - 1
    if idx < 0:
        return "normal"
    return regime_labels.get(ts_list[idx], "normal")


def analyze_by_dvol_regime(
    trips: list[Trip], dvol_regime_result: dict, zscore_data: list[dict]
) -> list[dict]:
    matched = [t for t in trips if t.close_fill is not None]
    if not matched:
        return []
    labels = dvol_regime_result["labels"]
    groups: dict[str, list[Trip]] = {"normal": [], "high": [], "low": []}
    for t in matched:
        regime = _get_dvol_regime_at(t.open_fill.timestamp, zscore_data, labels)
        if regime in groups:
            groups[regime].append(t)
    rows = []
    for regime in ["normal", "high", "low"]:
        items = groups[regime]
        if not items:
            rows.append(
                {"regime": regime, "count": 0, "pnl_sum": 0.0, "pnl_mean": 0.0, "win_rate": 0.0}
            )
            continue
        pnl_list = [t.pnl_jpy for t in items]
        wins = sum(1 for p in pnl_list if p > 0)
        rows.append(
            {
                "regime": regime,
                "count": len(items),
                "pnl_sum": sum(pnl_list),
                "pnl_mean": sum(pnl_list) / len(pnl_list),
                "win_rate": wins / len(items),
            }
        )
    return rows


def calc_dvol_filter_impact(
    trips: list[Trip],
    dvol_regime_result: dict,
    zscore_data: list[dict],
    exclude_regimes: list[str],
) -> dict:
    matched = [t for t in trips if t.close_fill is not None]
    labels = dvol_regime_result["labels"]
    exclude_set = set(exclude_regimes)
    included = [
        t
        for t in matched
        if _get_dvol_regime_at(t.open_fill.timestamp, zscore_data, labels) not in exclude_set
    ]
    excluded = [
        t
        for t in matched
        if _get_dvol_regime_at(t.open_fill.timestamp, zscore_data, labels) in exclude_set
    ]

    def _stats(ts: list[Trip]) -> dict:
        if not ts:
            return {"pnl_sum": 0.0, "pnl_mean": 0.0, "count": 0}
        pnl_list = [t.pnl_jpy for t in ts]
        return {
            "pnl_sum": sum(pnl_list),
            "pnl_mean": sum(pnl_list) / len(pnl_list),
            "count": len(ts),
        }

    return {
        "exclude_spec": "+".join(exclude_regimes),
        "included": _stats(included),
        "excluded": _stats(excluded),
        "total": {"pnl_sum": sum(t.pnl_jpy for t in matched), "count": len(matched)},
    }
