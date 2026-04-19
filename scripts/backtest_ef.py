"""E案・F案バックテスト

E案: max_hold追加 (min_hold=180s維持 + max_hold で強制close)
  - 一定時間以上保持しているtripを強制closeしてSL発動を回避する
  - max_hold > 180s (min_hold以上)

F案: D+E複合 (min_hold削除 + max_hold追加 + 早期TP/SL)
  - D案 (min_hold=0, TP=5, SL=-15) に max_hold cap を追加
  - max_hold時刻までにTP/SLどちらも発動しなければ強制close

シミュレーション:
  - mid_price timelineを前進してP&Lを計算
  - 各案の終了条件で close
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

from backtester.data_loader import Trip, build_trips, load_metrics, load_trades
from backtester.market_replay import MarketState, build_market_timeline

DATES = ["2026-04-02", "2026-04-03", "2026-04-04", "2026-04-05", "2026-04-06"]
SL_THRESHOLD_JPY = -15.0
F_PROFIT_TARGET = 5.0  # D案の最良値付近

E_MAX_HOLDS = [240, 300, 600, 900, 1800]  # min_hold(180s)以上
F_MAX_HOLDS = [60, 120, 180, 300, 600]    # min_hold制約なし


def simulate_e(
    trip: Trip,
    timeline: list[MarketState],
    max_hold_s: float,
) -> tuple[float, str, float]:
    """E案: baseline挙動 + max_hold強制close。

    - hold_time <= max_hold: baseline P&Lをそのまま使用
    - hold_time > max_hold: max_hold時点のmid_priceで強制close
    """
    if trip.close_fill is None:
        return (trip.pnl_jpy, "fallback_unclosed", trip.hold_time_s)

    # 実際の hold_time が max_hold 以下ならbaseline通り
    if trip.hold_time_s <= max_hold_s:
        reason = "baseline_sl" if trip.sl_triggered else "baseline_close"
        return (trip.pnl_jpy, reason, trip.hold_time_s)

    # max_hold を超えるtrip → max_hold時点のmid_priceで強制close
    open_ts = trip.open_fill.timestamp
    open_mid = trip.open_fill.mid_price
    direction = 1.0 if trip.open_fill.side == "BUY" else -1.0
    size = trip.open_fill.size

    target_state = None
    for state in timeline:
        if state.timestamp <= open_ts:
            continue
        elapsed = (state.timestamp - open_ts).total_seconds()
        if elapsed >= max_hold_s:
            target_state = state
            break

    if target_state is None:
        # timelineに該当時刻がない → baselineにフォールバック
        return (trip.pnl_jpy, "fallback_no_data", trip.hold_time_s)

    mid_change = target_state.mid_price - open_mid
    forced_pnl = mid_change * size * direction + trip.spread_captured_jpy
    elapsed = (target_state.timestamp - open_ts).total_seconds()
    return (forced_pnl, "forced_close", elapsed)


def simulate_f(
    trip: Trip,
    timeline: list[MarketState],
    max_hold_s: float,
    profit_target_jpy: float,
) -> tuple[float, str, float]:
    """F案: D案(min_hold=0, TP/SL) + max_hold強制close。

    - mid_priceを前進
    - SL/TP/max_hold の最初に達した条件でclose
    """
    if trip.close_fill is None:
        return (trip.pnl_jpy, "fallback_unclosed", trip.hold_time_s)

    open_ts = trip.open_fill.timestamp
    close_ts = trip.close_fill.timestamp
    open_mid = trip.open_fill.mid_price
    direction = 1.0 if trip.open_fill.side == "BUY" else -1.0
    size = trip.open_fill.size
    spread_captured = trip.spread_captured_jpy

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
            return (SL_THRESHOLD_JPY, "early_sl", elapsed)
        if unrealized >= profit_target_jpy:
            return (unrealized, "early_tp", elapsed)
        if elapsed >= max_hold_s:
            return (unrealized, "max_hold_close", elapsed)

        last_state = state

    # timeline尽きた → 最後の状態 or 履歴フォールバック
    if last_state is not None:
        elapsed = (last_state.timestamp - open_ts).total_seconds()
        mid_change = last_state.mid_price - open_mid
        forced = mid_change * size * direction + spread_captured
        return (forced, "fallback_last_state", elapsed)
    return (trip.pnl_jpy, "fallback_actual", trip.hold_time_s)


def aggregate_variant(matched: list[Trip], simulator, **kwargs) -> dict:
    """全tripに対してsimulatorを実行して集計。"""
    pnl = 0.0
    reasons: dict[str, int] = {}
    hold_sum = 0.0
    for trip in matched:
        p, reason, hold_s = simulator(trip, **kwargs)
        pnl += p
        hold_sum += hold_s
        reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "pnl": pnl,
        "reasons": reasons,
        "avg_hold_s": hold_sum / len(matched) if matched else 0.0,
    }


def run_day(date: str) -> dict:
    trades = load_trades(date)
    metrics = load_metrics(date)
    if not trades or not metrics:
        return {"date": date, "skipped": True}

    trips = build_trips(trades)
    timeline = build_market_timeline(metrics)
    matched = [t for t in trips if t.close_fill is not None]

    baseline_pnl = sum(t.pnl_jpy for t in matched)
    baseline_sl_count = sum(1 for t in matched if t.sl_triggered)

    e_results = {
        mh: aggregate_variant(matched, simulate_e, timeline=timeline, max_hold_s=float(mh))
        for mh in E_MAX_HOLDS
    }
    f_results = {
        mh: aggregate_variant(
            matched, simulate_f, timeline=timeline,
            max_hold_s=float(mh), profit_target_jpy=F_PROFIT_TARGET,
        )
        for mh in F_MAX_HOLDS
    }

    return {
        "date": date,
        "trips": len(matched),
        "baseline_pnl": baseline_pnl,
        "baseline_sl_count": baseline_sl_count,
        "e": e_results,
        "f": f_results,
    }


def print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def main() -> None:
    print_section("E案・F案バックテスト")
    print(f"対象日: {DATES[0]} ~ {DATES[-1]}")
    print(f"E案 max_hold: {E_MAX_HOLDS} s")
    print(f"F案 max_hold: {F_MAX_HOLDS} s (TP={F_PROFIT_TARGET}, SL={SL_THRESHOLD_JPY})")

    all_results = [run_day(d) for d in DATES]
    valid = [r for r in all_results if not r.get("skipped")]
    if not valid:
        print("有効データなし")
        return

    total_trips = sum(r["trips"] for r in valid)
    total_baseline_pnl = sum(r["baseline_pnl"] for r in valid)
    total_baseline_sl = sum(r["baseline_sl_count"] for r in valid)

    # E案: 日別
    print_section("E案 (max_hold追加, baseline + 強制close)")
    header = f"{'日付':<12}{'Trips':>7}{'Baseline':>11}"
    for mh in E_MAX_HOLDS:
        header += f"{'mh=' + str(mh):>10}"
    print(header)
    print("-" * len(header))
    e_totals = {mh: 0.0 for mh in E_MAX_HOLDS}
    for r in valid:
        line = f"{r['date']:<12}{r['trips']:>7}{r['baseline_pnl']:>+11.0f}"
        for mh in E_MAX_HOLDS:
            v = r["e"][mh]
            line += f"{v['pnl']:>+10.0f}"
            e_totals[mh] += v["pnl"]
        print(line)
    print("-" * len(header))
    line = f"{'合計':<12}{total_trips:>7}{total_baseline_pnl:>+11.0f}"
    for mh in E_MAX_HOLDS:
        line += f"{e_totals[mh]:>+10.0f}"
    print(line)

    # F案: 日別
    print_section(f"F案 (min_hold=0 + TP={int(F_PROFIT_TARGET)}/SL={int(SL_THRESHOLD_JPY)} + max_hold)")
    header = f"{'日付':<12}{'Trips':>7}{'Baseline':>11}"
    for mh in F_MAX_HOLDS:
        header += f"{'mh=' + str(mh):>10}"
    print(header)
    print("-" * len(header))
    f_totals = {mh: 0.0 for mh in F_MAX_HOLDS}
    for r in valid:
        line = f"{r['date']:<12}{r['trips']:>7}{r['baseline_pnl']:>+11.0f}"
        for mh in F_MAX_HOLDS:
            v = r["f"][mh]
            line += f"{v['pnl']:>+10.0f}"
            f_totals[mh] += v["pnl"]
        print(line)
    print("-" * len(header))
    line = f"{'合計':<12}{total_trips:>7}{total_baseline_pnl:>+11.0f}"
    for mh in F_MAX_HOLDS:
        line += f"{f_totals[mh]:>+10.0f}"
    print(line)

    # 詳細サマリー
    print_section("詳細サマリー (5日合計)")
    base_per_trip = total_baseline_pnl / total_trips if total_trips else 0.0
    print(f"{'パターン':<32}{'P&L':>10}{'P&L/trip':>11}{'差':>10}")
    print("-" * 63)
    print(f"{'baseline (min_hold=180s)':<32}{total_baseline_pnl:>+10.0f}{base_per_trip:>+11.2f}{'-':>10}")

    print()
    for mh in E_MAX_HOLDS:
        per_trip = e_totals[mh] / total_trips
        delta = e_totals[mh] - total_baseline_pnl
        label = f"E: max_hold={mh}s"
        print(f"{label:<32}{e_totals[mh]:>+10.0f}{per_trip:>+11.2f}{delta:>+10.0f}")

    print()
    for mh in F_MAX_HOLDS:
        per_trip = f_totals[mh] / total_trips
        delta = f_totals[mh] - total_baseline_pnl
        label = f"F: no-mh + TP=5 + max={mh}s"
        print(f"{label:<32}{f_totals[mh]:>+10.0f}{per_trip:>+11.2f}{delta:>+10.0f}")

    # 終了理由内訳 (5日合計)
    print_section("F案 終了理由内訳 (5日合計)")
    print(f"{'max_hold':<12}{'early_sl':>10}{'early_tp':>10}{'max_hold_close':>16}{'fallback':>12}")
    print("-" * 60)
    for mh in F_MAX_HOLDS:
        agg = {"early_sl": 0, "early_tp": 0, "max_hold_close": 0, "fallback_last_state": 0, "fallback_actual": 0, "fallback_unclosed": 0}
        for r in valid:
            for k, v in r["f"][mh]["reasons"].items():
                agg[k] = agg.get(k, 0) + v
        fb = agg.get("fallback_last_state", 0) + agg.get("fallback_actual", 0) + agg.get("fallback_unclosed", 0)
        print(f"{mh:<12}{agg['early_sl']:>10}{agg['early_tp']:>10}{agg['max_hold_close']:>16}{fb:>12}")

    # 結論
    print_section("評価")
    best_e_mh = max(E_MAX_HOLDS, key=lambda mh: e_totals[mh])
    best_f_mh = max(F_MAX_HOLDS, key=lambda mh: f_totals[mh])
    print(f"E案最良: max_hold={best_e_mh}s → P&L={e_totals[best_e_mh]:+.0f} JPY (baseline比 {e_totals[best_e_mh] - total_baseline_pnl:+.0f})")
    print(f"F案最良: max_hold={best_f_mh}s → P&L={f_totals[best_f_mh]:+.0f} JPY (baseline比 {f_totals[best_f_mh] - total_baseline_pnl:+.0f})")
    print()
    print("(参考) D案最良: TP=10 → P&L=+2,970 JPY (baseline比 +3,477)")


if __name__ == "__main__":
    main()
