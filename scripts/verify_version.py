#!/usr/bin/env python3
"""Standardized version verification script for gmo-bot.

Computes a fixed set of metrics (A-G categories, H-J planned) from trades/metrics CSVs,
outputs JSON for version-to-version comparison.

Usage:
    python scripts/verify_version.py --date 2026-02-19
    python scripts/verify_version.py --fetch --date 2026-02-19
    python scripts/verify_version.py --date 2026-02-19 --date 2026-02-20
    python scripts/verify_version.py --compare v0.9.5.json v0.10.0.json
    python scripts/verify_version.py --dates
    python scripts/verify_version.py --fetch --date 2026-02-22 --version v0.12.1 --phase 3-0
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


def calc_trips(trades: list[dict], uptime_hours: float = 0) -> dict:
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
            "D11_trips_per_hour": 0,
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
        "D11_trips_per_hour": round(n / uptime_hours, 2) if uptime_hours > 0 else 0,
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
# G. Stop-Loss Detailed Analysis
# ============================================================

def calc_stop_loss_detail(trades: list[dict], uptime_hours: float,
                          completed_trips: int, pnl_per_trip: float,
                          sl_total_jpy: float) -> dict:
    empty_result = {
        "G1_sl_count_per_hour": 0,
        "G2_sl_loss_per_event": 0,
        "G3_sl_impact_per_trip": 0,
        "G4_pnl_ex_sl_per_trip": 0,
        "G5_sl_recovery_trips": -1,
        "G6_max_sl_loss": 0,
    }
    if not trades:
        return empty_result

    stop_loss_events = [t for t in trades if t.get("event") == "STOP_LOSS_TRIGGERED"]

    # Extract individual SL losses from error field
    sl_losses: list[float] = []
    for t in stop_loss_events:
        error_str = t.get("error", "")
        match = re.search(r"unrealized_pnl[=:]?\s*(-?[\d.]+)", error_str)
        if match:
            sl_losses.append(safe_float(match.group(1)))

    sl_count = len(sl_losses)  # Use matched count for consistency with F5

    # G1: SL frequency normalized by uptime
    g1 = round(sl_count / uptime_hours, 4) if uptime_hours > 0 else 0

    # G2: Average loss per SL event
    g2 = round(sl_total_jpy / sl_count, 4) if sl_count > 0 else 0

    # G3: SL impact per trip (total SL loss / completed trips)
    g3 = round(sl_total_jpy / completed_trips, 4) if completed_trips > 0 else 0

    # G4: P&L excluding SL (structural profitability)
    g4 = round(pnl_per_trip - g3, 4)

    # G5: Trips needed to recover from one SL event (when G4 > 0.01)
    if g4 > 0.01:
        g5 = round(abs(g2) / g4, 2)
    else:
        g5 = -1  # Not meaningful: structural profit too small or negative

    # G6: Maximum single SL loss (worst case)
    g6 = round(min(sl_losses), 4) if sl_losses else 0

    return {
        "G1_sl_count_per_hour": g1,
        "G2_sl_loss_per_event": g2,
        "G3_sl_impact_per_trip": g3,
        "G4_pnl_ex_sl_per_trip": g4,
        "G5_sl_recovery_trips": g5,
        "G6_max_sl_loss": g6,
    }


# ============================================================
# H. P(fill) Analysis
# ============================================================

def calc_pfill(trades: list[dict]) -> dict:
    """Analyze P(fill) predictions vs actual fill outcomes.

    Uses new CSV columns (level, p_fill) when available.
    Graceful degradation: returns zeros for old CSV format.
    """
    empty = {
        "H1_observations": 0,
        "H2_predicted_pfill_avg": 0,
        "H3_actual_fill_rate": 0,
        "H4_brier_score": 0,
        "H5_calibration_error": 0,
    }

    sent = [t for t in trades if t.get("event") == "ORDER_SENT" and t.get("is_close") == "false"]
    if not sent:
        return empty

    # Check if new columns exist
    has_pfill = any(t.get("p_fill", "") not in ("", None) for t in sent)
    if not has_pfill:
        return empty

    # Build order_id -> predicted p_fill map
    predictions: dict[str, float] = {}
    for t in sent:
        oid = t.get("order_id", "")
        pf = safe_float(t.get("p_fill", ""))
        if oid and pf > 0:
            predictions[oid] = pf

    if not predictions:
        return empty

    # Match with outcomes (filled or cancelled)
    filled_ids = {t.get("order_id") for t in trades if t.get("event") == "ORDER_FILLED"}
    cancelled_ids = {t.get("order_id") for t in trades if t.get("event") == "ORDER_CANCELLED"}

    obs_count = 0
    pred_sum = 0.0
    actual_sum = 0
    brier_sum = 0.0

    for oid, pred_p in predictions.items():
        if oid in filled_ids:
            actual = 1
        elif oid in cancelled_ids:
            actual = 0
        else:
            continue  # still pending
        obs_count += 1
        pred_sum += pred_p
        actual_sum += actual
        brier_sum += (pred_p - actual) ** 2

    if obs_count == 0:
        return empty

    pred_avg = pred_sum / obs_count
    actual_rate = actual_sum / obs_count
    brier = brier_sum / obs_count
    calib_err = abs(pred_avg - actual_rate)

    return {
        "H1_observations": obs_count,
        "H2_predicted_pfill_avg": round(pred_avg, 6),
        "H3_actual_fill_rate": round(actual_rate, 6),
        "H4_brier_score": round(brier, 6),
        "H5_calibration_error": round(calib_err, 6),
    }


# ============================================================
# I. EV Analysis
# ============================================================

def calc_ev_analysis(trades: list[dict]) -> dict:
    """Analyze single-leg EV predictions and outcomes.

    Uses new CSV columns (single_leg_ev) when available.
    Graceful degradation: returns zeros for old CSV format.
    """
    empty = {
        "I1_avg_single_leg_ev": 0,
        "I2_ev_positive_orders": 0,
        "I3_ev_positive_fill_rate": 0,
        "I4_ev_negative_orders": 0,
        "I5_ev_negative_fill_rate": 0,
    }

    sent = [t for t in trades if t.get("event") == "ORDER_SENT" and t.get("is_close") == "false"]
    if not sent:
        return empty

    has_ev = any(t.get("single_leg_ev", "") not in ("", None) for t in sent)
    if not has_ev:
        return empty

    filled_ids = {t.get("order_id") for t in trades if t.get("event") == "ORDER_FILLED"}
    cancelled_ids = {t.get("order_id") for t in trades if t.get("event") == "ORDER_CANCELLED"}

    ev_values: list[float] = []
    ev_pos_sent = 0
    ev_pos_filled = 0
    ev_neg_sent = 0
    ev_neg_filled = 0

    for t in sent:
        ev = safe_float(t.get("single_leg_ev", ""))
        oid = t.get("order_id", "")
        if ev == 0.0 and t.get("single_leg_ev", "") in ("", None):
            continue
        ev_values.append(ev)

        resolved = oid in filled_ids or oid in cancelled_ids
        filled = oid in filled_ids

        if ev >= 0:
            ev_pos_sent += 1
            if resolved and filled:
                ev_pos_filled += 1
        else:
            ev_neg_sent += 1
            if resolved and filled:
                ev_neg_filled += 1

    if not ev_values:
        return empty

    return {
        "I1_avg_single_leg_ev": round(sum(ev_values) / len(ev_values), 6),
        "I2_ev_positive_orders": ev_pos_sent,
        "I3_ev_positive_fill_rate": round(ev_pos_filled / ev_pos_sent * 100, 2) if ev_pos_sent else 0,
        "I4_ev_negative_orders": ev_neg_sent,
        "I5_ev_negative_fill_rate": round(ev_neg_filled / ev_neg_sent * 100, 2) if ev_neg_sent else 0,
    }


# ============================================================
# Aggregate all categories
# ============================================================

def compute_all(trades: list[dict], metrics: list[dict]) -> dict:
    a = calc_operational(trades, metrics)
    uptime_hours = a.get("A1_uptime_hours", 0)
    b = calc_order_flow(trades)
    c = calc_pnl(metrics, uptime_hours)
    d = calc_trips(trades, uptime_hours)
    e = calc_market(metrics)
    f = calc_errors(trades)
    g = calc_stop_loss_detail(
        trades,
        uptime_hours=uptime_hours,
        completed_trips=d.get("D1_completed_trips", 0),
        pnl_per_trip=d.get("D2_pnl_per_trip", 0),
        sl_total_jpy=f.get("F5_stop_loss_total_jpy", 0),
    )
    h = calc_pfill(trades)
    i = calc_ev_analysis(trades)

    return {
        "A_operational": a,
        "B_order_flow": b,
        "C_pnl": c,
        "D_trips": d,
        "E_market": e,
        "F_errors": f,
        "G_stop_loss_detail": g,
        "H_pfill": h,
        "I_ev_analysis": i,
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
    print(f"  D11 Trips/hour:            {d.get('D11_trips_per_hour', 0):.2f}")

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

    if "G_stop_loss_detail" in result:
        g = result["G_stop_loss_detail"]
        print(f"\n--- G. Stop-Loss Detailed Analysis ---")
        print(f"  G1 SL count/hour:           {g['G1_sl_count_per_hour']:.4f}")
        print(f"  G2 SL loss/event:           {g['G2_sl_loss_per_event']:+.4f} JPY")
        print(f"  G3 SL impact/trip:          {g['G3_sl_impact_per_trip']:+.4f} JPY")
        print(f"  G4 P&L ex-SL/trip:          {g['G4_pnl_ex_sl_per_trip']:+.4f} JPY")
        g5 = g['G5_sl_recovery_trips']
        g5_str = f"{g5:.2f}" if g5 >= 0 else "N/A (G4<=0)"
        print(f"  G5 SL recovery trips:       {g5_str}")
        print(f"  G6 Max single SL loss:      {g['G6_max_sl_loss']:+.4f} JPY")

    if "H_pfill" in result:
        h = result["H_pfill"]
        if h.get("H1_observations", 0) > 0:
            print(f"\n--- H. P(fill) Analysis ---")
            print(f"  H1 Observations:            {h['H1_observations']:,}")
            print(f"  H2 Predicted P(fill) avg:   {h['H2_predicted_pfill_avg']:.6f}")
            print(f"  H3 Actual fill rate:        {h['H3_actual_fill_rate']:.6f}")
            print(f"  H4 Brier score:             {h['H4_brier_score']:.6f}")
            print(f"  H5 Calibration error:       {h['H5_calibration_error']:.6f}")
        else:
            print(f"\n--- H. P(fill) Analysis --- (no data, old CSV format)")

    if "I_ev_analysis" in result:
        i = result["I_ev_analysis"]
        if i.get("I2_ev_positive_orders", 0) > 0 or i.get("I4_ev_negative_orders", 0) > 0:
            print(f"\n--- I. EV Analysis ---")
            print(f"  I1 Avg single-leg EV:       {i['I1_avg_single_leg_ev']:.6f}")
            print(f"  I2 EV+ orders:              {i['I2_ev_positive_orders']:,}")
            print(f"  I3 EV+ fill rate:           {i['I3_ev_positive_fill_rate']:.2f}%")
            print(f"  I4 EV- orders:              {i['I4_ev_negative_orders']:,}")
            print(f"  I5 EV- fill rate:           {i['I5_ev_negative_fill_rate']:.2f}%")
        else:
            print(f"\n--- I. EV Analysis --- (no data, old CSV format)")


# ============================================================
# Phase judgment
# ============================================================

# Baselines from v0.12.1 (2026-02-22, 11.7h) - reference for phase judgment thresholds
_BASELINES_V0121 = {
    "G1_sl_count_per_hour": 0.94,   # 11 SL / 11.72h
    "G3_sl_impact_per_trip": -1.11,  # -218.32 / 196
    "G4_pnl_ex_sl_per_trip": 0.45,
    "D2_pnl_per_trip": -0.66,
    "C6_pnl_per_hour": -26.5,
}


def _check(label: str, actual: float, op: str, threshold: float, unit: str = "") -> str:
    if op == "<":
        passed = actual < threshold
    elif op == ">":
        passed = actual > threshold
    elif op == "<=":
        passed = actual <= threshold
    else:
        passed = actual >= threshold
    status = "PASS" if passed else "FAIL"
    return f"  [{status}] {label}: {actual:+.4f}{unit} (threshold: {op} {threshold}{unit})"


def print_phase_judgment(result: dict, phase: str) -> None:
    d = result.get("D_trips", {})
    c = result.get("C_pnl", {})
    g = result.get("G_stop_loss_detail", {})
    a = result.get("A_operational", {})
    b = result.get("B_order_flow", {})

    uptime = a.get("A1_uptime_hours", 0)
    trips = d.get("D1_completed_trips", 0)
    sl_count = b.get("B5_stop_loss_triggered", 0)

    if phase == "3-0":
        print(f"\n{'='*60}")
        print(f"  Phase 3-0 Judgment (SL -10 -> -15)")
        print(f"{'='*60}")

        print(f"\n  Data sufficiency:")
        print(f"    Uptime: {uptime:.1f}h (min: 24h) {'OK' if uptime >= 24 else 'INSUFFICIENT'}")
        print(f"    Trips:  {trips} (min: 300) {'OK' if trips >= 300 else 'INSUFFICIENT'}")
        print(f"    SL events: {sl_count} (min: 3) {'OK' if sl_count >= 3 else 'INSUFFICIENT'}")

        print(f"\n  Monitoring targets (check every 1h):")
        print(_check("G1 SL count/hour", g.get("G1_sl_count_per_hour", 0), "<", 0.5, "/h"))
        print(_check("G3 SL impact/trip", g.get("G3_sl_impact_per_trip", 0), ">", -0.50, " JPY"))

        print(f"\n  Success criteria (after 24h):")
        print(_check("D2 P&L/trip", d.get("D2_pnl_per_trip", 0), ">", -0.30, " JPY"))
        print(_check("C6 P&L/hour", c.get("C6_pnl_per_hour", 0), ">", -15.0, " JPY"))
        print(_check("G4 P&L ex-SL/trip", g.get("G4_pnl_ex_sl_per_trip", 0), ">", 0.30, " JPY"))

        print(f"\n  Rollback triggers:")
        print(_check("C5 Max Drawdown", c.get("C5_max_drawdown_jpy", 0), "<", 1500, " JPY"))
        print(_check("D2 P&L/trip (floor)", d.get("D2_pnl_per_trip", 0), ">", -1.0, " JPY"))
        print(_check("D6 Avg hold (bug check)", d.get("D6_avg_hold_seconds", 0), "<", 600, "s"))

    elif phase == "3-1":
        h = result.get("H_pfill", {})
        i_ev = result.get("I_ev_analysis", {})

        print(f"\n{'='*60}")
        print(f"  Phase 3-1 Judgment (Single-leg EV + P(fill))")
        print(f"{'='*60}")

        print(f"\n  Data sufficiency:")
        print(f"    Uptime: {uptime:.1f}h (min: 48h) {'OK' if uptime >= 48 else 'INSUFFICIENT'}")
        print(f"    Trips:  {trips} (min: 500) {'OK' if trips >= 500 else 'INSUFFICIENT'}")
        h1_obs = h.get("H1_observations", 0)
        print(f"    P(fill) obs: {h1_obs} (min: 200) {'OK' if h1_obs >= 200 else 'INSUFFICIENT'}")

        print(f"\n  P(fill) calibration (H category):")
        print(_check("H4 Brier score", h.get("H4_brier_score", 1.0), "<", 0.25))
        print(_check("H5 Calibration error", h.get("H5_calibration_error", 1.0), "<", 0.10))

        print(f"\n  EV analysis (I category):")
        print(f"    I1 Avg single-leg EV: {i_ev.get('I1_avg_single_leg_ev', 0):.6f}")
        print(f"    I2 EV+ orders: {i_ev.get('I2_ev_positive_orders', 0)}, fill rate: {i_ev.get('I3_ev_positive_fill_rate', 0):.2f}%")
        print(f"    I4 EV- orders: {i_ev.get('I4_ev_negative_orders', 0)}, fill rate: {i_ev.get('I5_ev_negative_fill_rate', 0):.2f}%")

        print(f"\n  Success criteria (after 48h):")
        print(_check("D2 P&L/trip improvement", d.get("D2_pnl_per_trip", 0), ">", -0.30, " JPY"))
        print(_check("D3 Spread capture", d.get("D3_spread_capture_per_trip", 0), ">", 1.60, " JPY"))
        print(_check("D4 Mid adverse", d.get("D4_mid_adverse_per_trip", 0), ">", -1.80, " JPY"))
        print(_check("D11 Trips/hour", d.get("D11_trips_per_hour", 0), ">", 12.0, "/h"))

        print(f"\n  Rollback triggers:")
        print(_check("B6 Fill rate", b.get("B6_fill_rate_pct", 0), ">", 5.0, "%"))

    elif phase == "3-2":
        print(f"\n{'='*60}")
        print(f"  Phase 3-2 Judgment (Parameter Optimization)")
        print(f"{'='*60}")

        print(f"\n  Data sufficiency:")
        print(f"    Uptime: {uptime:.1f}h (min: 24h) {'OK' if uptime >= 24 else 'INSUFFICIENT'}")
        print(f"    Trips:  {trips} (min: 300) {'OK' if trips >= 300 else 'INSUFFICIENT'}")

        print(f"\n  Criteria (per parameter adjustment, 24h each):")
        print(_check("D2 P&L/trip", d.get("D2_pnl_per_trip", 0), ">", -0.30, " JPY"))
        print(f"    J1-J5 optimization metrics: (requires J category - not yet implemented)")

    else:
        print(f"\n  Unknown phase: {phase}. Valid: 3-0, 3-1, 3-2")


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

    all_categories = ["A_operational", "B_order_flow", "C_pnl", "D_trips", "E_market", "F_errors", "G_stop_loss_detail", "H_pfill", "I_ev_analysis"]
    for category in all_categories:
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
    parser.add_argument("--phase", choices=["3-0", "3-1", "3-2"], help="Show phase-specific judgment criteria")
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
    meta = {
        "dates": dates,
        "version": args.version or "unknown",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if args.phase:
        meta["phase"] = args.phase
    result["_meta"] = meta

    if not args.json_only:
        print_report(result, dates)

    if args.phase:
        print_phase_judgment(result, args.phase)

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
