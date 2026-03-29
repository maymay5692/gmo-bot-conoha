"""ボラティリティレジーム分析モジュール。

EWMA volatilityのパーセンタイルで低・中・高の3レジームに分類し、
レジーム別P&L集計とフィルタwhat-ifシミュレーションを提供する。
"""
from __future__ import annotations

from datetime import datetime

from .data_loader import Trip
from .market_replay import MarketState, get_market_state_at


def _percentile(sorted_values: list[float], pct: float) -> float:
    """ソート済みリストのパーセンタイル値を返す（線形補間）。"""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    k = (n - 1) * pct / 100.0
    f = int(k)
    c = f + 1
    if c >= n:
        return sorted_values[-1]
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])


def classify_vol_regime(
    timeline: list[MarketState],
    percentiles: tuple[float, float] = (25, 75),
) -> dict:
    """volatility分布のパーセンタイルで各時刻にレジームラベルを付与。

    Args:
        timeline: build_market_timeline()の結果
        percentiles: (低/中の境界, 中/高の境界) パーセンタイル

    Returns:
        {
            "boundaries": {"low": float, "high": float},
            "labels": {datetime: "low" | "mid" | "high"},
        }
    """
    if not timeline:
        return {
            "boundaries": {"low": 0.0, "high": 0.0},
            "labels": {},
        }

    vols = sorted(s.volatility for s in timeline)
    p_low = _percentile(vols, percentiles[0])
    p_high = _percentile(vols, percentiles[1])

    # 全volatilityが同一の場合、全てmid領域
    if p_low == p_high:
        labels = {s.timestamp: "mid" for s in timeline}
        return {"boundaries": {"low": p_low, "high": p_high}, "labels": labels}

    labels: dict[datetime, str] = {}
    for s in timeline:
        if s.volatility < p_low:
            labels[s.timestamp] = "low"
        elif s.volatility >= p_high:
            labels[s.timestamp] = "high"
        else:
            labels[s.timestamp] = "mid"

    return {
        "boundaries": {"low": p_low, "high": p_high},
        "labels": labels,
    }


def _get_trip_regime(
    trip: Trip,
    regime_result: dict,
    timeline: list[MarketState],
) -> tuple[str, float]:
    """tripのopen時刻でのレジームとvolatilityを返す。"""
    state = get_market_state_at(timeline, trip.open_fill.timestamp)
    if state is None:
        return "mid", 0.0
    label = regime_result["labels"].get(state.timestamp, "mid")
    return label, state.volatility


def analyze_by_vol_regime(
    trips: list[Trip],
    regime_result: dict,
    timeline: list[MarketState],
) -> list[dict]:
    """レジーム別のP&L集計。"""
    matched = [t for t in trips if t.close_fill is not None]
    if not matched:
        return []

    groups: dict[str, list[tuple[Trip, float]]] = {
        "low": [], "mid": [], "high": [],
    }
    for t in matched:
        regime, vol = _get_trip_regime(t, regime_result, timeline)
        if regime in groups:
            groups[regime].append((t, vol))

    rows = []
    for regime in ["low", "mid", "high"]:
        items = groups[regime]
        if not items:
            rows.append({
                "regime": regime, "count": 0, "pnl_sum": 0.0, "pnl_mean": 0.0,
                "adverse_mean": 0.0, "win_rate": 0.0, "hold_mean_s": 0.0, "vol_mean": 0.0,
            })
            continue
        trip_list = [item[0] for item in items]
        vol_list = [item[1] for item in items]
        pnl_list = [t.pnl_jpy for t in trip_list]
        adverse_list = [t.mid_adverse_jpy for t in trip_list]
        hold_list = [t.hold_time_s for t in trip_list]
        wins = sum(1 for p in pnl_list if p > 0)
        rows.append({
            "regime": regime,
            "count": len(trip_list),
            "pnl_sum": sum(pnl_list),
            "pnl_mean": sum(pnl_list) / len(pnl_list),
            "adverse_mean": sum(adverse_list) / len(adverse_list),
            "win_rate": wins / len(trip_list),
            "hold_mean_s": sum(hold_list) / len(hold_list),
            "vol_mean": sum(vol_list) / len(vol_list),
        })
    return rows
