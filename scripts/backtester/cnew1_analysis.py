"""C-new-1: hold_time根本調査 - close cancel × hold_time クロス分析。

cancel回数がhold_timeを延長する因果関係を定量化し、
各cancel帯×hold_time帯のP&L構造を可視化する。
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from backtester.data_loader import build_order_book, build_trips, load_metrics, load_trades
from backtester.market_replay import build_market_timeline
from backtester.trip_analyzer import analyze_close_dynamics


def _hold_bucket(s: float) -> str:
    if s < 30:
        return "0-30s"
    if s < 60:
        return "30-60s"
    if s < 120:
        return "60-120s"
    if s < 300:
        return "120-300s"
    if s < 600:
        return "300-600s"
    return ">600s"


def _cancel_bucket(c: int) -> str:
    if c == 0:
        return "0"
    if c <= 2:
        return "1-2"
    if c <= 5:
        return "3-5"
    if c <= 10:
        return "6-10"
    return "11+"


def run_cnew1(date: str):
    print(f"\n{'='*70}")
    print(f"  C-new-1: hold_time根本調査 - {date}")
    print(f"{'='*70}")

    trades = load_trades(date)
    metrics = load_metrics(date)
    timeline = build_market_timeline(metrics)
    trips = build_trips(trades)
    order_map = build_order_book(trades)

    matched = [t for t in trips if t.close_fill is not None]
    close_dyn = analyze_close_dynamics(matched, order_map, timeline)

    # trip index → cancel details
    cancel_by_idx = {}
    for d in close_dyn["details"]:
        cancel_by_idx[d["trip_idx"]] = d

    # ─── 1. Cancel回数 × Hold_time クロス集計 ─────────────────
    print("\n--- 1. Cancel回数 × Hold_time クロス集計 (P&L/trip) ---")

    cancel_buckets = ["0", "1-2", "3-5", "6-10", "11+"]
    hold_buckets = ["0-30s", "30-60s", "60-120s", "120-300s", "300-600s", ">600s"]

    cross: dict[str, dict[str, list[float]]] = {
        cb: {hb: [] for hb in hold_buckets}
        for cb in cancel_buckets
    }
    cross_count: dict[str, dict[str, int]] = {
        cb: {hb: 0 for hb in hold_buckets}
        for cb in cancel_buckets
    }

    for idx, trip in enumerate(matched):
        detail = cancel_by_idx.get(idx)
        if detail is None:
            continue
        cb = _cancel_bucket(detail["cancel_count"])
        hb = _hold_bucket(trip.hold_time_s)
        cross[cb][hb].append(trip.pnl_jpy)
        cross_count[cb][hb] += 1

    # 表示
    header = f"{'cancel':>8}"
    for hb in hold_buckets:
        header += f"  {hb:>10}"
    header += f"  {'total':>8}"
    print(header)
    print("-" * len(header))

    for cb in cancel_buckets:
        row = f"{cb:>8}"
        total_pnl = []
        for hb in hold_buckets:
            vals = cross[cb][hb]
            if vals:
                mean = sum(vals) / len(vals)
                row += f"  {mean:>7.2f}({len(vals):>2})"
                total_pnl.extend(vals)
            else:
                row += f"  {'':>10}"
        if total_pnl:
            row += f"  {sum(total_pnl)/len(total_pnl):>5.2f}({len(total_pnl)})"
        print(row)

    # ─── 2. Cancel回数とHold_timeの相関 ─────────────────
    print("\n--- 2. Cancel回数 → Hold_time (平均) ---")
    cancel_to_hold: dict[str, list[float]] = defaultdict(list)
    cancel_to_pnl: dict[str, list[float]] = defaultdict(list)
    cancel_to_adverse: dict[str, list[float]] = defaultdict(list)
    cancel_to_spread: dict[str, list[float]] = defaultdict(list)

    for idx, trip in enumerate(matched):
        detail = cancel_by_idx.get(idx)
        if detail is None:
            continue
        cb = _cancel_bucket(detail["cancel_count"])
        cancel_to_hold[cb].append(trip.hold_time_s)
        cancel_to_pnl[cb].append(trip.pnl_jpy)
        cancel_to_adverse[cb].append(trip.mid_adverse_jpy)
        cancel_to_spread[cb].append(trip.spread_captured_jpy)

    print(f"{'cancel':>8}  {'count':>6}  {'hold_avg':>9}  {'hold_med':>9}  {'pnl/trip':>9}  {'adverse':>9}  {'spread':>8}  {'win%':>6}")
    print("-" * 80)
    for cb in cancel_buckets:
        holds = cancel_to_hold.get(cb, [])
        pnls = cancel_to_pnl.get(cb, [])
        advs = cancel_to_adverse.get(cb, [])
        sprs = cancel_to_spread.get(cb, [])
        if not holds:
            continue
        sorted_h = sorted(holds)
        med = sorted_h[len(sorted_h) // 2]
        wins = sum(1 for p in pnls if p > 0)
        print(
            f"{cb:>8}  {len(holds):>6}  {sum(holds)/len(holds):>8.1f}s  {med:>8.1f}s"
            f"  {sum(pnls)/len(pnls):>+8.3f}  {sum(advs)/len(advs):>+8.3f}"
            f"  {sum(sprs)/len(sprs):>7.3f}  {100*wins/len(pnls):>5.1f}%"
        )

    # ─── 3. Close所要時間の分析 ─────────────────
    print("\n--- 3. Close所要時間 → P&L ---")
    close_time_buckets = [
        ("0-10s", 0, 10), ("10-30s", 10, 30), ("30-60s", 30, 60),
        ("60-120s", 60, 120), ("120-300s", 120, 300), (">300s", 300, float("inf")),
    ]

    for label, lo, hi in close_time_buckets:
        relevant = []
        for idx, trip in enumerate(matched):
            detail = cancel_by_idx.get(idx)
            if detail is None:
                continue
            ct = detail["total_close_time_s"]
            if lo <= ct < hi:
                relevant.append(trip)
        if not relevant:
            continue
        pnl_mean = sum(t.pnl_jpy for t in relevant) / len(relevant)
        adv_mean = sum(t.mid_adverse_jpy for t in relevant) / len(relevant)
        spr_mean = sum(t.spread_captured_jpy for t in relevant) / len(relevant)
        hold_mean = sum(t.hold_time_s for t in relevant) / len(relevant)
        wins = sum(1 for t in relevant if t.pnl_jpy > 0)
        print(
            f"  {label:>8}: {len(relevant):>4}件  P&L={pnl_mean:>+7.3f}"
            f"  adv={adv_mean:>+7.3f}  spr={spr_mean:>6.3f}"
            f"  hold={hold_mean:>7.1f}s  win={100*wins/len(relevant):.1f}%"
        )

    # ─── 4. 価格調整方向の分析 ─────────────────
    print("\n--- 4. Close価格調整の方向分析 ---")
    total_adjustments = 0
    favorable = 0  # close方向に有利
    unfavorable = 0

    for idx, trip in enumerate(matched):
        detail = cancel_by_idx.get(idx)
        if detail is None:
            continue
        for adj in detail["price_adjustments"]:
            total_adjustments += 1
            # BUY open → SELL close: 価格下降=有利（より低い=market adverseに追随）
            # SELL open → BUY close: 価格上昇=有利（同上）
            if trip.open_fill.side == "BUY":
                # close is SELL, price down = chasing market = unfavorable
                if adj < 0:
                    unfavorable += 1
                else:
                    favorable += 1
            else:
                # close is BUY, price up = chasing market = unfavorable
                if adj > 0:
                    unfavorable += 1
                else:
                    favorable += 1

    if total_adjustments > 0:
        print(f"  Total adjustments: {total_adjustments}")
        print(f"  Market追随(不利方向): {unfavorable} ({100*unfavorable/total_adjustments:.1f}%)")
        print(f"  Mean reversion(有利方向): {favorable} ({100*favorable/total_adjustments:.1f}%)")

    # ─── 5. サマリー ─────────────────
    print(f"\n--- 5. サマリー ({date}) ---")
    total = len(matched)
    total_pnl = sum(t.pnl_jpy for t in matched)
    avg_hold = sum(t.hold_time_s for t in matched) / total if total else 0

    # cancel帯別のP&L寄与
    print(f"  Total trips: {total}")
    print(f"  P&L total: {total_pnl:+.2f} JPY")
    print(f"  P&L/trip: {total_pnl/total:+.3f}" if total else "")
    print(f"  Avg hold_time: {avg_hold:.1f}s")
    print(f"  Avg cancel: {close_dyn['avg_cancel_cycles']:.2f}")

    print("\n  Cancel帯別P&L寄与:")
    for cb in cancel_buckets:
        pnls = cancel_to_pnl.get(cb, [])
        if pnls:
            pnl_sum = sum(pnls)
            pct = pnl_sum / abs(total_pnl) * 100 if total_pnl != 0 else 0
            print(f"    {cb:>5}: {len(pnls):>4}件  P&L={pnl_sum:>+8.2f}  ({pct:>+6.1f}%)")

    # cancel 0-2 vs 3+ のP&L比較
    low_cancel_pnl = cancel_to_pnl.get("0", []) + cancel_to_pnl.get("1-2", [])
    high_cancel_pnl = []
    for cb in ["3-5", "6-10", "11+"]:
        high_cancel_pnl.extend(cancel_to_pnl.get(cb, []))

    if low_cancel_pnl and high_cancel_pnl:
        print(f"\n  ★ Cancel 0-2回: {len(low_cancel_pnl)}件, P&L/trip={sum(low_cancel_pnl)/len(low_cancel_pnl):+.3f}")
        print(f"  ★ Cancel 3+回:  {len(high_cancel_pnl)}件, P&L/trip={sum(high_cancel_pnl)/len(high_cancel_pnl):+.3f}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", nargs="+", default=["2026-02-27"])
    args = parser.parse_args()

    for date in args.dates:
        run_cnew1(date)
