"""D案・F案の追加検証

1. DSR算出: D案・F案候補の統計的有意性
2. 保守的再検証: spread_capturedを半額(close側のみ捕捉)で再計算
3. TP値の細かいスイープ: D案 TP=3,4,5,6,7,8,10
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
SL_THRESHOLD_JPY = -15.0
TP_SWEEP = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0]
F_PROFIT_TARGET = 5.0
F_MAX_HOLDS = [180, 300, 600]
SPREAD_FACTORS = [1.0, 0.5]  # 1.0 = 全額(楽観), 0.5 = 半額(保守)


def simulate_d(
    trip: Trip,
    timeline: list[MarketState],
    profit_target_jpy: float,
    spread_factor: float,
) -> float:
    """D案: min_hold無効化, TP/SLで早期close。

    spread_factor: spread_capturedにかける係数 (1.0=全額, 0.5=close側のみ捕捉想定)
    """
    if trip.close_fill is None:
        return trip.pnl_jpy

    open_ts = trip.open_fill.timestamp
    close_ts = trip.close_fill.timestamp
    open_mid = trip.open_fill.mid_price
    direction = 1.0 if trip.open_fill.side == "BUY" else -1.0
    size = trip.open_fill.size
    spread_captured = trip.spread_captured_jpy * spread_factor

    for state in timeline:
        if state.timestamp <= open_ts:
            continue
        if state.timestamp > close_ts:
            break

        mid_change = state.mid_price - open_mid
        unrealized = mid_change * size * direction + spread_captured

        if unrealized <= SL_THRESHOLD_JPY:
            return SL_THRESHOLD_JPY
        if unrealized >= profit_target_jpy:
            return unrealized

    # フォールバック: 履歴のP&L (spread_factorで調整)
    if trip.sl_triggered:
        return trip.pnl_jpy  # SLは履歴値そのまま
    # 通常close: spread_capturedの調整分を引く
    spread_adjustment = trip.spread_captured_jpy * (1.0 - spread_factor)
    return trip.pnl_jpy - spread_adjustment


def simulate_f(
    trip: Trip,
    timeline: list[MarketState],
    profit_target_jpy: float,
    max_hold_s: float,
    spread_factor: float,
) -> float:
    """F案: D案 + max_hold強制close。"""
    if trip.close_fill is None:
        return trip.pnl_jpy

    open_ts = trip.open_fill.timestamp
    close_ts = trip.close_fill.timestamp
    open_mid = trip.open_fill.mid_price
    direction = 1.0 if trip.open_fill.side == "BUY" else -1.0
    size = trip.open_fill.size
    spread_captured = trip.spread_captured_jpy * spread_factor

    last_unrealized = 0.0
    last_state = None
    for state in timeline:
        if state.timestamp <= open_ts:
            continue
        if state.timestamp > close_ts:
            break

        elapsed = (state.timestamp - open_ts).total_seconds()
        mid_change = state.mid_price - open_mid
        unrealized = mid_change * size * direction + spread_captured

        if unrealized <= SL_THRESHOLD_JPY:
            return SL_THRESHOLD_JPY
        if unrealized >= profit_target_jpy:
            return unrealized
        if elapsed >= max_hold_s:
            return unrealized

        last_unrealized = unrealized
        last_state = state

    if last_state is not None:
        return last_unrealized
    if trip.sl_triggered:
        return trip.pnl_jpy
    return trip.pnl_jpy - trip.spread_captured_jpy * (1.0 - spread_factor)


def load_all() -> tuple[list[Trip], list[MarketState]]:
    """全日のtripとtimelineを結合して返す。"""
    all_trips: list[Trip] = []
    all_timeline: list[MarketState] = []
    for date in DATES:
        trades = load_trades(date)
        metrics = load_metrics(date)
        if not trades or not metrics:
            continue
        trips = build_trips(trades)
        timeline = build_market_timeline(metrics)
        all_trips.extend(t for t in trips if t.close_fill is not None)
        all_timeline.extend(timeline)
    all_timeline.sort(key=lambda s: s.timestamp)
    return all_trips, all_timeline


def baseline_pnl_list(matched: list[Trip], spread_factor: float) -> list[float]:
    result = []
    for t in matched:
        if t.sl_triggered:
            result.append(t.pnl_jpy)
        else:
            adj = t.spread_captured_jpy * (1.0 - spread_factor)
            result.append(t.pnl_jpy - adj)
    return result


def print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def main() -> None:
    print_section("D案・F案 追加検証")
    print(f"対象日: {DATES[0]} ~ {DATES[-1]}")
    print(f"検証項目:")
    print(f"  1. DSR (統計的有意性)")
    print(f"  2. 保守的再検証 (spread_factor=0.5)")
    print(f"  3. D案 TPスイープ (TP={TP_SWEEP})")
    print()

    matched, timeline = load_all()
    total_trips = len(matched)
    print(f"全trip数: {total_trips}")

    # baselineをspread_factor別に計算
    base_pnls = {sf: baseline_pnl_list(matched, sf) for sf in SPREAD_FACTORS}
    base_totals = {sf: sum(base_pnls[sf]) for sf in SPREAD_FACTORS}

    # ------------------------------------------------------------
    # 検証1+3: D案 TPスイープ (両spread_factor)
    # ------------------------------------------------------------
    print_section("検証1+3: D案 TPスイープ (DSR付き)")
    n_trials = len(TP_SWEEP)  # 比較パラメータ数

    for sf in SPREAD_FACTORS:
        label_sf = "全額(楽観)" if sf == 1.0 else "半額(保守)"
        print()
        print(f"--- spread_factor={sf} ({label_sf}) ---")
        print(f"baseline P&L: {base_totals[sf]:+.0f} JPY (P&L/trip={base_totals[sf]/total_trips:+.2f})")
        print()
        print(f"{'TP':>5}{'P&L':>10}{'P&L/trip':>11}{'差':>10}{'SR':>8}{'DSR':>8}{'有意':>6}")
        print("-" * 58)

        d_results = {}
        for tp in TP_SWEEP:
            pnls = [simulate_d(t, timeline, tp, sf) for t in matched]
            total = sum(pnls)
            per_trip = total / total_trips
            delta = total - base_totals[sf]
            dsr_eval = evaluate_dsr(pnls, N=n_trials)
            mark = "✓" if dsr_eval["significant"] else "-"
            print(
                f"{int(tp):>5}{total:>+10.0f}{per_trip:>+11.2f}{delta:>+10.0f}"
                f"{dsr_eval['sr_best']:>+8.3f}{dsr_eval['dsr']:>8.2f}{mark:>6}"
            )
            d_results[tp] = {"pnl": total, "dsr": dsr_eval}

    # ------------------------------------------------------------
    # 検証2: F案候補のDSR (両spread_factor)
    # ------------------------------------------------------------
    print_section("検証2: F案候補 (TP=5固定, max_hold変化)")
    n_trials_f = len(F_MAX_HOLDS)

    for sf in SPREAD_FACTORS:
        label_sf = "全額(楽観)" if sf == 1.0 else "半額(保守)"
        print()
        print(f"--- spread_factor={sf} ({label_sf}) ---")
        print(f"baseline P&L: {base_totals[sf]:+.0f} JPY")
        print()
        print(f"{'max_hold':>10}{'P&L':>10}{'P&L/trip':>11}{'差':>10}{'SR':>8}{'DSR':>8}{'有意':>6}")
        print("-" * 63)
        for mh in F_MAX_HOLDS:
            pnls = [simulate_f(t, timeline, F_PROFIT_TARGET, float(mh), sf) for t in matched]
            total = sum(pnls)
            per_trip = total / total_trips
            delta = total - base_totals[sf]
            dsr_eval = evaluate_dsr(pnls, N=n_trials_f)
            mark = "✓" if dsr_eval["significant"] else "-"
            print(
                f"{mh:>10}{total:>+10.0f}{per_trip:>+11.2f}{delta:>+10.0f}"
                f"{dsr_eval['sr_best']:>+8.3f}{dsr_eval['dsr']:>8.2f}{mark:>6}"
            )

    # ------------------------------------------------------------
    # 結論
    # ------------------------------------------------------------
    print_section("総合評価")
    print()
    print("【観点1: 楽観 vs 保守 (spread_factor)】")
    print(f"  spread_factor=1.0 (楽観): open+close両方のspread捕捉前提")
    print(f"  spread_factor=0.5 (保守): close時に板を超える可能性を考慮")
    print()
    print("【観点2: DSR (Deflated Sharpe Ratio)】")
    print(f"  DSR ≥ 0.95 = 統計的に有意")
    print(f"  N=試行回数で多重比較バイアスを補正")
    print()
    print("【判定基準】")
    print(f"  spread_factor=0.5 でも黒字 + DSR ≥ 0.95 → 本番投入の根拠あり")
    print(f"  どちらかを満たさない → 追加検証が必要")


if __name__ == "__main__":
    main()
