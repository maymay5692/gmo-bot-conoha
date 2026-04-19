"""現実版バックテスト: 実測 spread_factor でD案・F案を再評価

spread_capture 実測分析の結果:
  - 通常close trip の avg_open_spread = +2.374 JPY
  - 通常close trip の avg_close_spread = +0.946 JPY
  - close/open ratio = 0.40 (全日で安定)
  - 実効 spread_factor = (1 + 0.40) / 2 = 0.70

検証モデル:
  A. fixed_factor = 1.00 (楽観, 参考)
  B. fixed_factor = 0.70 (実測値)
  C. fixed_factor = 0.50 (保守, 参考)
  D. time_dependent (早期closeほど ratio 低下)
     - close_ratio(hold_s) = 0.40 * min(1.0, hold_s / 180)
     - hold_s=30  → ratio=0.067, factor=0.533
     - hold_s=60  → ratio=0.133, factor=0.567
     - hold_s=180 → ratio=0.400, factor=0.700
     - hold_s=300 → ratio=0.400, factor=0.700

シミュレーション式:
  close_spread_eff = open_spread * close_ratio(elapsed_s)
  spread_captured_eff = open_spread + close_spread_eff
  unrealized = mid_change * size * dir + spread_captured_eff
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
TP_SWEEP = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
F_MAX_HOLDS = [180, 300, 600]
BASE_CLOSE_RATIO = 0.40  # 実測値
REFERENCE_HOLD_S = 180  # 実測の時の平均hold付近


def trip_open_spread_jpy(trip: Trip) -> float:
    """open側の favorable spread (JPY)。"""
    size = trip.open_fill.size
    mid = trip.open_fill.mid_price
    price = trip.open_fill.price
    if trip.open_fill.side == "BUY":
        return (mid - price) * size
    return (price - mid) * size


def effective_spread_captured(
    open_spread: float,
    elapsed_s: float,
    model: str,
    fixed_factor: float = 0.70,
) -> float:
    """モデル別に実効 spread_captured を計算。

    total = open_spread + close_spread
    close_spread = open_spread * close_ratio
    """
    if model == "fixed":
        # 固定 factor: total_capture = 2 * open_spread * factor
        return 2.0 * open_spread * fixed_factor
    if model == "time_dependent":
        ratio = BASE_CLOSE_RATIO * min(1.0, elapsed_s / REFERENCE_HOLD_S)
        return open_spread * (1.0 + ratio)
    raise ValueError(f"Unknown model: {model}")


def simulate_d_realistic(
    trip: Trip,
    timeline: list[MarketState],
    profit_target_jpy: float,
    model: str,
    fixed_factor: float = 0.70,
) -> float:
    """D案 (min_hold=0, TP/SL) を現実的 spread_capture で再計算。"""
    if trip.close_fill is None:
        return trip.pnl_jpy

    open_ts = trip.open_fill.timestamp
    close_ts = trip.close_fill.timestamp
    open_mid = trip.open_fill.mid_price
    direction = 1.0 if trip.open_fill.side == "BUY" else -1.0
    size = trip.open_fill.size
    open_spread = trip_open_spread_jpy(trip)

    for state in timeline:
        if state.timestamp <= open_ts:
            continue
        if state.timestamp > close_ts:
            break

        elapsed_s = (state.timestamp - open_ts).total_seconds()
        mid_change = state.mid_price - open_mid
        spread_cap = effective_spread_captured(open_spread, elapsed_s, model, fixed_factor)
        unrealized = mid_change * size * direction + spread_cap

        if unrealized <= SL_THRESHOLD_JPY:
            return SL_THRESHOLD_JPY
        if unrealized >= profit_target_jpy:
            return unrealized

    # フォールバック: 履歴のP&L 調整
    if trip.sl_triggered:
        return trip.pnl_jpy
    # 通常close: 履歴 spread_captured を実効値に置き換え
    hold_s = trip.hold_time_s
    eff_total = effective_spread_captured(open_spread, hold_s, model, fixed_factor)
    delta = eff_total - trip.spread_captured_jpy
    return trip.pnl_jpy + delta


def simulate_f_realistic(
    trip: Trip,
    timeline: list[MarketState],
    profit_target_jpy: float,
    max_hold_s: float,
    model: str,
    fixed_factor: float = 0.70,
) -> float:
    """F案 (D + max_hold) を現実的 spread_capture で再計算。"""
    if trip.close_fill is None:
        return trip.pnl_jpy

    open_ts = trip.open_fill.timestamp
    close_ts = trip.close_fill.timestamp
    open_mid = trip.open_fill.mid_price
    direction = 1.0 if trip.open_fill.side == "BUY" else -1.0
    size = trip.open_fill.size
    open_spread = trip_open_spread_jpy(trip)

    last_unrealized = 0.0
    last_has_state = False
    for state in timeline:
        if state.timestamp <= open_ts:
            continue
        if state.timestamp > close_ts:
            break

        elapsed_s = (state.timestamp - open_ts).total_seconds()
        mid_change = state.mid_price - open_mid
        spread_cap = effective_spread_captured(open_spread, elapsed_s, model, fixed_factor)
        unrealized = mid_change * size * direction + spread_cap

        if unrealized <= SL_THRESHOLD_JPY:
            return SL_THRESHOLD_JPY
        if unrealized >= profit_target_jpy:
            return unrealized
        if elapsed_s >= max_hold_s:
            return unrealized

        last_unrealized = unrealized
        last_has_state = True

    if last_has_state:
        return last_unrealized
    if trip.sl_triggered:
        return trip.pnl_jpy
    hold_s = trip.hold_time_s
    eff_total = effective_spread_captured(open_spread, hold_s, model, fixed_factor)
    delta = eff_total - trip.spread_captured_jpy
    return trip.pnl_jpy + delta


def load_all() -> tuple[list[Trip], list[MarketState]]:
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


def baseline_pnl_adjusted(matched: list[Trip], model: str, fixed_factor: float = 0.70) -> list[float]:
    """baseline を実効 spread_factor で再計算。"""
    result = []
    for t in matched:
        if t.sl_triggered:
            result.append(t.pnl_jpy)
            continue
        open_spread = trip_open_spread_jpy(t)
        hold_s = t.hold_time_s
        eff_total = effective_spread_captured(open_spread, hold_s, model, fixed_factor)
        delta = eff_total - t.spread_captured_jpy
        result.append(t.pnl_jpy + delta)
    return result


def print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def main() -> None:
    print_section("現実版バックテスト: 実測 spread_factor でD案・F案を再評価")
    print(f"対象日: {DATES[0]} ~ {DATES[-1]}")
    print(f"実測 close/open ratio: {BASE_CLOSE_RATIO}")
    print(f"基準 hold time: {REFERENCE_HOLD_S}s")
    print()

    matched, timeline = load_all()
    total_trips = len(matched)
    print(f"全trip数: {total_trips}")

    # ------------------------------------------------------------
    # 各モデルで D案 TPスイープ
    # ------------------------------------------------------------
    models = [
        ("fixed", 1.00, "楽観 factor=1.00"),
        ("fixed", 0.70, "実測 factor=0.70"),
        ("fixed", 0.50, "保守 factor=0.50"),
        ("time_dependent", 0.70, "時間依存 (早期close→低ratio)"),
    ]

    for model, fixed_factor, label in models:
        print_section(f"D案 TPスイープ — {label}")
        base_pnls = baseline_pnl_adjusted(matched, model, fixed_factor)
        base_total = sum(base_pnls)
        base_per_trip = base_total / total_trips
        print(f"baseline (min_hold=180s): {base_total:+.0f} JPY (P&L/trip={base_per_trip:+.2f})")
        print()
        print(f"{'TP':>5}{'P&L':>10}{'P&L/trip':>11}{'差':>10}{'SR':>8}{'DSR':>8}{'有意':>6}")
        print("-" * 58)
        n_trials = len(TP_SWEEP)
        best_tp = None
        best_pnl = float("-inf")
        for tp in TP_SWEEP:
            pnls = [simulate_d_realistic(t, timeline, tp, model, fixed_factor) for t in matched]
            total = sum(pnls)
            per_trip = total / total_trips
            delta = total - base_total
            dsr_eval = evaluate_dsr(pnls, N=n_trials)
            mark = "✓" if dsr_eval["significant"] else "-"
            print(
                f"{int(tp):>5}{total:>+10.0f}{per_trip:>+11.2f}{delta:>+10.0f}"
                f"{dsr_eval['sr_best']:>+8.3f}{dsr_eval['dsr']:>8.2f}{mark:>6}"
            )
            if total > best_pnl:
                best_pnl = total
                best_tp = tp
        print(f"\n→ 最良: TP={int(best_tp)} で P&L={best_pnl:+.0f} JPY")

    # ------------------------------------------------------------
    # 実測モデルで F案 max_hold スイープ
    # ------------------------------------------------------------
    print_section("F案 max_hold スイープ — 実測 factor=0.70")
    base_pnls = baseline_pnl_adjusted(matched, "fixed", 0.70)
    base_total = sum(base_pnls)
    print(f"baseline: {base_total:+.0f} JPY")
    print()
    print(f"{'TP':>4}{'max_hold':>10}{'P&L':>10}{'P&L/trip':>11}{'差':>10}{'SR':>8}{'DSR':>8}{'有意':>6}")
    print("-" * 67)
    n_trials = len(F_MAX_HOLDS) * 3  # TP × max_hold 全組み合わせ
    for tp in [3.0, 5.0, 7.0]:
        for mh in F_MAX_HOLDS:
            pnls = [simulate_f_realistic(t, timeline, tp, float(mh), "fixed", 0.70) for t in matched]
            total = sum(pnls)
            per_trip = total / total_trips
            delta = total - base_total
            dsr_eval = evaluate_dsr(pnls, N=n_trials)
            mark = "✓" if dsr_eval["significant"] else "-"
            print(
                f"{int(tp):>4}{mh:>10}{total:>+10.0f}{per_trip:>+11.2f}{delta:>+10.0f}"
                f"{dsr_eval['sr_best']:>+8.3f}{dsr_eval['dsr']:>8.2f}{mark:>6}"
            )

    # ------------------------------------------------------------
    # 時間依存モデルで F案
    # ------------------------------------------------------------
    print_section("F案 max_hold スイープ — 時間依存モデル (最もリアル)")
    base_pnls = baseline_pnl_adjusted(matched, "time_dependent", 0.70)
    base_total = sum(base_pnls)
    print(f"baseline: {base_total:+.0f} JPY")
    print()
    print(f"{'TP':>4}{'max_hold':>10}{'P&L':>10}{'P&L/trip':>11}{'差':>10}{'SR':>8}{'DSR':>8}{'有意':>6}")
    print("-" * 67)
    for tp in [3.0, 5.0, 7.0]:
        for mh in F_MAX_HOLDS:
            pnls = [simulate_f_realistic(t, timeline, tp, float(mh), "time_dependent", 0.70) for t in matched]
            total = sum(pnls)
            per_trip = total / total_trips
            delta = total - base_total
            dsr_eval = evaluate_dsr(pnls, N=n_trials)
            mark = "✓" if dsr_eval["significant"] else "-"
            print(
                f"{int(tp):>4}{mh:>10}{total:>+10.0f}{per_trip:>+11.2f}{delta:>+10.0f}"
                f"{dsr_eval['sr_best']:>+8.3f}{dsr_eval['dsr']:>8.2f}{mark:>6}"
            )

    # ------------------------------------------------------------
    # 総合評価
    # ------------------------------------------------------------
    print_section("総合評価")
    print()
    print("【モデル別の期待 P&L 範囲 (5日, 688 trips)】")
    print()
    print("  楽観   (factor=1.00): 大幅黒字, DSR 有意")
    print("  実測   (factor=0.70): 現実的な期待値")
    print("  時間依存            : 最もリアル (早期closeでは spread 捕捉が下がる)")
    print("  保守   (factor=0.50): 最悪シナリオ")
    print()
    print("【最終判定】")
    print("  時間依存モデルの最良パターンが黒字 + 日次プラス 維持なら")
    print("  → D/F案は実装価値あり")
    print("  DSR ≥ 0.95 を満たすなら統計的にも強い根拠")


if __name__ == "__main__":
    main()
