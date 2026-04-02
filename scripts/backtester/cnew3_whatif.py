"""C-new-3 What-if分析: close戦略変更のシミュレーション。

仮説: death zone (60-300s) で決済せず、mean reversionを待つ方が有利。
手法: 各tripのclose_timeを変更した場合のP&L変化を、mid_price推移から推定。
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from dataclasses import dataclass

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from backtester.data_loader import (
    build_order_book,
    build_trips,
    load_metrics,
    load_trades,
)
from datetime import timedelta

from backtester.market_replay import build_market_timeline, get_mid_price_series
from backtester.trip_analyzer import analyze_close_dynamics


# timeline探索時のバッファ（metricsの3s間隔 + 余裕）
_TIMELINE_BUFFER_S = 10


@dataclass(frozen=True)
class WhatIfResult:
    scenario: str
    total_trips: int
    affected_trips: int
    original_pnl: float
    simulated_pnl: float
    delta_pnl: float
    pnl_per_trip_orig: float
    pnl_per_trip_sim: float


def _find_mid_at(timeline, open_ts, target_s: float) -> float | None:
    """open_ts + target_s 時点のmid_priceを取得。"""
    target_ts = open_ts + timedelta(seconds=target_s)
    search_end = target_ts + timedelta(seconds=_TIMELINE_BUFFER_S)
    series = get_mid_price_series(timeline, open_ts, search_end)
    for ts, mid in series:
        elapsed = (ts - open_ts).total_seconds()
        if elapsed >= target_s - 1.0:  # 1s tolerance for metrics interval
            return mid
    return None


def _simulate_delayed_close(
    matched_trips, timeline, min_hold_s: float, target_hold_s: float
) -> WhatIfResult:
    """
    min_hold_s < hold_time < target_hold_sのtripについて、
    target_hold_s時点のmid_priceでcloseしたと仮定してP&L変化を推定。
    """
    original_pnl = 0.0
    simulated_pnl = 0.0
    affected = 0
    total = 0

    for trip in matched_trips:
        if trip.close_fill is None:
            continue
        total += 1
        original_pnl += trip.pnl_jpy

        if trip.hold_time_s < min_hold_s or trip.hold_time_s >= target_hold_s:
            simulated_pnl += trip.pnl_jpy
            continue

        open_ts = trip.open_fill.timestamp
        target_mid = _find_mid_at(timeline, open_ts, target_hold_s)

        if target_mid is None:
            simulated_pnl += trip.pnl_jpy
            continue

        affected += 1
        direction = 1.0 if trip.open_fill.side == "BUY" else -1.0
        size = trip.open_fill.size
        mid_change = target_mid - trip.open_fill.mid_price
        mid_pnl = mid_change * size * direction
        new_pnl = mid_pnl + trip.spread_captured_jpy
        simulated_pnl += new_pnl

    ppt_orig = original_pnl / total if total else 0
    ppt_sim = simulated_pnl / total if total else 0

    return WhatIfResult(
        scenario=f"hold {min_hold_s:.0f}-{target_hold_s:.0f}s → delay to {target_hold_s:.0f}s",
        total_trips=total,
        affected_trips=affected,
        original_pnl=original_pnl,
        simulated_pnl=simulated_pnl,
        delta_pnl=simulated_pnl - original_pnl,
        pnl_per_trip_orig=ppt_orig,
        pnl_per_trip_sim=ppt_sim,
    )


def _simulate_min_hold(
    matched_trips, timeline, min_hold_s: float
) -> WhatIfResult:
    """
    hold_time < min_hold_sのtripについて、min_hold_s時点のmid_priceでcloseしたと仮定。
    """
    original_pnl = 0.0
    simulated_pnl = 0.0
    affected = 0
    total = 0

    for trip in matched_trips:
        if trip.close_fill is None:
            continue
        total += 1
        original_pnl += trip.pnl_jpy

        if trip.hold_time_s >= min_hold_s:
            simulated_pnl += trip.pnl_jpy
            continue

        open_ts = trip.open_fill.timestamp
        target_mid = _find_mid_at(timeline, open_ts, min_hold_s)

        if target_mid is None:
            simulated_pnl += trip.pnl_jpy
            continue

        affected += 1
        direction = 1.0 if trip.open_fill.side == "BUY" else -1.0
        size = trip.open_fill.size
        mid_change = target_mid - trip.open_fill.mid_price
        mid_pnl = mid_change * size * direction
        new_pnl = mid_pnl + trip.spread_captured_jpy
        simulated_pnl += new_pnl

    ppt_orig = original_pnl / total if total else 0
    ppt_sim = simulated_pnl / total if total else 0

    return WhatIfResult(
        scenario=f"min_hold = {min_hold_s:.0f}s",
        total_trips=total,
        affected_trips=affected,
        original_pnl=original_pnl,
        simulated_pnl=simulated_pnl,
        delta_pnl=simulated_pnl - original_pnl,
        pnl_per_trip_orig=ppt_orig,
        pnl_per_trip_sim=ppt_sim,
    )


def _simulate_early_sl(
    matched_trips, timeline, sl_threshold_s: float, sl_loss_jpy: float = -15.0
) -> WhatIfResult:
    """
    death zone (sl_threshold_s) 到達時にadverseがSL以上なら強制SLする仮想戦略。
    「death zoneで損切りすれば300s+のmean reversionを捨てるが損失は限定される」の検証。
    """
    original_pnl = 0.0
    simulated_pnl = 0.0
    affected = 0
    total = 0

    for trip in matched_trips:
        if trip.close_fill is None:
            continue
        total += 1
        original_pnl += trip.pnl_jpy

        if trip.hold_time_s < sl_threshold_s:
            simulated_pnl += trip.pnl_jpy
            continue

        # sl_threshold_s時点のmid_priceを確認
        open_ts = trip.open_fill.timestamp
        close_ts = trip.close_fill.timestamp
        series = get_mid_price_series(timeline, open_ts, close_ts)

        threshold_mid = None
        for ts, mid in series:
            elapsed = (ts - open_ts).total_seconds()
            if elapsed >= sl_threshold_s:
                threshold_mid = mid
                break

        if threshold_mid is None:
            simulated_pnl += trip.pnl_jpy
            continue

        direction = 1.0 if trip.open_fill.side == "BUY" else -1.0
        size = trip.open_fill.size
        mid_adverse = -(threshold_mid - trip.open_fill.mid_price) * size * direction

        if mid_adverse > abs(sl_loss_jpy) * size:
            # adverseが大きい → SL発動と仮定
            affected += 1
            simulated_pnl += sl_loss_jpy * size
        else:
            # adverseが小さい → 元のP&Lを使用（そのまま保持）
            simulated_pnl += trip.pnl_jpy

    ppt_orig = original_pnl / total if total else 0
    ppt_sim = simulated_pnl / total if total else 0

    return WhatIfResult(
        scenario=f"early_SL at {sl_threshold_s:.0f}s (SL={sl_loss_jpy})",
        total_trips=total,
        affected_trips=affected,
        original_pnl=original_pnl,
        simulated_pnl=simulated_pnl,
        delta_pnl=simulated_pnl - original_pnl,
        pnl_per_trip_orig=ppt_orig,
        pnl_per_trip_sim=ppt_sim,
    )


def run_whatif(date: str):
    print(f"\n{'='*70}")
    print(f"  C-new-3 What-if分析: {date}")
    print(f"{'='*70}")

    trades = load_trades(date)
    metrics = load_metrics(date)
    timeline = build_market_timeline(metrics)
    trips = build_trips(trades)
    order_map = build_order_book(trades)

    matched = [t for t in trips if t.close_fill is not None]
    close_dyn = analyze_close_dynamics(matched, order_map, timeline)

    print(f"  Trips: {len(matched)} matched")
    print(f"  P&L total: {sum(t.pnl_jpy for t in matched):+.2f} JPY")

    # ─── Scenario 1: Minimum hold time ─────────────────
    print("\n--- Scenario 1: 最低保持時間 (close禁止期間) ---")
    print(f"{'scenario':>30}  {'trips':>5}  {'affected':>8}  {'orig_pnl':>10}  {'sim_pnl':>10}  {'delta':>10}  {'ppt_orig':>9}  {'ppt_sim':>8}")
    print("-" * 100)

    for min_hold in [30, 60, 120, 180, 300]:
        r = _simulate_min_hold(matched, timeline, min_hold)
        print(
            f"{r.scenario:>30}  {r.total_trips:>5}  {r.affected_trips:>8}"
            f"  {r.original_pnl:>+10.2f}  {r.simulated_pnl:>+10.2f}  {r.delta_pnl:>+10.2f}"
            f"  {r.pnl_per_trip_orig:>+8.3f}  {r.pnl_per_trip_sim:>+7.3f}"
        )

    # ─── Scenario 2: Death zone delay ─────────────────
    print("\n--- Scenario 2: Death zone trip → 遅延close ---")
    print(f"{'scenario':>40}  {'trips':>5}  {'affected':>8}  {'orig_pnl':>10}  {'sim_pnl':>10}  {'delta':>10}")
    print("-" * 95)

    delay_scenarios = [
        (60, 300), (60, 600), (120, 300), (120, 600),
        (30, 300), (30, 600),
    ]
    for min_s, target_s in delay_scenarios:
        r = _simulate_delayed_close(matched, timeline, min_s, target_s)
        print(
            f"{r.scenario:>40}  {r.total_trips:>5}  {r.affected_trips:>8}"
            f"  {r.original_pnl:>+10.2f}  {r.simulated_pnl:>+10.2f}  {r.delta_pnl:>+10.2f}"
        )

    # ─── Scenario 3: Mid adverse path analysis ─────────────────
    print("\n--- Scenario 3: 保持時間帯別 mid逆行の推移 ---")

    # 全tripのmid_priceパスを追跡して、特定の時点でのadverse平均を計算
    checkpoints = [10, 30, 60, 120, 180, 300, 600]
    # hold_time_bucket別に集計
    buckets = {
        "0-60s": (0, 60),
        "60-300s": (60, 300),
        "300s+": (300, float("inf")),
    }

    for bucket_name, (blo, bhi) in buckets.items():
        bucket_trips = [t for t in matched if blo <= t.hold_time_s < bhi]
        if not bucket_trips:
            continue

        print(f"\n  [{bucket_name}] {len(bucket_trips)} trips, P&L/trip={sum(t.pnl_jpy for t in bucket_trips)/len(bucket_trips):+.3f}")

        for cp in checkpoints:
            adverses = []
            for trip in bucket_trips:
                open_ts = trip.open_fill.timestamp
                # 実際のclose_tsを超えても探索するため、cpまで拡張
                search_end = open_ts + timedelta(seconds=cp + _TIMELINE_BUFFER_S)
                series = get_mid_price_series(timeline, open_ts, search_end)
                direction = 1.0 if trip.open_fill.side == "BUY" else -1.0
                size = trip.open_fill.size

                for ts, mid in series:
                    elapsed = (ts - open_ts).total_seconds()
                    if elapsed >= cp - 1.0:
                        adv = -(mid - trip.open_fill.mid_price) * size * direction
                        adverses.append(adv)
                        break

            if adverses:
                avg_adv = sum(adverses) / len(adverses)
                print(f"    t={cp:>4}s: {len(adverses):>4}/{len(bucket_trips)} trips, avg_adverse={avg_adv:>+8.3f} JPY")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", nargs="+", default=["2026-02-27"])
    args = parser.parse_args()

    for date in args.dates:
        run_whatif(date)
