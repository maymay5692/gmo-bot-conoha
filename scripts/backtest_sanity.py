"""補正版バックテスト — D案の詳細 sanity check

補正版 (factor=0.765, SL=-15.35) を使って:
  1. D案 TPスイープを細かく (1.0 〜 15.0)
  2. 日別の安定性確認
  3. spread_factor 感度分析 (0.60, 0.70, 0.765, 0.85)
  4. SL_TRIGGER 感度分析 (-12, -15, -18, -20)
  5. 各 TP の終了理由内訳 (early_sl/early_tp/fallback)
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

from backtester.data_loader import Trip, build_trips, load_metrics, load_trades
from backtester.dsr import evaluate_dsr
from backtester.market_replay import MarketState, build_market_timeline

DATES = ["2026-04-02", "2026-04-03", "2026-04-04", "2026-04-05", "2026-04-06"]
GMO_BASELINE = -864.0  # 5日合計、PDF真値
GMO_BASELINE_PER_DAY = {
    "2026-04-02": -245,
    "2026-04-03": -288,
    "2026-04-04": +46,
    "2026-04-05": +25,
    "2026-04-06": -403,
}

DEFAULT_FACTOR = 0.765
DEFAULT_SL_TRIGGER = -15.0
DEFAULT_SL_RETURN = -15.35  # PDF実測 slippage 込み

TP_SWEEP_FINE = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0, 10.0, 15.0]
SPREAD_FACTORS = [0.60, 0.70, 0.765, 0.85]
SL_TRIGGERS = [(-12.0, -12.35), (-15.0, -15.35), (-18.0, -18.35), (-20.0, -20.35)]


def trip_open_spread_jpy(trip: Trip) -> float:
    size = trip.open_fill.size
    mid = trip.open_fill.mid_price
    price = trip.open_fill.price
    if trip.open_fill.side == "BUY":
        return (mid - price) * size
    return (price - mid) * size


def simulate_d(
    trip: Trip,
    timeline: list[MarketState],
    profit_target: float,
    spread_factor: float,
    sl_trigger: float,
    sl_return: float,
) -> tuple[float, str]:
    """D案 simulator. (pnl, exit_reason) を返す。"""
    if trip.close_fill is None:
        return (trip.pnl_jpy, "fallback_unclosed")

    open_ts = trip.open_fill.timestamp
    close_ts = trip.close_fill.timestamp
    open_mid = trip.open_fill.mid_price
    direction = 1.0 if trip.open_fill.side == "BUY" else -1.0
    size = trip.open_fill.size
    open_spread = trip_open_spread_jpy(trip)
    spread_cap = 2.0 * open_spread * spread_factor

    for state in timeline:
        if state.timestamp <= open_ts:
            continue
        if state.timestamp > close_ts:
            break
        mid_change = state.mid_price - open_mid
        unrealized = mid_change * size * direction + spread_cap
        if unrealized <= sl_trigger:
            return (sl_return, "early_sl")
        if unrealized >= profit_target:
            return (unrealized, "early_tp")

    if trip.sl_triggered:
        return (trip.pnl_jpy, "fallback_sl")
    delta = spread_cap - trip.spread_captured_jpy
    return (trip.pnl_jpy + delta, "fallback_normal")


def load_all() -> dict[str, tuple[list[Trip], list[MarketState]]]:
    """日別に trip と timeline を返す。"""
    result: dict[str, tuple[list[Trip], list[MarketState]]] = {}
    for date in DATES:
        trades = load_trades(date)
        metrics = load_metrics(date)
        if not trades or not metrics:
            continue
        trips = [t for t in build_trips(trades) if t.close_fill is not None]
        timeline = build_market_timeline(metrics)
        result[date] = (trips, timeline)
    return result


def print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def main() -> None:
    print_section("補正版 D案 詳細 sanity check")
    print(f"factor={DEFAULT_FACTOR}, SL_trigger={DEFAULT_SL_TRIGGER}, SL_return={DEFAULT_SL_RETURN}")
    print(f"GMO真値 baseline: {GMO_BASELINE:+.0f} JPY (5日)")

    by_day = load_all()
    all_trips: list[Trip] = []
    all_timeline: list[MarketState] = []
    for date in DATES:
        if date in by_day:
            all_trips.extend(by_day[date][0])
            all_timeline.extend(by_day[date][1])
    all_timeline.sort(key=lambda s: s.timestamp)
    n_trips = len(all_trips)

    # ------------------------------------------------------------
    # 1. TP fine sweep
    # ------------------------------------------------------------
    print_section("1. TP 詳細スイープ (1.0 - 15.0)")
    print(f"{'TP':>6}{'P&L':>10}{'P&L/trip':>11}{'改善':>10}{'SR':>8}{'DSR':>8}{'有意':>6}")
    print("-" * 59)
    n_trials = len(TP_SWEEP_FINE)
    sweep_results = []
    for tp in TP_SWEEP_FINE:
        pnls = []
        reasons = {}
        for trip in all_trips:
            pnl, reason = simulate_d(trip, all_timeline, tp, DEFAULT_FACTOR, DEFAULT_SL_TRIGGER, DEFAULT_SL_RETURN)
            pnls.append(pnl)
            reasons[reason] = reasons.get(reason, 0) + 1
        total = sum(pnls)
        per_trip = total / n_trips
        delta = total - GMO_BASELINE
        dsr_eval = evaluate_dsr(pnls, N=n_trials)
        mark = "✓" if dsr_eval["significant"] else "-"
        print(
            f"{tp:>6.1f}{total:>+10.0f}{per_trip:>+11.2f}{delta:>+10.0f}"
            f"{dsr_eval['sr_best']:>+8.3f}{dsr_eval['dsr']:>8.2f}{mark:>6}"
        )
        sweep_results.append((tp, total, dsr_eval, reasons))

    best_tp, best_pnl, best_dsr, best_reasons = max(sweep_results, key=lambda x: x[1])
    print()
    print(f"  最良: TP={best_tp:.1f} → P&L={best_pnl:+.0f}, DSR={best_dsr['dsr']:.2f}")

    # ------------------------------------------------------------
    # 2. 日別ブレークダウン (TP=4 を使用)
    # ------------------------------------------------------------
    print_section("2. 日別ブレークダウン (TP=4.0)")
    print(f"{'日付':<12}{'GMO真値':>11}{'D案 TP=4':>12}{'差':>10}{'P&L/trip':>11}")
    print("-" * 56)
    for date in DATES:
        if date not in by_day:
            continue
        trips, timeline = by_day[date]
        pnls = [simulate_d(t, timeline, 4.0, DEFAULT_FACTOR, DEFAULT_SL_TRIGGER, DEFAULT_SL_RETURN)[0] for t in trips]
        total = sum(pnls)
        per_trip = total / len(trips)
        gmo = GMO_BASELINE_PER_DAY.get(date, 0)
        diff = total - gmo
        print(f"{date:<12}{gmo:>+11.0f}{total:>+12.0f}{diff:>+10.0f}{per_trip:>+11.2f}")

    # ------------------------------------------------------------
    # 3. spread_factor 感度分析 (TP=4 固定)
    # ------------------------------------------------------------
    print_section("3. spread_factor 感度分析 (TP=4.0)")
    print(f"{'factor':>10}{'P&L':>10}{'P&L/trip':>11}{'改善':>10}")
    print("-" * 41)
    for sf in SPREAD_FACTORS:
        pnls = [
            simulate_d(t, all_timeline, 4.0, sf, DEFAULT_SL_TRIGGER, DEFAULT_SL_RETURN)[0]
            for t in all_trips
        ]
        total = sum(pnls)
        per_trip = total / n_trips
        delta = total - GMO_BASELINE
        marker = " ←PDF実測" if abs(sf - DEFAULT_FACTOR) < 0.01 else ""
        print(f"{sf:>10.3f}{total:>+10.0f}{per_trip:>+11.2f}{delta:>+10.0f}{marker}")

    # ------------------------------------------------------------
    # 4. SL_TRIGGER 感度分析 (TP=4 固定)
    # ------------------------------------------------------------
    print_section("4. SL_TRIGGER 感度分析 (TP=4.0, factor=0.765)")
    print(f"{'SL':>10}{'P&L':>10}{'P&L/trip':>11}{'改善':>10}")
    print("-" * 41)
    for sl_trig, sl_ret in SL_TRIGGERS:
        pnls = [
            simulate_d(t, all_timeline, 4.0, DEFAULT_FACTOR, sl_trig, sl_ret)[0]
            for t in all_trips
        ]
        total = sum(pnls)
        per_trip = total / n_trips
        delta = total - GMO_BASELINE
        marker = " ←現状" if abs(sl_trig - DEFAULT_SL_TRIGGER) < 0.01 else ""
        print(f"{sl_trig:>10.0f}{total:>+10.0f}{per_trip:>+11.2f}{delta:>+10.0f}{marker}")

    # ------------------------------------------------------------
    # 5. 終了理由内訳 (TP=4 で詳細)
    # ------------------------------------------------------------
    print_section("5. TP=4.0 の終了理由内訳")
    pnls_with_reason = [
        simulate_d(t, all_timeline, 4.0, DEFAULT_FACTOR, DEFAULT_SL_TRIGGER, DEFAULT_SL_RETURN)
        for t in all_trips
    ]
    by_reason: dict[str, list[float]] = {}
    for pnl, reason in pnls_with_reason:
        by_reason.setdefault(reason, []).append(pnl)

    print(f"{'理由':<22}{'件数':>8}{'P&L合計':>12}{'avg':>10}{'割合':>8}")
    print("-" * 60)
    for reason in ["early_tp", "early_sl", "fallback_normal", "fallback_sl", "fallback_unclosed"]:
        pnls = by_reason.get(reason, [])
        if not pnls:
            continue
        total = sum(pnls)
        avg = total / len(pnls)
        pct = len(pnls) / n_trips * 100
        print(f"{reason:<22}{len(pnls):>8}{total:>+12.0f}{avg:>+10.2f}{pct:>7.1f}%")

    # ------------------------------------------------------------
    # 6. 統合判定
    # ------------------------------------------------------------
    print_section("6. 統合判定")
    print()
    print("【観点1: TP感度】")
    tps_above_zero = [r for r in sweep_results if r[1] > 0]
    print(f"  P&L > 0 となる TP数: {len(tps_above_zero)}/{len(sweep_results)}")
    print(f"  TP={best_tp:.1f} で最良 P&L={best_pnl:+.0f}")
    range_pnls = [r[1] for r in sweep_results if 2.0 <= r[0] <= 8.0]
    print(f"  TP=2-8 のレンジ P&L: {min(range_pnls):+.0f} 〜 {max(range_pnls):+.0f}")
    print()
    print("【観点2: 日別安定性】")
    print("  全日で改善があれば安定. 1日でも改善なしなら要注意")
    print()
    print("【観点3: spread_factor 感度】")
    pnls_60 = sum(simulate_d(t, all_timeline, 4.0, 0.60, DEFAULT_SL_TRIGGER, DEFAULT_SL_RETURN)[0] for t in all_trips)
    pnls_85 = sum(simulate_d(t, all_timeline, 4.0, 0.85, DEFAULT_SL_TRIGGER, DEFAULT_SL_RETURN)[0] for t in all_trips)
    print(f"  factor=0.60 (悲観): {pnls_60:+.0f} JPY")
    print(f"  factor=0.85 (楽観): {pnls_85:+.0f} JPY")
    print(f"  範囲: {pnls_85 - pnls_60:.0f} JPY")
    if pnls_60 > GMO_BASELINE:
        print(f"  → 悲観前提でも baseline ({GMO_BASELINE:+.0f}) より良い")
    else:
        print(f"  → 悲観前提では baseline 未満")
    print()
    print("【観点4: SL_TRIGGER 感度】")
    print(f"  SL=-15 (現状) が最適か、緩和する余地があるか確認")


if __name__ == "__main__":
    main()
