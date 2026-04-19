"""D案バックテスト: min_hold無効化シミュレーション

仮説: min_hold=180sがmean reversionを待つ間に逆行を放置し、SL発動を増やしている。
   min_hold=0なら早期closeで損失を限定でき、トータルP&Lが改善するはず。

シミュレーション方法:
  各tripのopen時刻からmid_price timelineを前進し、
  unrealized_pnl = mid_change * size * direction + spread_captured を計算。
  以下のいずれかで close:
    1. unrealized_pnl <= -15 JPY  → 即SL (現状のSL閾値で発動)
    2. unrealized_pnl >= profit_target → 利確close
    3. 履歴のclose時刻に到達 → 履歴のP&Lを採用 (フォールバック)

複数のprofit_targetでスイープし、baselineと比較する。
"""
from __future__ import annotations

import sys
from pathlib import Path

# backtester モジュールをimport可能に
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

from backtester.data_loader import Trip, build_trips, load_metrics, load_trades
from backtester.market_replay import MarketState, build_market_timeline

DATES = ["2026-04-02", "2026-04-03", "2026-04-04", "2026-04-05", "2026-04-06"]
SL_THRESHOLD_JPY = -15.0
PROFIT_TARGETS = [1.0, 2.0, 5.0, 10.0]


def simulate_no_min_hold(
    trip: Trip,
    timeline: list[MarketState],
    profit_target_jpy: float,
) -> tuple[float, str, float]:
    """min_hold無効化下でtripを再シミュレート。

    Returns:
        (simulated_pnl_jpy, exit_reason, exit_hold_time_s)
        exit_reason: "early_sl" | "early_tp" | "fallback_actual"
    """
    if trip.close_fill is None:
        return (trip.pnl_jpy, "fallback_actual", trip.hold_time_s)

    open_ts = trip.open_fill.timestamp
    close_ts = trip.close_fill.timestamp
    open_mid = trip.open_fill.mid_price
    direction = 1.0 if trip.open_fill.side == "BUY" else -1.0
    size = trip.open_fill.size
    spread_captured = trip.spread_captured_jpy

    # open_ts < ts <= close_ts のmid_priceを順に評価
    for state in timeline:
        if state.timestamp <= open_ts:
            continue
        if state.timestamp > close_ts:
            break

        mid_change = state.mid_price - open_mid
        unrealized = mid_change * size * direction + spread_captured

        if unrealized <= SL_THRESHOLD_JPY:
            elapsed = (state.timestamp - open_ts).total_seconds()
            return (SL_THRESHOLD_JPY, "early_sl", elapsed)
        if unrealized >= profit_target_jpy:
            elapsed = (state.timestamp - open_ts).total_seconds()
            return (unrealized, "early_tp", elapsed)

    # フォールバック: 履歴のP&L
    return (trip.pnl_jpy, "fallback_actual", trip.hold_time_s)


def run_day(date: str) -> dict:
    """1日分のデータを読み込み、baseline + 各profit_targetでシミュレート。"""
    trades = load_trades(date)
    metrics = load_metrics(date)
    if not trades or not metrics:
        return {"date": date, "skipped": True}

    trips = build_trips(trades)
    timeline = build_market_timeline(metrics)
    matched = [t for t in trips if t.close_fill is not None]

    baseline_pnl = sum(t.pnl_jpy for t in matched)
    baseline_sl_count = sum(1 for t in matched if t.sl_triggered)

    results = {
        "date": date,
        "trips": len(matched),
        "baseline_pnl": baseline_pnl,
        "baseline_sl_count": baseline_sl_count,
        "variants": {},
    }

    for tp in PROFIT_TARGETS:
        sim_pnl = 0.0
        sl_count = 0
        tp_count = 0
        fallback_count = 0
        hold_time_sum = 0.0
        for trip in matched:
            pnl, reason, hold_s = simulate_no_min_hold(trip, timeline, tp)
            sim_pnl += pnl
            hold_time_sum += hold_s
            if reason == "early_sl":
                sl_count += 1
            elif reason == "early_tp":
                tp_count += 1
            else:
                fallback_count += 1
        results["variants"][tp] = {
            "pnl": sim_pnl,
            "sl_count": sl_count,
            "tp_count": tp_count,
            "fallback_count": fallback_count,
            "avg_hold_s": hold_time_sum / len(matched) if matched else 0.0,
        }

    return results


