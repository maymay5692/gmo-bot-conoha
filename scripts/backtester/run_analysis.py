"""Phase C分析エントリポイント。

使用例:
  python scripts/backtester/run_analysis.py --date 2026-02-27 --analysis hold_time
  python scripts/backtester/run_analysis.py --date 2026-02-27 --analysis time_filter --utc-start 8 --utc-end 14
  python scripts/backtester/run_analysis.py --date 2026-02-27 --analysis ev_sim --alpha 0.5
  python scripts/backtester/run_analysis.py --date 2026-02-27 --analysis all
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from backtester.data_loader import (  # noqa: E402
    build_order_book,
    build_trips,
    load_metrics,
    load_trades,
)
from backtester.decision_sim import (  # noqa: E402
    EVParams,
    analyze_alpha_sensitivity,
    simulate_level_selection,
)
from backtester.market_replay import build_market_timeline  # noqa: E402
from backtester.metrics_sim import (  # noqa: E402
    aggregate_metrics_by_hour,
    aggregate_trips_by_hour,
    calc_calibration_factors,
    estimate_non_trading_hours,
    format_summary,
)
from backtester.trip_analyzer import (  # noqa: E402
    analyze_by_group,
    analyze_close_dynamics,
    analyze_hold_time_vs_pnl,
    calc_time_filter_impact,
)
from backtester.dsr import calc_sharpe_ratio, evaluate_dsr, format_dsr_line  # noqa: E402
from backtester.vol_regime import (  # noqa: E402
    analyze_by_vol_regime,
    calc_vol_filter_impact,
    classify_vol_regime,
    get_trip_regime_label,
)
from backtester.min_hold_sim import simulate_min_hold_sweep  # noqa: E402
from backtester.close_fill_sim import (  # noqa: E402
    aggregate_results as close_fill_aggregate,
    print_sweep_grid,
    run_close_fill_sweep,
)
from backtester.dvol_fetcher import fetch_dvol  # noqa: E402
from backtester.dvol_regime import (  # noqa: E402
    analyze_by_dvol_regime,
    calc_dvol_filter_impact,
    calc_dvol_zscore,
    classify_dvol_regime,
    _get_dvol_regime_at,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# テーブル表示ヘルパー
# ---------------------------------------------------------------------------

def _print_table(headers: list[str], rows: list[list[str]], col_widths: list[int]) -> None:
    """固定幅テーブル表示。"""
    header_line = "  ".join(h.rjust(w) for h, w in zip(headers, col_widths))
    print(header_line)
    print("-" * len(header_line))
    for row in rows:
        print("  ".join(str(v).rjust(w) for v, w in zip(row, col_widths)))


# ---------------------------------------------------------------------------
# 分析関数
# ---------------------------------------------------------------------------

def analysis_hold_time(trades, metrics, trips, timeline):
    """hold_time帯別P&L分析。"""
    print("\n=== hold_time別P&L分析 ===")
    rows = analyze_hold_time_vs_pnl(trips)

    headers = ["hold_bucket", "count", "pnl_sum", "pnl_mean", "adverse", "spread", "win_rate", "SL"]
    widths = [12, 6, 10, 9, 9, 9, 8, 4]
    table_rows = []
    for r in rows:
        if r["count"] == 0:
            continue
        table_rows.append([
            r["hold_bucket"],
            str(r["count"]),
            f"{r['pnl_sum']:.2f}",
            f"{r['pnl_mean']:.3f}",
            f"{r['adverse_mean']:.3f}",
            f"{r['spread_mean']:.3f}",
            f"{r['win_rate']:.1%}",
            str(r["sl_count"]),
        ])

    _print_table(headers, table_rows, widths)
    total_pnl = sum(r["pnl_sum"] for r in rows)
    total_count = sum(r["count"] for r in rows)
    print(f"\n  Total: {total_count}件  P&L合計={total_pnl:.2f} JPY")

    print("\n=== level別集計 ===")
    level_rows = analyze_by_group(trips, group_by="level")
    headers2 = ["level", "count", "pnl_sum", "pnl_mean", "adverse", "hold_mean", "win_rate", "SL"]
    widths2 = [6, 6, 10, 9, 9, 10, 8, 4]
    table_rows2 = []
    for r in level_rows:
        table_rows2.append([
            r["group"],
            str(r["count"]),
            f"{r['pnl_sum']:.2f}",
            f"{r['pnl_mean']:.3f}",
            f"{r['adverse_mean']:.3f}",
            f"{r['hold_mean_s']:.1f}s",
            f"{r['win_rate']:.1%}",
            str(r["sl_count"]),
        ])
    _print_table(headers2, table_rows2, widths2)

    print("\n=== UTC時間帯別集計 ===")
    hour_rows = analyze_by_group(trips, group_by="utc_hour")
    headers3 = ["UTC_hour", "count", "pnl_sum", "pnl_mean", "win_rate"]
    widths3 = [10, 6, 10, 9, 8]
    table_rows3 = []
    for r in hour_rows:
        table_rows3.append([
            r["group"],
            str(r["count"]),
            f"{r['pnl_sum']:.2f}",
            f"{r['pnl_mean']:.3f}",
            f"{r['win_rate']:.1%}",
        ])
    _print_table(headers3, table_rows3, widths3)

    return {"hold_time": rows, "level": level_rows, "utc_hour": hour_rows}


def analysis_time_filter(trades, metrics, trips, timeline, utc_start: int, utc_end: int):
    """時間フィルタ変更の影響。"""
    print(f"\n=== 時間フィルタ影響: UTC {utc_start:02d}-{utc_end:02d} ===")
    result = calc_time_filter_impact(trips, utc_start=utc_start, utc_end=utc_end)
    inc = result["included"]
    exc = result["excluded"]
    total = result["total"]

    print(f"  Total trips: {total['count']}件  P&L={total['pnl_sum']:.2f} JPY")
    print(f"  Included (filter ON):  {inc['count']}件  P&L={inc['pnl_sum']:.2f}  mean={inc['pnl_mean']:.3f}")
    print(f"  Excluded (filter OFF): {exc['count']}件  P&L={exc['pnl_sum']:.2f}  mean={exc['pnl_mean']:.3f}")

    if total["count"] > 0:
        overall_mean = total["pnl_sum"] / total["count"]
        if inc["count"] > 0:
            improvement = inc["pnl_mean"] - overall_mean
            print(f"  フィルタ適用でのpnl/trip変化: {improvement:+.3f} JPY/trip")

    print("\n=== 比較: 複数のフィルタ設定 ===")
    filters = [(0, 6), (0, 8), (3, 7), (6, 12), (8, 14), (14, 20), (20, 24)]
    headers = ["filter", "count", "pnl_sum", "pnl_mean"]
    widths = [12, 6, 10, 9]
    table_rows = []
    for fs, fe in filters:
        r = calc_time_filter_impact(trips, utc_start=fs, utc_end=fe)
        inc_r = r["included"]
        table_rows.append([
            f"UTC {fs:02d}-{fe:02d}",
            str(inc_r["count"]),
            f"{inc_r['pnl_sum']:.2f}",
            f"{inc_r['pnl_mean']:.3f}" if inc_r["count"] > 0 else "N/A",
        ])
    _print_table(headers, table_rows, widths)

    # --- DSR 判定 ---
    # 各フィルタのP&LサブセットからSRを計算し、ベストSRでDSR判定
    matched = [t for t in trips if t.close_fill is not None]

    def _in_hour_range(hour: int, start: int, end: int) -> bool:
        if start <= end:
            return start <= hour < end
        return hour >= start or hour < end

    if matched:
        best_sr = float("-inf")
        best_pnl_list: list[float] = []
        for fs, fe in filters:
            r = calc_time_filter_impact(trips, utc_start=fs, utc_end=fe)
            inc = r["included"]
            if inc["count"] >= 2:
                # そのフィルタで含まれるトリップのP&Lリスト
                filtered_trips = [
                    t for t in matched
                    if _in_hour_range(t.open_fill.timestamp.hour, fs, fe)
                ]
                pnl_list = [t.pnl_jpy for t in filtered_trips]
                sr = calc_sharpe_ratio(pnl_list)
                if sr > best_sr:
                    best_sr = sr
                    best_pnl_list = pnl_list
        if best_pnl_list:
            dsr_result = evaluate_dsr(best_pnl_list, N=len(filters))
            print(f"\n  {format_dsr_line(dsr=dsr_result['dsr'], N=dsr_result['N'], T=dsr_result['T'], sr_best=dsr_result['sr_best'], significant=dsr_result['significant'])}")

    return result


def analysis_ev_sim(trades, metrics, trips, timeline, alpha: float):
    """EVパラメータ変更でのlevel選択比較。"""
    print(f"\n=== EV式比較 (alpha={alpha}) ===")

    base_params = EVParams(alpha=0.7, ev_formula="current")
    base_results = simulate_level_selection(trades, metrics, base_params)
    total = len(base_results)
    if total == 0:
        print("  ORDER_SENTイベントなし")
        return

    # formula比較
    print(f"  ORDER_SENTタイミング: {total}件")
    print()
    for formula in ["current", "sqrt_t", "hold_time", "mean_reversion"]:
        params = EVParams(alpha=alpha, ev_formula=formula)
        results = simulate_level_selection(trades, metrics, params)
        changed = sum(1 for r in results if r["changed"])
        avg_ev = sum(r["sim_ev"] for r in results) / len(results) if results else 0
        print(
            f"  {formula:20s}: level変化={changed}/{total} ({100*changed/total:.1f}%)"
            f"  avg_ev={avg_ev:.2f}"
        )

    # alpha感度分析
    print("\n=== alpha感度分析 ===")
    alphas = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    sens = analyze_alpha_sensitivity(trades, metrics, alphas)

    headers = ["alpha", "avg_ev", "change%", "L22%", "L23%", "L24%", "L25%"]
    widths = [7, 10, 8, 7, 7, 7, 7]
    table_rows = []
    for r in sens:
        table_rows.append([
            f"{r['alpha']:.1f}",
            f"{r['avg_ev']:.2f}",
            f"{r['change_rate']:.1%}",
            f"{r.get('level_22_pct', 0):.1%}",
            f"{r.get('level_23_pct', 0):.1%}",
            f"{r.get('level_24_pct', 0):.1%}",
            f"{r.get('level_25_pct', 0):.1%}",
        ])
    _print_table(headers, table_rows, widths)

    # --- DSR 判定 (近似) ---
    # 注意: ev_simは理論EVが変わるだけで実P&Lは同一のため、
    # 厳密なDSR適用ではなく参考値として表示
    matched = [t for t in trips if t.close_fill is not None]
    if matched:
        pnl_list = [t.pnl_jpy for t in matched]
        dsr_result = evaluate_dsr(pnl_list, N=len(alphas))
        print(f"\n  {format_dsr_line(dsr=dsr_result['dsr'], N=dsr_result['N'], T=dsr_result['T'], sr_best=dsr_result['sr_best'], significant=dsr_result['significant'])}")


def analysis_market_hours(trades, metrics, trips, timeline):
    """24h Market Hours シミュレーション。"""
    print("\n=== 24h Market Hours Analysis ===")

    hourly_metrics = aggregate_metrics_by_hour(metrics)
    hourly_trips = aggregate_trips_by_hour(trips, metrics)
    calibration = calc_calibration_factors(hourly_metrics, hourly_trips)

    print("\n--- Calibration (UTC 00-14 trading data) ---")
    print(f"  P&L/trip: {calibration.pnl_per_trip:.2f} JPY")
    print(f"  avg best_ev: {calibration.avg_best_ev:.1f}")
    print(f"  ev_to_pnl_ratio: {calibration.ev_to_pnl_ratio:.6f}")
    print(f"  Fill rate: {calibration.fill_rate:.1%}")
    print(f"  Trips/h: {calibration.trips_per_hour:.1f}")
    print(f"  Trading hours observed: {calibration.trading_hours_observed:.1f}h")

    estimates = estimate_non_trading_hours(hourly_metrics, hourly_trips, calibration)

    # 非取引時間帯に実績があるか判定 (クロスバリデーション可能?)
    non_trading_actual = [
        e for e in estimates
        if e.is_actual and not (0 <= e.utc_hour < 15)
    ]
    has_cross_val = len(non_trading_actual) > 0

    print("\n--- Hourly Comparison ---")
    if has_cross_val:
        headers = [
            "UTC", "status", "trips", "pnl/trip", "pnl/h",
            "est_pnl/t", "est_pnl/h", "err%", "best_ev", "vol",
        ]
        widths = [4, 10, 6, 9, 9, 9, 9, 6, 9, 8]
    else:
        headers = [
            "UTC", "status", "trips", "pnl/trip", "pnl/h",
            "best_ev", "vol", "spread", "p_fill",
        ]
        widths = [4, 10, 6, 9, 9, 9, 8, 8, 7]

    rows = []
    for e in estimates:
        if e.best_ev == 0 and e.trips == 0 and not e.is_actual:
            continue
        status = "actual" if e.is_actual else "estimated"
        if has_cross_val:
            if e.is_actual and e.pnl_per_hour != 0 and e.est_pnl_per_hour != 0:
                err_pct = (e.est_pnl_per_hour - e.pnl_per_hour) / abs(e.pnl_per_hour) * 100
                err_str = f"{err_pct:+.0f}%"
            else:
                err_str = "-"
            rows.append([
                f"{e.utc_hour:02d}",
                status,
                str(e.trips) if e.is_actual else "-",
                f"{e.pnl_per_trip:+.3f}",
                f"{e.pnl_per_hour:+.1f}",
                f"{e.est_pnl_per_trip:+.3f}" if e.is_actual else "-",
                f"{e.est_pnl_per_hour:+.1f}" if e.is_actual else "-",
                err_str,
                f"{e.best_ev:.1f}",
                f"{e.volatility:.1f}",
            ])
        else:
            rows.append([
                f"{e.utc_hour:02d}",
                status,
                str(e.trips) if e.is_actual else "-",
                f"{e.pnl_per_trip:+.3f}",
                f"{e.pnl_per_hour:+.1f}",
                f"{e.best_ev:.1f}",
                f"{e.volatility:.1f}",
                f"{e.spread:.0f}",
                f"{e.p_fill:.2f}",
            ])
    _print_table(headers, rows, widths)

    if has_cross_val:
        print(f"\n  Cross-validation: {len(non_trading_actual)}"
              " non-trading hours with actual data")
        act_sum = sum(e.pnl_per_hour for e in non_trading_actual)
        est_sum = sum(e.est_pnl_per_hour for e in non_trading_actual)
        print(f"  Non-trading actual P&L/h:    {act_sum / len(non_trading_actual):+.1f}")
        print(f"  Non-trading estimated P&L/h: {est_sum / len(non_trading_actual):+.1f}")

    print("\n--- Summary ---")
    print(format_summary(estimates))

    return {"calibration": calibration, "estimates": estimates}


def analysis_vol_regime(trades, metrics, trips, timeline):
    """ボラティリティレジーム別P&L分析。"""
    print("\n=== ボラティリティレジーム分析 ===")
    regime_result = classify_vol_regime(timeline)
    p_low = regime_result["boundaries"]["low"]
    p_high = regime_result["boundaries"]["high"]
    print(f"  Volatility分布: P25={p_low:.1f}  P75={p_high:.1f}")

    rows = analyze_by_vol_regime(trips, regime_result, timeline)
    if not rows:
        print("  トリップデータなし")
        return

    print()
    headers = ["レジーム", "件数", "P&L合計", "P&L/trip", "adverse", "win率", "hold(s)", "avg_vol"]
    widths = [10, 6, 10, 9, 9, 8, 8, 9]
    table_rows = []
    for r in rows:
        if r["count"] == 0:
            continue
        table_rows.append([
            r["regime"],
            str(r["count"]),
            f"{r['pnl_sum']:+.2f}",
            f"{r['pnl_mean']:+.3f}",
            f"{r['adverse_mean']:.3f}",
            f"{r['win_rate']:.1%}",
            f"{r['hold_mean_s']:.1f}",
            f"{r['vol_mean']:.1f}",
        ])
    _print_table(headers, table_rows, widths)

    # --- フィルタwhat-if ---
    print("\n=== フィルタwhat-if ===")
    filter_patterns = [
        ["high"],
        ["high", "mid"],
        ["low"],
    ]
    total_count = sum(r["count"] for r in rows)
    total_pnl = sum(r["pnl_sum"] for r in rows)
    overall_mean = total_pnl / total_count if total_count > 0 else 0.0

    wh_headers = ["除外パターン", "件数", "P&L合計", "P&L/trip", "改善"]
    wh_widths = [18, 6, 10, 9, 12]
    wh_rows = []
    for excl in filter_patterns:
        result = calc_vol_filter_impact(
            trips, regime_result, timeline, exclude_regimes=excl,
        )
        inc = result["included"]
        if inc["count"] > 0:
            improvement = inc["pnl_mean"] - overall_mean
            wh_rows.append([
                "+".join(excl) + "除外",
                str(inc["count"]),
                f"{inc['pnl_sum']:+.2f}",
                f"{inc['pnl_mean']:+.3f}",
                f"{improvement:+.3f}/trip",
            ])
    _print_table(wh_headers, wh_rows, wh_widths)

    # --- DSR 判定 ---
    matched = [t for t in trips if t.close_fill is not None]
    if matched:
        best_sr = float("-inf")
        best_pnl_list: list[float] = []
        for excl in filter_patterns:
            inc_trips = [
                t for t in matched
                if get_trip_regime_label(t, regime_result, timeline) not in set(excl)
            ]
            if len(inc_trips) >= 2:
                pnl_list = [t.pnl_jpy for t in inc_trips]
                sr = calc_sharpe_ratio(pnl_list)
                if sr > best_sr:
                    best_sr = sr
                    best_pnl_list = pnl_list
        if best_pnl_list:
            dsr_result = evaluate_dsr(best_pnl_list, N=len(filter_patterns))
            dsr_line = format_dsr_line(
                dsr=dsr_result["dsr"],
                N=dsr_result["N"],
                T=dsr_result["T"],
                sr_best=dsr_result["sr_best"],
                significant=dsr_result["significant"],
            )
            print(f"\n  {dsr_line}")


def analysis_min_hold(trades, metrics, trips, timeline):
    """min_hold（最低保持時間）シミュレーション分析。"""
    print("\n=== min_hold シミュレーション ===")
    results = simulate_min_hold_sweep(trips, timeline)
    if not results or results[0]["total_trips"] == 0:
        print("  トリップデータなし")
        return

    headers = ["min_hold", "件数", "影響trip", "orig_pnl/t", "sim_pnl/t", "delta"]
    widths = [10, 6, 10, 12, 12, 10]
    table_rows = []
    for r in results:
        table_rows.append([
            f"{r['min_hold_s']:.0f}s",
            str(r["total_trips"]),
            str(r["affected_trips"]),
            f"{r['pnl_per_trip_orig']:+.3f}",
            f"{r['pnl_per_trip_sim']:+.3f}",
            f"{r['delta_pnl'] / r['total_trips']:+.3f}",
        ])
    _print_table(headers, table_rows, widths)

    # --- DSR 判定 ---
    best_sr = float("-inf")
    best_pnl_list: list[float] = []
    for r in results:
        pnl_list = r["simulated_pnl_list"]
        if len(pnl_list) >= 2:
            sr = calc_sharpe_ratio(pnl_list)
            if sr > best_sr:
                best_sr = sr
                best_pnl_list = pnl_list
    if best_pnl_list:
        dsr_result = evaluate_dsr(best_pnl_list, N=len(results))
        dsr_line = format_dsr_line(
            dsr=dsr_result["dsr"],
            N=dsr_result["N"],
            T=dsr_result["T"],
            sr_best=dsr_result["sr_best"],
            significant=dsr_result["significant"],
        )
        print(f"\n  {dsr_line}")


def analysis_dvol_regime(trades, metrics, trips, timeline, date: str):
    """DVOL Z-Scoreレジーム分析。"""
    print("\n=== DVOL Z-Scoreレジーム分析 ===")

    from datetime import datetime as _datetime, timedelta as _timedelta
    target = _datetime.strptime(date, "%Y-%m-%d")
    start = (target - _timedelta(days=30)).strftime("%Y-%m-%d")

    try:
        dvol_data = fetch_dvol(start, date)
    except Exception as e:
        print(f"  DVOL取得失敗: {e}")
        return

    if not dvol_data:
        print("  DVOLデータなし")
        return

    zscore_data = calc_dvol_zscore(dvol_data, lookback_hours=720)
    regime_result = classify_dvol_regime(zscore_data)

    stats = regime_result["stats"]
    print(f"  DVOL: mean={stats['mean']:.1f}  std={stats['std']:.1f}")

    day_zscores = [d for d in zscore_data if d["timestamp"].strftime("%Y-%m-%d") == date]
    if day_zscores:
        z_min = min(d["z_score"] for d in day_zscores)
        z_max = max(d["z_score"] for d in day_zscores)
        z_last = day_zscores[-1]["z_score"]
        print(f"  当日Z-Score: min={z_min:.2f}  max={z_max:.2f}  last={z_last:.2f}")

    rows = analyze_by_dvol_regime(trips, regime_result, zscore_data)
    if not rows:
        print("  トリップデータなし")
        return

    print()
    headers = ["レジーム", "件数", "P&L合計", "P&L/trip", "win率"]
    widths = [10, 6, 10, 9, 8]
    table_rows = []
    for r in rows:
        if r["count"] == 0:
            continue
        table_rows.append([
            r["regime"],
            str(r["count"]),
            f"{r['pnl_sum']:+.2f}",
            f"{r['pnl_mean']:+.3f}",
            f"{r['win_rate']:.1%}",
        ])
    _print_table(headers, table_rows, widths)

    print("\n=== フィルタwhat-if ===")
    filter_patterns = [["high"], ["high", "low"]]
    total_count = sum(r["count"] for r in rows)
    total_pnl = sum(r["pnl_sum"] for r in rows)
    overall_mean = total_pnl / total_count if total_count > 0 else 0.0

    wh_headers = ["除外パターン", "件数", "P&L合計", "P&L/trip", "改善"]
    wh_widths = [18, 6, 10, 9, 12]
    wh_rows = []
    for excl in filter_patterns:
        result = calc_dvol_filter_impact(
            trips, regime_result, zscore_data, exclude_regimes=excl,
        )
        inc = result["included"]
        if inc["count"] > 0:
            improvement = inc["pnl_mean"] - overall_mean
            wh_rows.append([
                "+".join(excl) + "除外",
                str(inc["count"]),
                f"{inc['pnl_sum']:+.2f}",
                f"{inc['pnl_mean']:+.3f}",
                f"{improvement:+.3f}/trip",
            ])
    _print_table(wh_headers, wh_rows, wh_widths)

    # DSR
    matched = [t for t in trips if t.close_fill is not None]
    if matched:
        labels = regime_result["labels"]
        best_sr = float("-inf")
        best_pnl_list: list[float] = []
        for excl in filter_patterns:
            excl_set = set(excl)
            inc_trips = [
                t for t in matched
                if _get_dvol_regime_at(t.open_fill.timestamp, zscore_data, labels) not in excl_set
            ]
            if len(inc_trips) >= 2:
                pnl_list = [t.pnl_jpy for t in inc_trips]
                sr = calc_sharpe_ratio(pnl_list)
                if sr > best_sr:
                    best_sr = sr
                    best_pnl_list = pnl_list
        if best_pnl_list:
            dsr_result = evaluate_dsr(best_pnl_list, N=len(filter_patterns))
            dsr_line = format_dsr_line(
                dsr=dsr_result["dsr"],
                N=dsr_result["N"],
                T=dsr_result["T"],
                sr_best=dsr_result["sr_best"],
                significant=dsr_result["significant"],
            )
            print(f"\n  {dsr_line}")


def analysis_close_fill(trades, metrics, trips, timeline, min_holds_str, factors_str, after_utc_str=None):
    """反事実 close fill シミュレーション + parameter sweep."""
    print("\n=== close_fill 反事実シミュレーション ===")
    matched = [t for t in trips if t.close_fill is not None]

    # 時間フィルタ: --after-utc で open_fill.timestamp >= 指定時刻のtripのみ
    if after_utc_str:
        from datetime import datetime as _dt, timezone as _tz
        cutoff = _dt.fromisoformat(after_utc_str).replace(tzinfo=_tz.utc)
        before = len(matched)
        matched = [t for t in matched if t.open_fill.timestamp >= cutoff]
        print(f"  時間フィルタ: >= {after_utc_str} UTC ({before} -> {len(matched)} trips)")

    if not matched:
        print("  トリップデータなし")
        return

    # 実績P&Lとの比較用
    actual_pnl = sum(t.pnl_jpy for t in matched)
    actual_pnl_per_trip = actual_pnl / len(matched) if matched else 0.0
    actual_sl = sum(1 for t in matched if t.sl_triggered)
    print(f"  実績: {len(matched)} trips, P&L={actual_pnl:+.2f} ({actual_pnl_per_trip:+.3f}/trip), SL={actual_sl}")

    min_holds = [int(x) for x in min_holds_str.split(",")] if min_holds_str else None
    factors = [float(x) for x in factors_str.split(",")] if factors_str else None

    # --- Baseline 検証 (counterfactual, factor=0.4) ---
    print("\n--- Baseline 検証 (counterfactual) ---")
    cal_results = run_close_fill_sweep(
        trips=matched, timeline=timeline, min_holds=[180], factors=[0.4],
        use_counterfactual=True,
    )
    cal = close_fill_aggregate(cal_results[(180, 0.4)])
    sim_pnl = cal["total_pnl"]
    dev = (sim_pnl - actual_pnl) / abs(actual_pnl) * 100 if actual_pnl != 0 else float("inf")
    sl_err_pp = abs(cal["sl_rate"] - actual_sl / len(matched)) * 100
    print(f"  Sim: P&L={sim_pnl:+.2f} ({cal['pnl_per_trip']:+.3f}/trip), SL={cal['sl_count']}")
    print(f"  P&L 乖離: {dev:+.1f}% (target: ±30%)")
    print(f"  SL 乖離:  {sl_err_pp:.1f}pp (target: ±5pp)")

    # --- Factor sweep ---
    print("\n--- P&L/trip グリッド (counterfactual) ---")
    sweep = run_close_fill_sweep(
        trips=matched, timeline=timeline,
        min_holds=min_holds, factors=factors,
        use_counterfactual=True,
    )
    print_sweep_grid(sweep, metric="pnl_per_trip")
    print("\n--- SL率 グリッド ---")
    print_sweep_grid(sweep, metric="sl_rate")


def analysis_close_dynamics(trades, metrics, trips, timeline):
    """close注文のcancel/resubmit分析。"""
    print("\n=== close注文dynamics分析 ===")
    order_map = build_order_book(trades)
    result = analyze_close_dynamics(trips, order_map, timeline)

    print(f"  Close fills analyzed: {result['total_close_fills']}")
    print(f"  Avg cancel cycles per close: {result['avg_cancel_cycles']:.2f}")
    print(f"  Avg price adjustment (abs): {result['avg_price_adjustment']:.0f} JPY")

    # cancel回数の分布
    cancel_dist: dict[int, int] = {}
    for d in result["details"]:
        cc = d["cancel_count"]
        cancel_dist[cc] = cancel_dist.get(cc, 0) + 1

    print("\n  Cancel回数分布:")
    for cc in sorted(cancel_dist.keys()):
        cnt = cancel_dist[cc]
        print(f"    {cc}回: {cnt}件 ({100*cnt/result['total_close_fills']:.1f}%)")


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="GMO Bot Phase C バックテスト分析")
    parser.add_argument("--date", default="2026-02-27", help="分析日付 (YYYY-MM-DD)")
    parser.add_argument(
        "--analysis",
        choices=["all", "hold_time", "time_filter", "ev_sim", "close_dynamics", "market_hours", "vol_regime", "min_hold", "dvol_regime", "close_fill"],
        default="all",
        help="実行する分析",
    )
    parser.add_argument("--utc-start", type=int, default=8, help="時間フィルタ開始 (UTC hour)")
    parser.add_argument("--utc-end", type=int, default=14, help="時間フィルタ終了 (UTC hour)")
    parser.add_argument("--alpha", type=float, default=0.7, help="EV計算のalpha値")
    parser.add_argument("--force-fetch", action="store_true", help="キャッシュ無視でVPSから再取得")
    parser.add_argument("--min-holds", type=str, default=None, help="close_fill: min_hold values (comma-separated)")
    parser.add_argument("--factors", type=str, default=None, help="close_fill: factor values (comma-separated)")
    parser.add_argument("--after-utc", type=str, default=None, help="close_fill: filter trips after this UTC time (ISO format, e.g. 2026-04-08T06:14:00)")
    args = parser.parse_args()

    print(f"GMO Bot バックテスト分析: {args.date}")
    print("=" * 60)

    trades = load_trades(args.date, force_fetch=args.force_fetch)
    metrics = load_metrics(args.date, force_fetch=args.force_fetch)
    logger.info("Trades: %d件, Metrics: %d行", len(trades), len(metrics))

    if not trades:
        logger.error("No trade data found for %s", args.date)
        sys.exit(1)

    timeline = build_market_timeline(metrics)
    trips = build_trips(trades)
    matched = [t for t in trips if t.close_fill is not None]
    unclosed = len(trips) - len(matched)
    logger.info("Trips: %d件 (matched: %d, unclosed: %d)", len(trips), len(matched), unclosed)

    print(f"Trips: {len(trips)}件 (matched: {len(matched)}, unclosed: {unclosed})")
    print()

    if args.analysis in ("all", "hold_time"):
        analysis_hold_time(trades, metrics, trips, timeline)

    if args.analysis in ("all", "time_filter"):
        analysis_time_filter(
            trades, metrics, trips, timeline,
            utc_start=args.utc_start, utc_end=args.utc_end,
        )

    if args.analysis in ("all", "ev_sim"):
        analysis_ev_sim(trades, metrics, trips, timeline, alpha=args.alpha)

    if args.analysis in ("all", "close_dynamics"):
        analysis_close_dynamics(trades, metrics, trips, timeline)

    if args.analysis in ("all", "market_hours"):
        analysis_market_hours(trades, metrics, trips, timeline)

    if args.analysis in ("all", "vol_regime"):
        analysis_vol_regime(trades, metrics, trips, timeline)

    if args.analysis in ("all", "min_hold"):
        analysis_min_hold(trades, metrics, trips, timeline)

    if args.analysis in ("all", "dvol_regime"):
        analysis_dvol_regime(trades, metrics, trips, timeline, date=args.date)

    if args.analysis in ("all", "close_fill"):
        analysis_close_fill(trades, metrics, trips, timeline, args.min_holds, args.factors, args.after_utc)


if __name__ == "__main__":
    main()
