"""最適パラメータ探索 — D案・F案 TP=1〜2 + SL=-12 の詳細検証

前回の発見:
  - TP=1.0 が最良 (+771 JPY)
  - SL=-12 が最良 (+612 JPY)
  - 組み合わせ未検証
  - F案 (+max_hold) は TP=5 でしか試していない

このスクリプト:
  1. D案 TP × SL クロスマトリクス (最適組み合わせ探索)
  2. F案 TP=1〜2 + SL=-12 + max_hold スイープ
  3. 最良パラメータの詳細分析 (日別、終了理由、DSR)
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
GMO_BASELINE = -864.0
GMO_BASELINE_PER_DAY = {
    "2026-04-02": -245, "2026-04-03": -288, "2026-04-04": +46,
    "2026-04-05": +25, "2026-04-06": -403,
}

DEFAULT_FACTOR = 0.765
SLIPPAGE_JPY = -0.35  # PDF実測

TP_GRID = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
SL_GRID = [-10.0, -12.0, -15.0, -18.0]
F_MAX_HOLDS = [120, 180, 300, 600]


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
) -> tuple[float, str]:
    """D案: min_hold無効化 + early TP/SL."""
    sl_return = sl_trigger + SLIPPAGE_JPY
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


def simulate_f(
    trip: Trip,
    timeline: list[MarketState],
    profit_target: float,
    max_hold_s: float,
    spread_factor: float,
    sl_trigger: float,
) -> tuple[float, str]:
    """F案: D + max_hold."""
    sl_return = sl_trigger + SLIPPAGE_JPY
    if trip.close_fill is None:
        return (trip.pnl_jpy, "fallback_unclosed")

    open_ts = trip.open_fill.timestamp
    close_ts = trip.close_fill.timestamp
    open_mid = trip.open_fill.mid_price
    direction = 1.0 if trip.open_fill.side == "BUY" else -1.0
    size = trip.open_fill.size
    open_spread = trip_open_spread_jpy(trip)
    spread_cap = 2.0 * open_spread * spread_factor

    last_unrealized = 0.0
    last_has = False
    for state in timeline:
        if state.timestamp <= open_ts:
            continue
        if state.timestamp > close_ts:
            break
        elapsed = (state.timestamp - open_ts).total_seconds()
        mid_change = state.mid_price - open_mid
        unrealized = mid_change * size * direction + spread_cap
        if unrealized <= sl_trigger:
            return (sl_return, "early_sl")
        if unrealized >= profit_target:
            return (unrealized, "early_tp")
        if elapsed >= max_hold_s:
            return (unrealized, "max_hold")
        last_unrealized = unrealized
        last_has = True

    if last_has:
        return (last_unrealized, "fallback_last")
    if trip.sl_triggered:
        return (trip.pnl_jpy, "fallback_sl")
    delta = spread_cap - trip.spread_captured_jpy
    return (trip.pnl_jpy + delta, "fallback_normal")


def load_all() -> tuple[list[Trip], list[MarketState], dict[str, tuple[list[Trip], list[MarketState]]]]:
    by_day: dict[str, tuple[list[Trip], list[MarketState]]] = {}
    all_trips: list[Trip] = []
    all_timeline: list[MarketState] = []
    for date in DATES:
        trades = load_trades(date)
        metrics = load_metrics(date)
        if not trades or not metrics:
            continue
        trips = [t for t in build_trips(trades) if t.close_fill is not None]
        timeline = build_market_timeline(metrics)
        by_day[date] = (trips, timeline)
        all_trips.extend(trips)
        all_timeline.extend(timeline)
    all_timeline.sort(key=lambda s: s.timestamp)
    return all_trips, all_timeline, by_day


def print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def main() -> None:
    print_section("最適パラメータ探索")
    print(f"factor={DEFAULT_FACTOR}, slippage={SLIPPAGE_JPY:+.2f}")
    print(f"GMO真値 baseline: {GMO_BASELINE:+.0f} JPY (5日)")

    all_trips, all_timeline, by_day = load_all()
    n_trips = len(all_trips)

    # ------------------------------------------------------------
    # 1. D案 TP × SL マトリクス
    # ------------------------------------------------------------
    print_section("1. D案 TP × SL マトリクス")
    label = "TP/SL"
    header = f"{label:>7}"
    for sl in SL_GRID:
        header += f"{int(sl):>11}"
    print(header)
    print("-" * len(header))

    matrix: dict[tuple[float, float], float] = {}
    for tp in TP_GRID:
        line = f"{tp:>7.1f}"
        for sl in SL_GRID:
            pnls = [simulate_d(t, all_timeline, tp, DEFAULT_FACTOR, sl)[0] for t in all_trips]
            total = sum(pnls)
            matrix[(tp, sl)] = total
            line += f"{total:>+11.0f}"
        print(line)

    best_d = max(matrix.items(), key=lambda kv: kv[1])
    best_tp, best_sl = best_d[0]
    best_d_pnl = best_d[1]
    print()
    print(f"  最良: TP={best_tp:.1f}, SL={int(best_sl)} → P&L={best_d_pnl:+.0f} JPY")
    print(f"  改善: {best_d_pnl - GMO_BASELINE:+.0f} JPY (日次 {(best_d_pnl - GMO_BASELINE)/5:+.0f}/日)")
    print(f"  絶対値: {best_d_pnl/5:+.0f} JPY/日")

    # ------------------------------------------------------------
    # 2. F案 TP=1〜2 + SL=-12 + max_hold スイープ
    # ------------------------------------------------------------
    print_section("2. F案 TP=1〜3 + SL=-12 + max_hold スイープ")
    label2 = "TP/mh"
    header = f"{label2:>6}"
    for mh in F_MAX_HOLDS:
        header += f"{mh:>11}"
    print(header)
    print("-" * len(header))

    f_matrix: dict[tuple[float, int], float] = {}
    for tp in [0.5, 1.0, 1.5, 2.0, 3.0]:
        line = f"{tp:>6.1f}"
        for mh in F_MAX_HOLDS:
            pnls = [simulate_f(t, all_timeline, tp, float(mh), DEFAULT_FACTOR, -12.0)[0] for t in all_trips]
            total = sum(pnls)
            f_matrix[(tp, mh)] = total
            line += f"{total:>+11.0f}"
        print(line)

    best_f = max(f_matrix.items(), key=lambda kv: kv[1])
    best_f_tp, best_f_mh = best_f[0]
    best_f_pnl = best_f[1]
    print()
    print(f"  最良: TP={best_f_tp:.1f}, max_hold={best_f_mh}s → P&L={best_f_pnl:+.0f} JPY")
    print(f"  改善: {best_f_pnl - GMO_BASELINE:+.0f} JPY (日次 {(best_f_pnl - GMO_BASELINE)/5:+.0f}/日)")
    print(f"  絶対値: {best_f_pnl/5:+.0f} JPY/日")

    # ------------------------------------------------------------
    # 3. F案 SL別マトリクス (TP=1.0 固定)
    # ------------------------------------------------------------
    print_section("3. F案 SL × max_hold マトリクス (TP=1.0 固定)")
    label3 = "SL/mh"
    header = f"{label3:>7}"
    for mh in F_MAX_HOLDS:
        header += f"{mh:>11}"
    print(header)
    print("-" * len(header))

    f_sl_matrix: dict[tuple[float, int], float] = {}
    for sl in [-10.0, -12.0, -15.0, -18.0]:
        line = f"{int(sl):>7}"
        for mh in F_MAX_HOLDS:
            pnls = [simulate_f(t, all_timeline, 1.0, float(mh), DEFAULT_FACTOR, sl)[0] for t in all_trips]
            total = sum(pnls)
            f_sl_matrix[(sl, mh)] = total
            line += f"{total:>+11.0f}"
        print(line)

    best_f_sl = max(f_sl_matrix.items(), key=lambda kv: kv[1])
    best_sl_val, best_mh_val = best_f_sl[0]
    best_f_sl_pnl = best_f_sl[1]
    print()
    print(f"  TP=1.0 固定での最良: SL={int(best_sl_val)}, max_hold={best_mh_val}s → P&L={best_f_sl_pnl:+.0f}")

    # ------------------------------------------------------------
    # 4. 最良パラメータの日別ブレークダウン
    # ------------------------------------------------------------
    print_section(f"4. 最良パラメータ詳細 (D: TP={best_tp}, SL={int(best_sl)})")
    print(f"{'日付':<12}{'GMO真値':>11}{'D案':>11}{'差':>10}{'P&L/trip':>11}")
    print("-" * 55)
    for date in DATES:
        if date not in by_day:
            continue
        trips, timeline = by_day[date]
        pnls = [simulate_d(t, timeline, best_tp, DEFAULT_FACTOR, best_sl)[0] for t in trips]
        total = sum(pnls)
        per_trip = total / len(trips) if trips else 0
        gmo = GMO_BASELINE_PER_DAY.get(date, 0)
        diff = total - gmo
        marker = " ⚠️" if diff < 0 else ""
        print(f"{date:<12}{gmo:>+11.0f}{total:>+11.0f}{diff:>+10.0f}{per_trip:>+11.2f}{marker}")

    print()
    print(f"--- 最良 F案 (TP={best_f_tp}, max={best_f_mh}, SL=-12) ---")
    print(f"{'日付':<12}{'GMO真値':>11}{'F案':>11}{'差':>10}{'P&L/trip':>11}")
    print("-" * 55)
    for date in DATES:
        if date not in by_day:
            continue
        trips, timeline = by_day[date]
        pnls = [simulate_f(t, timeline, best_f_tp, float(best_f_mh), DEFAULT_FACTOR, -12.0)[0] for t in trips]
        total = sum(pnls)
        per_trip = total / len(trips) if trips else 0
        gmo = GMO_BASELINE_PER_DAY.get(date, 0)
        diff = total - gmo
        marker = " ⚠️" if diff < 0 else ""
        print(f"{date:<12}{gmo:>+11.0f}{total:>+11.0f}{diff:>+10.0f}{per_trip:>+11.2f}{marker}")

    # ------------------------------------------------------------
    # 5. 最良パラメータの終了理由内訳
    # ------------------------------------------------------------
    print_section(f"5. 終了理由内訳 (D: TP={best_tp}, SL={int(best_sl)})")
    by_reason_d: dict[str, list[float]] = {}
    for trip in all_trips:
        pnl, reason = simulate_d(trip, all_timeline, best_tp, DEFAULT_FACTOR, best_sl)
        by_reason_d.setdefault(reason, []).append(pnl)
    print(f"{'理由':<22}{'件数':>8}{'P&L合計':>12}{'avg':>10}{'割合':>8}")
    print("-" * 60)
    for reason in ["early_tp", "early_sl", "fallback_normal", "fallback_sl", "fallback_unclosed"]:
        pnls = by_reason_d.get(reason, [])
        if not pnls:
            continue
        total = sum(pnls)
        avg = total / len(pnls)
        pct = len(pnls) / n_trips * 100
        print(f"{reason:<22}{len(pnls):>8}{total:>+12.0f}{avg:>+10.2f}{pct:>7.1f}%")

    print()
    print(f"--- F案 ({best_f_tp}, max={best_f_mh}, SL=-12) ---")
    by_reason_f: dict[str, list[float]] = {}
    for trip in all_trips:
        pnl, reason = simulate_f(trip, all_timeline, best_f_tp, float(best_f_mh), DEFAULT_FACTOR, -12.0)
        by_reason_f.setdefault(reason, []).append(pnl)
    print(f"{'理由':<22}{'件数':>8}{'P&L合計':>12}{'avg':>10}{'割合':>8}")
    print("-" * 60)
    for reason in ["early_tp", "early_sl", "max_hold", "fallback_last", "fallback_normal", "fallback_sl"]:
        pnls = by_reason_f.get(reason, [])
        if not pnls:
            continue
        total = sum(pnls)
        avg = total / len(pnls)
        pct = len(pnls) / n_trips * 100
        print(f"{reason:<22}{len(pnls):>8}{total:>+12.0f}{avg:>+10.2f}{pct:>7.1f}%")

    # ------------------------------------------------------------
    # 6. DSR
    # ------------------------------------------------------------
    print_section("6. 最良パラメータのDSR")
    n_trials = len(TP_GRID) * len(SL_GRID)  # 比較数
    pnls_d = [simulate_d(t, all_timeline, best_tp, DEFAULT_FACTOR, best_sl)[0] for t in all_trips]
    dsr_d = evaluate_dsr(pnls_d, N=n_trials)
    print(f"  D案 (TP={best_tp}, SL={int(best_sl)}):")
    print(f"    P&L={best_d_pnl:+.0f}, SR={dsr_d['sr_best']:+.3f}, DSR={dsr_d['dsr']:.2f}")
    print(f"    {'✓ 統計的に有意' if dsr_d['significant'] else '- 未有意'}")

    n_trials_f = 5 * len(F_MAX_HOLDS)
    pnls_f = [simulate_f(t, all_timeline, best_f_tp, float(best_f_mh), DEFAULT_FACTOR, -12.0)[0] for t in all_trips]
    dsr_f = evaluate_dsr(pnls_f, N=n_trials_f)
    print(f"  F案 (TP={best_f_tp}, max={best_f_mh}, SL=-12):")
    print(f"    P&L={best_f_pnl:+.0f}, SR={dsr_f['sr_best']:+.3f}, DSR={dsr_f['dsr']:.2f}")
    print(f"    {'✓ 統計的に有意' if dsr_f['significant'] else '- 未有意'}")

    # ------------------------------------------------------------
    # 7. 統合判定
    # ------------------------------------------------------------
    print_section("7. 統合判定")
    print()
    print(f"  ★ D案 最良: TP={best_tp}, SL={int(best_sl)}")
    print(f"      P&L: {best_d_pnl:+.0f} JPY/5日 ({best_d_pnl/5:+.0f}/日)")
    print(f"      改善: {best_d_pnl - GMO_BASELINE:+.0f} ({(best_d_pnl - GMO_BASELINE)/5:+.0f}/日)")
    print(f"      DSR: {dsr_d['dsr']:.2f}")
    print()
    print(f"  ★ F案 最良: TP={best_f_tp}, max_hold={best_f_mh}s, SL=-12")
    print(f"      P&L: {best_f_pnl:+.0f} JPY/5日 ({best_f_pnl/5:+.0f}/日)")
    print(f"      改善: {best_f_pnl - GMO_BASELINE:+.0f} ({(best_f_pnl - GMO_BASELINE)/5:+.0f}/日)")
    print(f"      DSR: {dsr_f['dsr']:.2f}")
    print()
    if best_f_pnl > best_d_pnl:
        print(f"  推奨: F案 (max_hold で更なる安定化)")
    else:
        print(f"  推奨: D案 (シンプル & 最良)")


if __name__ == "__main__":
    main()
