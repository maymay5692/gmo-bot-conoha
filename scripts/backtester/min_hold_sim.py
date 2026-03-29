"""min_hold（最低保持時間）シミュレーションモジュール。

open後一定時間closeを禁止した場合のP&L変化をwhat-ifシミュレーションする。
"""
from __future__ import annotations

from datetime import timedelta

from .data_loader import Trip
from .market_replay import MarketState, get_mid_price_series

_TIMELINE_BUFFER_S = 10
_DEFAULT_HOLD_VALUES = [30, 60, 120, 180, 300]


def simulate_min_hold(
    trips: list[Trip],
    timeline: list[MarketState],
    min_hold_s: float,
) -> dict:
    """hold_time < min_hold_s のtripをmin_hold_s時点のmid_priceで再評価。

    Args:
        trips: build_trips()の結果
        timeline: build_market_timeline()の結果
        min_hold_s: 最低保持時間（秒）

    Returns:
        dict with min_hold_s, total_trips, affected_trips, original_pnl_sum,
        simulated_pnl_sum, delta_pnl, pnl_per_trip_orig, pnl_per_trip_sim,
        simulated_pnl_list
    """
    matched = [t for t in trips if t.close_fill is not None]
    if not matched:
        return {
            "min_hold_s": min_hold_s, "total_trips": 0, "affected_trips": 0,
            "original_pnl_sum": 0.0, "simulated_pnl_sum": 0.0, "delta_pnl": 0.0,
            "pnl_per_trip_orig": 0.0, "pnl_per_trip_sim": 0.0, "simulated_pnl_list": [],
        }

    original_pnl = 0.0
    simulated_pnl = 0.0
    affected = 0
    sim_pnl_list: list[float] = []

    for trip in matched:
        original_pnl += trip.pnl_jpy
        if trip.hold_time_s >= min_hold_s:
            simulated_pnl += trip.pnl_jpy
            sim_pnl_list.append(trip.pnl_jpy)
            continue

        open_ts = trip.open_fill.timestamp
        target_ts = open_ts + timedelta(seconds=min_hold_s)
        search_end = target_ts + timedelta(seconds=_TIMELINE_BUFFER_S)
        series = get_mid_price_series(timeline, open_ts, search_end)

        target_mid = None
        for ts, mid in series:
            elapsed = (ts - open_ts).total_seconds()
            if elapsed >= min_hold_s - 1.0:
                target_mid = mid
                break

        if target_mid is None:
            simulated_pnl += trip.pnl_jpy
            sim_pnl_list.append(trip.pnl_jpy)
            continue

        affected += 1
        direction = 1.0 if trip.open_fill.side == "BUY" else -1.0
        size = trip.open_fill.size
        mid_change = target_mid - trip.open_fill.mid_price
        mid_pnl = mid_change * size * direction
        new_pnl = mid_pnl + trip.spread_captured_jpy
        simulated_pnl += new_pnl
        sim_pnl_list.append(new_pnl)

    total = len(matched)
    return {
        "min_hold_s": min_hold_s, "total_trips": total, "affected_trips": affected,
        "original_pnl_sum": original_pnl, "simulated_pnl_sum": simulated_pnl,
        "delta_pnl": simulated_pnl - original_pnl,
        "pnl_per_trip_orig": original_pnl / total, "pnl_per_trip_sim": simulated_pnl / total,
        "simulated_pnl_list": sim_pnl_list,
    }


def simulate_min_hold_sweep(
    trips: list[Trip],
    timeline: list[MarketState],
    hold_values: list[int] | None = None,
) -> list[dict]:
    """複数のmin_hold値でシミュレーション結果を返す。

    Args:
        trips: build_trips()の結果
        timeline: build_market_timeline()の結果
        hold_values: テスト対象のmin_hold値リスト。Noneの場合はデフォルト値を使用

    Returns:
        各min_hold値に対するシミュレーション結果のリスト（min_hold値でソート済み）
    """
    if hold_values is None:
        hold_values = _DEFAULT_HOLD_VALUES
    return [simulate_min_hold(trips, timeline, float(h)) for h in hold_values]
