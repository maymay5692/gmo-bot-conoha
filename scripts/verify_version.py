#!/usr/bin/env python3
"""Standardized version verification script for gmo-bot.

Computes a fixed set of metrics (A-F categories) from trades/metrics CSVs,
outputs JSON for version-to-version comparison.

Usage:
    python scripts/verify_version.py --date 2026-02-19
    python scripts/verify_version.py --fetch --date 2026-02-19
    python scripts/verify_version.py --date 2026-02-19 --date 2026-02-20
    python scripts/verify_version.py --compare v0.9.5.json v0.10.0.json
    python scripts/verify_version.py --dates
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, deque
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))
from lib.data_fetch import fetch_dates, get_data, AUTH  # noqa: E402

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), ".cache")


def safe_float(val, default=0.0) -> float:
    try:
        v = float(val)
        return v if v == v else default  # NaN check
    except (ValueError, TypeError):
        return default


def parse_ts(ts_str: str) -> Optional[datetime]:
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str)
    except ValueError:
        return None


# ============================================================
# A. Operational Summary
# ============================================================

def calc_operational(trades: list[dict], metrics: list[dict]) -> dict:
    result = {}

    if trades:
        valid_timestamps: list[datetime] = [
            ts for ts in (parse_ts(t.get("timestamp", "")) for t in trades)
            if ts is not None
        ]
        if len(valid_timestamps) >= 2:
            duration = (max(valid_timestamps) - min(valid_timestamps)).total_seconds()
            result["A1_uptime_hours"] = round(duration / 3600, 2)
        else:
            result["A1_uptime_hours"] = 0
        result["A2_total_events"] = len(trades)
    else:
        result["A1_uptime_hours"] = 0
        result["A2_total_events"] = 0

    result["A3_cycles"] = len(metrics) if metrics else 0
    return result


# ============================================================
# B. Order Flow
# ============================================================

def calc_order_flow(trades: list[dict]) -> dict:
    if not trades:
        return {f"B{i}": 0 for i in range(1, 11)}

    events = Counter(t.get("event", "") for t in trades)
    sent = events.get("ORDER_SENT", 0)
    filled = events.get("ORDER_FILLED", 0)
    cancelled = events.get("ORDER_CANCELLED", 0)
    failed = events.get("ORDER_FAILED", 0)
    stop_loss = events.get("STOP_LOSS_TRIGGERED", 0)

    # Open/Close fill rates
    open_sent = sum(1 for t in trades if t.get("event") == "ORDER_SENT" and t.get("is_close") == "false")
    open_filled = sum(1 for t in trades if t.get("event") == "ORDER_FILLED" and t.get("is_close") == "false")
    close_sent = sum(1 for t in trades if t.get("event") == "ORDER_SENT" and t.get("is_close") == "true")
    close_filled = sum(1 for t in trades if t.get("event") == "ORDER_FILLED" and t.get("is_close") == "true")

    # BUY/SELL fill rates
    buy_sent = sum(1 for t in trades if t.get("event") == "ORDER_SENT" and t.get("side") == "BUY")
    buy_filled = sum(1 for t in trades if t.get("event") == "ORDER_FILLED" and t.get("side") == "BUY")
    sell_sent = sum(1 for t in trades if t.get("event") == "ORDER_SENT" and t.get("side") == "SELL")
    sell_filled = sum(1 for t in trades if t.get("event") == "ORDER_FILLED" and t.get("side") == "SELL")

    return {
        "B1_order_sent": sent,
        "B2_order_filled": filled,
        "B3_order_cancelled": cancelled,
        "B4_order_failed": failed,
        "B5_stop_loss_triggered": stop_loss,
        "B6_fill_rate_pct": round(filled / sent * 100, 2) if sent else 0,
        "B7_open_fill_rate_pct": round(open_filled / open_sent * 100, 2) if open_sent else 0,
        "B8_close_fill_rate_pct": round(close_filled / close_sent * 100, 2) if close_sent else 0,
        "B9_buy_fill_rate_pct": round(buy_filled / buy_sent * 100, 2) if buy_sent else 0,
        "B10_sell_fill_rate_pct": round(sell_filled / sell_sent * 100, 2) if sell_sent else 0,
    }


# ============================================================
# C. P&L
# ============================================================

def calc_pnl(metrics: list[dict], uptime_hours: float) -> dict:
    if not metrics:
        return {f"C{i}": 0 for i in range(1, 7)}

    collaterals = [safe_float(m.get("collateral", 0)) for m in metrics]
    positive = [c for c in collaterals if c > 0]

    if len(positive) < 2:
        return {f"C{i}": 0 for i in range(1, 7)}

    c_start = positive[0]
    c_end = positive[-1]
    pnl = c_end - c_start

    # Max drawdown: peak - trough
    peak = positive[0]
    max_dd: float = 0.0
    for c in positive:
        if c > peak:
            peak = c
        dd = peak - c
        if dd > max_dd:
            max_dd = dd

    return {
        "C1_collateral_start": round(c_start),
        "C2_collateral_end": round(c_end),
        "C3_pnl_jpy": round(pnl),
        "C4_pnl_pct": round(pnl / c_start * 100, 4) if c_start else 0,
        "C5_max_drawdown_jpy": round(max_dd),
        "C6_pnl_per_hour": round(pnl / uptime_hours, 2) if uptime_hours > 0 else 0,
    }


# ============================================================
# D. Trip Analysis (FIFO matching)
# ============================================================

def build_trips(trades: list[dict]) -> tuple[list[dict], int, int]:
    """FIFO match open fills to close fills to build round-trip trades.

    Returns (trips, unmatched_opens, unmatched_closes).
    """
    fills = [t for t in trades if t.get("event") == "ORDER_FILLED"]

    open_buy_queue: deque[dict] = deque()
    open_sell_queue: deque[dict] = deque()
    trips: list[dict] = []
    unmatched_closes = 0

    for f in fills:
        is_close = f.get("is_close") == "true"
        side = f.get("side", "")

        if not is_close:
            if side == "BUY":
                open_buy_queue.append(f)
            elif side == "SELL":
                open_sell_queue.append(f)
        else:
            # Close fill: match with opposite open
            if side == "SELL" and open_buy_queue:
                open_fill = open_buy_queue.popleft()
                trips.append(_make_trip(open_fill, f, "LONG"))
            elif side == "BUY" and open_sell_queue:
                open_fill = open_sell_queue.popleft()
                trips.append(_make_trip(open_fill, f, "SHORT"))
            else:
                unmatched_closes += 1

    unmatched_opens = len(open_buy_queue) + len(open_sell_queue)
    return trips, unmatched_opens, unmatched_closes


def _make_trip(open_fill: dict, close_fill: dict, direction: str) -> dict:
    open_price = safe_float(open_fill.get("price"))
    close_price = safe_float(close_fill.get("price"))
    size = safe_float(open_fill.get("size"))
    open_mid = safe_float(open_fill.get("mid_price"))
    close_mid = safe_float(close_fill.get("mid_price"))

    open_ts = parse_ts(open_fill.get("timestamp", ""))
    close_ts = parse_ts(close_fill.get("timestamp", ""))
    hold_seconds = (close_ts - open_ts).total_seconds() if open_ts and close_ts else 0

    if direction == "LONG":
        pnl = (close_price - open_price) * size
        # Signed spread capture: positive = bought below mid + sold above mid
        spread_capture = (open_mid - open_price) + (close_price - close_mid)
        # Mid movement: positive = favorable for long (mid went up)
        mid_adverse_signed = close_mid - open_mid
    else:  # SHORT
        pnl = (open_price - close_price) * size
        # Signed spread capture: positive = sold above mid + bought below mid
        spread_capture = (open_price - open_mid) + (close_mid - close_price)
        # Mid movement: positive = favorable for short (mid went down)
        mid_adverse_signed = open_mid - close_mid

    return {
        "direction": direction,
        "pnl": pnl,
        "spread_capture": spread_capture * size,
        "mid_movement": mid_adverse_signed * size,
        "hold_seconds": hold_seconds,
        "open_price": open_price,
        "close_price": close_price,
        "open_mid": open_mid,
        "close_mid": close_mid,
        "size": size,
    }


def calc_trips(trades: list[dict]) -> dict:
    trips, unmatched_opens, unmatched_closes = build_trips(trades)

    if not trips:
        return {
            "D1_completed_trips": 0,
            "D2_pnl_per_trip": 0,
            "D3_spread_capture_per_trip": 0,
            "D4_mid_adverse_per_trip": 0,
            "D5_win_rate_pct": 0,
            "D6_avg_hold_seconds": 0,
            "D7_median_hold_seconds": 0,
            "D8_hold_distribution": {},
            "D9_unmatched_opens": unmatched_opens,
            "D10_unmatched_closes": unmatched_closes,
        }

    n = len(trips)
    pnls = [t["pnl"] for t in trips]
    spreads = [t["spread_capture"] for t in trips]
    mids = [t["mid_movement"] for t in trips]
    holds = sorted(t["hold_seconds"] for t in trips)
    wins = sum(1 for p in pnls if p > 0)

    # Hold time distribution buckets
    buckets = {"0-5s": [], "5-10s": [], "10-30s": [], "30-120s": [], "120s+": []}
    for t in trips:
        h = t["hold_seconds"]
        if h <= 5:
            buckets["0-5s"].append(t["pnl"])
        elif h <= 10:
            buckets["5-10s"].append(t["pnl"])
        elif h <= 30:
            buckets["10-30s"].append(t["pnl"])
        elif h <= 120:
            buckets["30-120s"].append(t["pnl"])
        else:
            buckets["120s+"].append(t["pnl"])

    hold_dist = {}
    for bucket, bucket_pnls in buckets.items():
        hold_dist[bucket] = {
            "count": len(bucket_pnls),
            "avg_pnl": round(sum(bucket_pnls) / len(bucket_pnls), 4) if bucket_pnls else 0,
        }

    median_idx = n // 2
    median_hold: float = holds[median_idx] if n % 2 == 1 else (holds[median_idx - 1] + holds[median_idx]) / 2

    return {
        "D1_completed_trips": n,
        "D2_pnl_per_trip": round(sum(pnls) / n, 4),
        "D3_spread_capture_per_trip": round(sum(spreads) / n, 4),
        "D4_mid_adverse_per_trip": round(sum(mids) / n, 4),
        "D5_win_rate_pct": round(wins / n * 100, 2),
        "D6_avg_hold_seconds": round(sum(holds) / n, 2),
        "D7_median_hold_seconds": round(median_hold, 2),
        "D8_hold_distribution": hold_dist,
        "D9_unmatched_opens": unmatched_opens,
        "D10_unmatched_closes": unmatched_closes,
    }


# ============================================================
# E. Market Environment
# ============================================================

def calc_market(metrics: list[dict]) -> dict:
    if not metrics:
        return {f"E{i}": 0 for i in range(1, 7)}

    def avg_field(field: str) -> float:
        vals = [safe_float(m.get(field)) for m in metrics if m.get(field) is not None and m.get(field) != ""]
        return round(sum(vals) / len(vals), 6) if vals else 0

    buy_spreads = [safe_float(m.get("buy_spread_pct")) for m in metrics if m.get("buy_spread_pct") is not None and m.get("buy_spread_pct") != ""]
    sell_spreads = [safe_float(m.get("sell_spread_pct")) for m in metrics if m.get("sell_spread_pct") is not None and m.get("sell_spread_pct") != ""]
    avg_spread = 0
    if buy_spreads and sell_spreads:
        avg_spread = (sum(buy_spreads) / len(buy_spreads) + sum(sell_spreads) / len(sell_spreads)) / 2

    return {
        "E1_avg_mid_price": round(avg_field("mid_price"), 1),
        "E2_avg_volatility": round(avg_field("volatility"), 2),
        "E3_avg_sigma_1s": avg_field("sigma_1s"),
        "E4_avg_spread_pct": round(avg_spread, 6),
        "E5_avg_t_optimal_ms": round(avg_field("t_optimal_ms"), 1),
        "E6_avg_best_ev": round(avg_field("best_ev"), 4),
    }


# ============================================================
# F. Errors & Anomalies
# ============================================================

def calc_errors(trades: list[dict]) -> dict:
    if not trades:
        return {f"F{i}": 0 for i in range(1, 6)}

    failed = [t for t in trades if t.get("event") == "ORDER_FAILED"]
    stop_loss = [t for t in trades if t.get("event") == "STOP_LOSS_TRIGGERED"]

    err_201 = sum(1 for t in failed if "ERR-201" in t.get("error", ""))
    err_422 = sum(1 for t in failed if "ERR-422" in t.get("error", ""))
    err_5003 = sum(1 for t in failed if "ERR-5003" in t.get("error", ""))
    err_5122 = sum(1 for t in failed if "ERR-5122" in t.get("error", ""))

    # Stop-loss total loss (extract unrealized_pnl from error field)
    sl_total_loss = 0.0
    for t in stop_loss:
        error_str = t.get("error", "")
        match = re.search(r"unrealized_pnl[=:]?\s*(-?[\d.]+)", error_str)
        if match:
            sl_total_loss += safe_float(match.group(1))

    return {
        "F1_err_201_margin": err_201,
        "F2_err_422_ghost": err_422,
        "F3_err_5003_sok": err_5003,
        "F4_err_5122_already_filled": err_5122,
        "F5_stop_loss_total_jpy": round(sl_total_loss, 2),
    }


# ============================================================
# Aggregate all categories
# ============================================================

def compute_all(trades: list[dict], metrics: list[dict]) -> dict:
    a = calc_operational(trades, metrics)
    b = calc_order_flow(trades)
    c = calc_pnl(metrics, a.get("A1_uptime_hours", 0))
    d = calc_trips(trades)
    e = calc_market(metrics)
    f = calc_errors(trades)

    return {
        "A_operational": a,
        "B_order_flow": b,
        "C_pnl": c,
        "D_trips": d,
        "E_market": e,
        "F_errors": f,
    }


# ============================================================
# Display
# ============================================================

def print_report(result: dict, dates: list[str]) -> None:
    print(f"\n{'='*60}")
    print(f"  Version Verification Report")
    print(f"  Dates: {', '.join(dates)}")
    print(f"{'='*60}")

    a = result["A_operational"]
    print(f"\n--- A. Operational Summary ---")
    print(f"  A1 Uptime:        {a['A1_uptime_hours']:.1f} hours")
    print(f"  A2 Total events:  {a['A2_total_events']:,}")
    print(f"  A3 Cycles:        {a['A3_cycles']:,}")

    b = result["B_order_flow"]
    print(f"\n--- B. Order Flow ---")
    print(f"  B1 ORDER_SENT:      {b['B1_order_sent']:,}")
    print(f"  B2 ORDER_FILLED:    {b['B2_order_filled']:,}")
    print(f"  B3 ORDER_CANCELLED: {b['B3_order_cancelled']:,}")
    print(f"  B4 ORDER_FAILED:    {b['B4_order_failed']:,}")
    print(f"  B5 STOP_LOSS:       {b['B5_stop_loss_triggered']}")
    print(f"  B6 Fill Rate:       {b['B6_fill_rate_pct']:.2f}%")
    print(f"  B7 Open Fill Rate:  {b['B7_open_fill_rate_pct']:.2f}%")
    print(f"  B8 Close Fill Rate: {b['B8_close_fill_rate_pct']:.2f}%")
    print(f"  B9 BUY Fill Rate:   {b['B9_buy_fill_rate_pct']:.2f}%")
    print(f"  B10 SELL Fill Rate: {b['B10_sell_fill_rate_pct']:.2f}%")

    c = result["C_pnl"]
    print(f"\n--- C. P&L ---")
    print(f"  C1 Collateral start: {c['C1_collateral_start']:,} JPY")
    print(f"  C2 Collateral end:   {c['C2_collateral_end']:,} JPY")
    print(f"  C3 P&L:             {c['C3_pnl_jpy']:+,} JPY")
    print(f"  C4 P&L %:           {c['C4_pnl_pct']:+.4f}%")
    print(f"  C5 Max Drawdown:    {c['C5_max_drawdown_jpy']:,} JPY")
    print(f"  C6 P&L/hour:        {c['C6_pnl_per_hour']:+.2f} JPY/h")

    d = result["D_trips"]
    print(f"\n--- D. Trip Analysis ---")
    print(f"  D1 Completed trips:        {d['D1_completed_trips']:,}")
    print(f"  D2 P&L/trip:               {d['D2_pnl_per_trip']:+.4f} JPY")
    print(f"  D3 Spread capture/trip:    {d['D3_spread_capture_per_trip']:.4f} JPY")
    print(f"  D4 Mid adverse/trip:       {d['D4_mid_adverse_per_trip']:+.4f} JPY")
    print(f"  D5 Win rate:               {d['D5_win_rate_pct']:.2f}%")
    print(f"  D6 Avg hold time:          {d['D6_avg_hold_seconds']:.1f}s")
    print(f"  D7 Median hold time:       {d['D7_median_hold_seconds']:.1f}s")
    if d.get("D8_hold_distribution"):
        print("  D8 Hold distribution:")
        for bucket, info in d["D8_hold_distribution"].items():
            print(f"      {bucket:8s}: {info['count']:5d} trips, avg P&L {info['avg_pnl']:+.4f} JPY")
    print(f"  D9 Unmatched opens:        {d.get('D9_unmatched_opens', 0)}")
    print(f"  D10 Unmatched closes:      {d.get('D10_unmatched_closes', 0)}")

    e = result["E_market"]
    print(f"\n--- E. Market Environment ---")
    print(f"  E1 Avg mid price:    {e['E1_avg_mid_price']:,.1f} JPY")
    print(f"  E2 Avg volatility:   {e['E2_avg_volatility']:.2f}")
    print(f"  E3 Avg sigma_1s:     {e['E3_avg_sigma_1s']:.6f}")
    print(f"  E4 Avg spread_pct:   {e['E4_avg_spread_pct']:.6f}")
    print(f"  E5 Avg t_optimal_ms: {e['E5_avg_t_optimal_ms']:.1f}")
    print(f"  E6 Avg best_ev:      {e['E6_avg_best_ev']:.4f}")

    f_err = result["F_errors"]
    print(f"\n--- F. Errors & Anomalies ---")
    print(f"  F1 ERR-201 (Margin):        {f_err['F1_err_201_margin']}")
    print(f"  F2 ERR-422 (Ghost):         {f_err['F2_err_422_ghost']}")
    print(f"  F3 ERR-5003 (SOK):          {f_err['F3_err_5003_sok']}")
    print(f"  F4 ERR-5122 (Already filled):{f_err['F4_err_5122_already_filled']}")
    print(f"  F5 Stop-loss total:         {f_err['F5_stop_loss_total_jpy']:+.2f} JPY")


# ============================================================
# Compare mode
# ============================================================

def compare_reports(path_a: str, path_b: str) -> None:
    with open(path_a, "r") as f:
        a = json.load(f)
    with open(path_b, "r") as f:
        b = json.load(f)

    name_a = os.path.basename(path_a)
    name_b = os.path.basename(path_b)

    print(f"\n{'='*72}")
    print(f"  Version Comparison: {name_a} vs {name_b}")
    print(f"{'='*72}")

    for category in ["A_operational", "B_order_flow", "C_pnl", "D_trips", "E_market", "F_errors"]:
        cat_a = a.get(category, {})
        cat_b = b.get(category, {})
        all_keys = sorted(set(list(cat_a.keys()) + list(cat_b.keys())))

        print(f"\n--- {category} ---")
        print(f"  {'Metric':<35s} {'Old':>14s} {'New':>14s} {'Delta':>14s}")
        print(f"  {'-'*35} {'-'*14} {'-'*14} {'-'*14}")

        for key in all_keys:
            if key == "D8_hold_distribution":
                _compare_hold_dist(cat_a.get(key, {}), cat_b.get(key, {}))
                continue

            val_a = cat_a.get(key, 0)
            val_b = cat_b.get(key, 0)

            if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                delta = val_b - val_a
                delta_str = f"{delta:+.4f}" if isinstance(delta, float) else f"{delta:+d}"
                print(f"  {key:<35s} {_fmt(val_a):>14s} {_fmt(val_b):>14s} {delta_str:>14s}")
            else:
                print(f"  {key:<35s} {str(val_a):>14s} {str(val_b):>14s}")


def _compare_hold_dist(dist_a: dict, dist_b: dict) -> None:
    buckets = ["0-5s", "5-10s", "10-30s", "30-120s", "120s+"]
    print(f"  {'D8 Hold Distribution':<35s}")
    for bucket in buckets:
        a_info = dist_a.get(bucket, {"count": 0, "avg_pnl": 0})
        b_info = dist_b.get(bucket, {"count": 0, "avg_pnl": 0})
        cnt_delta = b_info["count"] - a_info["count"]
        pnl_delta = b_info["avg_pnl"] - a_info["avg_pnl"]
        print(f"    {bucket:8s} count: {a_info['count']:>5d} -> {b_info['count']:>5d} ({cnt_delta:+d})"
              f"  avg_pnl: {a_info['avg_pnl']:+.4f} -> {b_info['avg_pnl']:+.4f} ({pnl_delta:+.4f})")


def _fmt(val) -> str:
    if isinstance(val, int):
        return f"{val:,}"
    if isinstance(val, float):
        return f"{val:.4f}"
    return str(val)


# ============================================================
# Multi-date aggregation
# ============================================================

def merge_data(all_trades: list[list[dict]], all_metrics: list[list[dict]]) -> tuple[list[dict], list[dict]]:
    merged_trades = []
    for t in all_trades:
        if t:
            merged_trades.extend(t)
    merged_metrics = []
    for m in all_metrics:
        if m:
            merged_metrics.extend(m)

    merged_trades.sort(key=lambda x: x.get("timestamp", ""))
    merged_metrics.sort(key=lambda x: x.get("timestamp", ""))
    return merged_trades, merged_metrics


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Standardized version verification")
    parser.add_argument("--date", action="append", help="Date(s) to analyze (YYYY-MM-DD). Can specify multiple.")
    parser.add_argument("--fetch", action="store_true", help="Force fetch from VPS")
    parser.add_argument("--dates", action="store_true", help="List available dates")
    parser.add_argument("--compare", nargs=2, metavar=("OLD_JSON", "NEW_JSON"), help="Compare two JSON reports")
    parser.add_argument("--version", help="Version label for output filename (e.g. v0.10.0)")
    parser.add_argument("--output", help="Custom output path for JSON")
    parser.add_argument("--json-only", action="store_true", help="Output JSON only, no human-readable report")
    args = parser.parse_args()

    if args.compare:
        compare_reports(args.compare[0], args.compare[1])
        return

    needs_vps = args.dates or args.fetch
    if needs_vps and not AUTH[1]:
        print("Error: Set VPS_PASS environment variable (e.g., export VPS_PASS=yourpass)")
        return

    if args.dates:
        print("Available dates:")
        for csv_type in ["metrics", "trades"]:
            dates = fetch_dates(csv_type)
            print(f"  {csv_type}: {', '.join(dates) if dates else '(none)'}")
        return

    if not args.date:
        print("Error: --date required (e.g. --date 2026-02-19)")
        return

    dates = args.date
    all_trades = []
    all_metrics = []

    for date in dates:
        print(f"Loading data for {date}...")
        trades = get_data("trades", date, force_fetch=args.fetch)
        metrics = get_data("metrics", date, force_fetch=args.fetch)
        all_trades.append(trades or [])
        all_metrics.append(metrics or [])

    merged_trades, merged_metrics = merge_data(all_trades, all_metrics)

    if not merged_trades and not merged_metrics:
        print("\nNo data available. Use --fetch to download from VPS.")
        return

    result = compute_all(merged_trades, merged_metrics)
    result["_meta"] = {
        "dates": dates,
        "version": args.version or "unknown",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if not args.json_only:
        print_report(result, dates)

    # Save JSON
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if args.output:
        out_path = args.output
    else:
        version_label = args.version or "unknown"
        date_label = dates[0] if len(dates) == 1 else f"{dates[0]}_to_{dates[-1]}"
        out_path = os.path.join(OUTPUT_DIR, f"verify-{version_label}-{date_label}.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\nJSON saved: {out_path}")


if __name__ == "__main__":
    main()