def main() -> None:
    print("=" * 78)
    print("D案バックテスト: min_hold無効化シミュレーション")
    print("=" * 78)
    print(f"対象日: {DATES[0]} ~ {DATES[-1]}")
    print(f"SL閾値: {SL_THRESHOLD_JPY} JPY")
    print(f"Profit targets: {PROFIT_TARGETS}")
    print()

    all_results = [run_day(d) for d in DATES]
    valid = [r for r in all_results if not r.get("skipped")]
    if not valid:
        print("有効なデータがありません")
        return

    # 日別結果
    print("=" * 78)
    print("日別結果")
    print("=" * 78)
    header = f"{'日付':<12}{'Trips':>7}{'Baseline':>12}{'SL数':>7}"
    for tp in PROFIT_TARGETS:
        header += f"{'TP=' + str(int(tp)):>11}"
    print(header)
    print("-" * len(header))

    totals = {
        "trips": 0,
        "baseline_pnl": 0.0,
        "baseline_sl_count": 0,
        "variants": {tp: {"pnl": 0.0, "sl_count": 0, "tp_count": 0, "fallback_count": 0} for tp in PROFIT_TARGETS},
    }

    for r in valid:
        line = f"{r['date']:<12}{r['trips']:>7}{r['baseline_pnl']:>+12.0f}{r['baseline_sl_count']:>7}"
        for tp in PROFIT_TARGETS:
            v = r["variants"][tp]
            line += f"{v['pnl']:>+11.0f}"
        print(line)
        totals["trips"] += r["trips"]
        totals["baseline_pnl"] += r["baseline_pnl"]
        totals["baseline_sl_count"] += r["baseline_sl_count"]
        for tp in PROFIT_TARGETS:
            for k in ("pnl", "sl_count", "tp_count", "fallback_count"):
                totals["variants"][tp][k] += r["variants"][tp][k]

    print("-" * len(header))
    line = f"{'合計':<12}{totals['trips']:>7}{totals['baseline_pnl']:>+12.0f}{totals['baseline_sl_count']:>7}"
    for tp in PROFIT_TARGETS:
        line += f"{totals['variants'][tp]['pnl']:>+11.0f}"
    print(line)
    print()

    # 詳細サマリー
    print("=" * 78)
    print("詳細サマリー (5日合計)")
    print("=" * 78)
    print(f"{'パターン':<25}{'P&L':>10}{'P&L/trip':>12}{'SL':>6}{'TP':>6}{'Fallback':>10}{'差':>10}")
    print("-" * 79)
    base_pnl = totals["baseline_pnl"]
    base_per_trip = base_pnl / totals["trips"] if totals["trips"] else 0.0
    print(f"{'baseline (min_hold=180s)':<25}{base_pnl:>+10.0f}{base_per_trip:>+12.2f}{totals['baseline_sl_count']:>6}{'-':>6}{'-':>10}{'-':>10}")
    for tp in PROFIT_TARGETS:
        v = totals["variants"][tp]
        per_trip = v["pnl"] / totals["trips"] if totals["trips"] else 0.0
        delta = v["pnl"] - base_pnl
        sign = "+" if delta >= 0 else ""
        label = f"D: no-min_hold TP={int(tp)}"
        print(f"{label:<25}{v['pnl']:>+10.0f}{per_trip:>+12.2f}{v['sl_count']:>6}{v['tp_count']:>6}{v['fallback_count']:>10}{sign}{delta:>+9.0f}")
    print()

    # 結論
    print("=" * 78)
    print("評価")
    print("=" * 78)
    best_tp = max(PROFIT_TARGETS, key=lambda tp: totals["variants"][tp]["pnl"])
    best_v = totals["variants"][best_tp]
    best_delta = best_v["pnl"] - base_pnl
    print(f"最良: TP={int(best_tp)} JPY → P&L={best_v['pnl']:+.0f} JPY (baseline比 {best_delta:+.0f} JPY)")
    if best_v["pnl"] > 0:
        print("→ D案で黒字化の可能性あり")
    elif best_delta > 0:
        print(f"→ D案で改善するが黒字化せず ({best_delta:+.0f} JPY 改善)")
    else:
        print(f"→ D案は逆効果 ({best_delta:+.0f} JPY 悪化)")


if __name__ == "__main__":
    main()
