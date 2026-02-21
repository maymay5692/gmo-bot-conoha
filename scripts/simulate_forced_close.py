#!/usr/bin/env python3
"""Simulate forced-close at N seconds after each open fill.

Uses bid/ask from metrics CSV for realistic close price estimation.

Usage:
    python scripts/simulate_forced_close.py --date 2026-02-16 --fetch
    python scripts/simulate_forced_close.py --date 2026-02-16          # use cache
    VPS_PASS=yourpassword python scripts/simulate_forced_close.py --date 2026-02-16 --fetch
"""
import argparse
import bisect
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

VPS_URL = os.environ.get("VPS_URL", "http://160.251.219.3")
AUTH = (
    os.environ.get("VPS_USER", "admin"),
    os.environ.get("VPS_PASS", ""),
)
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")

# Forced-close offsets to simulate (seconds). Extra 1s for API latency.
CLOSE_OFFSETS = [10, 15, 20, 30]
LATENCY_BUFFER_S = 1


# ============================================================
# Data fetching (reused from analyze_metrics.py)
# ============================================================

def fetch_csv(csv_type: str, date: str) -> Optional[list[dict]]:
    url = f"{VPS_URL}/api/{csv_type}/csv?date={date}"
    try:
        resp = requests.get(url, auth=AUTH, timeout=30)
        if resp.status_code == 404:
            print(f"  No {csv_type} data for {date}")
            return None
        resp.raise_for_status()
        return resp.json().get("rows", [])
    except requests.RequestException as e:
        print(f"  Failed to fetch {csv_type}: {e}")
        return None


def cache_data(csv_type: str, date: str, rows: list[dict]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{csv_type}-{date}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)


def load_cached(csv_type: str, date: str) -> Optional[list[dict]]:
    path = os.path.join(CACHE_DIR, f"{csv_type}-{date}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_data(csv_type: str, date: str, force_fetch: bool = False) -> Optional[list[dict]]:
    if not force_fetch:
        cached = load_cached(csv_type, date)
        if cached is not None:
            print(f"  Using cached {csv_type} data ({len(cached)} rows)")
            return cached
    print(f"  Fetching {csv_type} from VPS...")
    rows = fetch_csv(csv_type, date)
    if rows is not None:
        cache_data(csv_type, date, rows)
        print(f"  Fetched and cached {len(rows)} rows")
    return rows


# ============================================================
# Timestamp parsing
# ============================================================

def parse_ts(ts_str: str) -> float:
    """Parse ISO 8601 timestamp to UNIX epoch seconds."""
    ts_str = ts_str.rstrip("Z").split(".")[0]
    dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
    return dt.replace(tzinfo=timezone.utc).timestamp()


# ============================================================
# Metrics time-series index
# ============================================================

class MetricsIndex:
    """Sorted metrics snapshots for fast nearest-neighbour lookup."""

    def __init__(self, metrics_rows: list[dict]):
        self._timestamps: list[float] = []
        self._mid_prices: list[float] = []
        self._best_bids: list[float] = []
        self._best_asks: list[float] = []

        for row in metrics_rows:
            ts = parse_ts(row["timestamp"])
            mid = float(row.get("mid_price", 0))
            bid = float(row.get("best_bid", 0))
            ask = float(row.get("best_ask", 0))
            if mid > 0 and bid > 0 and ask > 0:
                self._timestamps.append(ts)
                self._mid_prices.append(mid)
                self._best_bids.append(bid)
                self._best_asks.append(ask)

    def __len__(self) -> int:
        return len(self._timestamps)

    def lookup(self, target_ts: float) -> Optional[dict]:
        """Find nearest metrics snapshot to target_ts.

        Returns None if no data within 5 seconds of target.
        """
        if not self._timestamps:
            return None

        idx = bisect.bisect_left(self._timestamps, target_ts)

        best_idx = None
        best_diff = float("inf")
        for candidate in [max(0, idx - 1), min(idx, len(self._timestamps) - 1)]:
            diff = abs(self._timestamps[candidate] - target_ts)
            if diff < best_diff:
                best_diff = diff
                best_idx = candidate

        if best_diff > 5.0:
            return None

        return {
            "mid_price": self._mid_prices[best_idx],
            "best_bid": self._best_bids[best_idx],
            "best_ask": self._best_asks[best_idx],
            "ts_diff": best_diff,
        }


# ============================================================
# Extract open fills from trades
# ============================================================

def extract_open_fills(trades_rows: list[dict]) -> list[dict]:
    """Extract ORDER_FILLED events with is_close=false."""
    fills = []
    for row in trades_rows:
        if row.get("event") != "ORDER_FILLED":
            continue
        if row.get("is_close", "").lower() == "true":
            continue

        try:
            fill = {
                "timestamp": parse_ts(row["timestamp"]),
                "side": row["side"],
                "fill_price": int(row["price"]),
                "size": float(row["size"]),
                "mid_price_entry": int(row.get("mid_price", 0)),
                "spread_pct": float(row.get("spread_pct", 0)),
            }
            if fill["fill_price"] > 0 and fill["size"] > 0:
                fills.append(fill)
        except (ValueError, KeyError):
            continue

    return fills


# ============================================================
# Simulation
# ============================================================

def simulate_single(fill: dict, index: MetricsIndex, offset_s: int) -> Optional[dict]:
    """Simulate forced close for a single open fill."""
    target_ts = fill["timestamp"] + offset_s + LATENCY_BUFFER_S
    snap = index.lookup(target_ts)
    if snap is None:
        return None

    side = fill["side"]
    fill_price = fill["fill_price"]
    size = fill["size"]
    mid_entry = fill["mid_price_entry"]
    mid_exit = snap["mid_price"]

    # Close price: sell at bid (long close), buy at ask (short close)
    if side == "BUY":
        close_price = snap["best_bid"]
        pnl = (close_price - fill_price) * size
        mid_movement = (mid_exit - mid_entry) * size
    else:
        close_price = snap["best_ask"]
        pnl = (fill_price - close_price) * size
        mid_movement = (mid_entry - mid_exit) * size

    entry_spread_cost = abs(fill_price - mid_entry) * size
    exit_spread_cost = abs(mid_exit - close_price) * size

    return {
        "side": side,
        "fill_price": fill_price,
        "close_price": close_price,
        "size": size,
        "pnl": pnl,
        "mid_movement": mid_movement,
        "entry_spread_cost": entry_spread_cost,
        "exit_spread_cost": exit_spread_cost,
        "ts_diff": snap["ts_diff"],
    }


def simulate_all(fills: list[dict], index: MetricsIndex, offset_s: int) -> list[dict]:
    results = []
    for fill in fills:
        result = simulate_single(fill, index, offset_s)
        if result is not None:
            results.append(result)
    return results


# ============================================================
# Report
# ============================================================

def print_report(results: list[dict], offset_s: int, total_fills: int) -> None:
    if not results:
        print(f"\n  [{offset_s}s] No results (no metrics data at T+{offset_s}s)")
        return

    n = len(results)
    total_pnl = sum(r["pnl"] for r in results)
    avg_pnl = total_pnl / n
    win_count = sum(1 for r in results if r["pnl"] > 0)
    win_rate = win_count / n * 100

    buy_results = [r for r in results if r["side"] == "BUY"]
    sell_results = [r for r in results if r["side"] == "SELL"]

    avg_mid_mov = sum(r["mid_movement"] for r in results) / n
    avg_entry_cost = sum(r["entry_spread_cost"] for r in results) / n
    avg_exit_cost = sum(r["exit_spread_cost"] for r in results) / n
    avg_ts_diff = sum(r["ts_diff"] for r in results) / n

    # P&L distribution buckets
    buckets = {"<-10": 0, "-10~-5": 0, "-5~-2": 0, "-2~0": 0,
               "0~+2": 0, "+2~+5": 0, "+5<": 0}
    for r in results:
        p = r["pnl"]
        if p < -10:
            buckets["<-10"] += 1
        elif p < -5:
            buckets["-10~-5"] += 1
        elif p < -2:
            buckets["-5~-2"] += 1
        elif p < 0:
            buckets["-2~0"] += 1
        elif p < 2:
            buckets["0~+2"] += 1
        elif p < 5:
            buckets["+2~+5"] += 1
        else:
            buckets["+5<"] += 1

    print(f"\n{'='*60}")
    print(f"  FORCED CLOSE @ T+{offset_s}s (+ {LATENCY_BUFFER_S}s latency)")
    print(f"{'='*60}")
    print(f"  Matched fills: {n}/{total_fills} ({n/total_fills*100:.1f}%)")
    print(f"  Metrics lookup avg error: {avg_ts_diff:.2f}s")
    print()
    print(f"  Total P&L:   {total_pnl:+.1f} JPY")
    print(f"  Avg P&L:     {avg_pnl:+.3f} JPY/trip")
    print(f"  Win rate:    {win_rate:.1f}% ({win_count}/{n})")
    print()

    if buy_results:
        buy_pnl = sum(r["pnl"] for r in buy_results)
        buy_avg = buy_pnl / len(buy_results)
        buy_win = sum(1 for r in buy_results if r["pnl"] > 0) / len(buy_results) * 100
        print(f"  BUY:  avg={buy_avg:+.3f} JPY, win={buy_win:.1f}%, n={len(buy_results)}")

    if sell_results:
        sell_pnl = sum(r["pnl"] for r in sell_results)
        sell_avg = sell_pnl / len(sell_results)
        sell_win = sum(1 for r in sell_results if r["pnl"] > 0) / len(sell_results) * 100
        print(f"  SELL: avg={sell_avg:+.3f} JPY, win={sell_win:.1f}%, n={len(sell_results)}")

    print()
    print(f"  P&L decomposition (avg per trip):")
    print(f"    Mid-price movement: {avg_mid_mov:+.3f} JPY")
    print(f"    Entry spread cost:  -{avg_entry_cost:.3f} JPY")
    print(f"    Exit spread cost:   -{avg_exit_cost:.3f} JPY")
    print(f"    Net (should match): {avg_mid_mov - avg_entry_cost - avg_exit_cost:+.3f} JPY")

    print()
    print(f"  P&L distribution:")
    for label, count in buckets.items():
        bar = "#" * int(count / n * 40) if n > 0 else ""
        print(f"    {label:>7}: {count:4d} ({count/n*100:5.1f}%) {bar}")

    # Worst/best 10
    sorted_by_pnl = sorted(results, key=lambda r: r["pnl"])
    print()
    print(f"  Worst 5 trips:")
    for r in sorted_by_pnl[:5]:
        print(f"    {r['side']:4s} fill={r['fill_price']} close={r['close_price']:.0f} "
              f"pnl={r['pnl']:+.2f}")
    print(f"  Best 5 trips:")
    for r in sorted_by_pnl[-5:]:
        print(f"    {r['side']:4s} fill={r['fill_price']} close={r['close_price']:.0f} "
              f"pnl={r['pnl']:+.2f}")


def print_comparison(all_results: dict[int, list[dict]], collateral_change: Optional[float]) -> None:
    print(f"\n{'='*60}")
    print(f"  COMPARISON ACROSS TIMEOUTS")
    print(f"{'='*60}")
    print(f"  {'Offset':>8s} | {'Avg PnL':>10s} | {'Win%':>6s} | {'Total PnL':>12s} | {'N':>5s}")
    print(f"  {'-'*8} | {'-'*10} | {'-'*6} | {'-'*12} | {'-'*5}")

    for offset in sorted(all_results.keys()):
        results = all_results[offset]
        if not results:
            continue
        n = len(results)
        total = sum(r["pnl"] for r in results)
        avg = total / n
        win = sum(1 for r in results if r["pnl"] > 0) / n * 100
        print(f"  {offset:>6d}s | {avg:>+10.3f} | {win:>5.1f}% | {total:>+12.1f} | {n:>5d}")

    if collateral_change is not None:
        print(f"\n  Actual collateral change: {collateral_change:+.1f} JPY")
        print(f"  (includes all trades: open + close, not just open fills)")


# ============================================================
# Main
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate forced-close at N seconds")
    parser.add_argument("--date", default=None, help="Date to analyze (YYYY-MM-DD)")
    parser.add_argument("--fetch", action="store_true", help="Force fetch from VPS")
    args = parser.parse_args()

    if args.date is None:
        now_jst = datetime.now(timezone(timedelta(hours=9)))
        args.date = now_jst.strftime("%Y-%m-%d")

    print(f"Forced Close Simulation - {args.date}")
    print(f"Close offsets: {CLOSE_OFFSETS} + {LATENCY_BUFFER_S}s latency buffer")

    # Fetch data
    trades = get_data("trades", args.date, args.fetch)
    metrics = get_data("metrics", args.date, args.fetch)

    if not trades or not metrics:
        print("ERROR: Could not load data")
        return

    # Build index
    index = MetricsIndex(metrics)
    print(f"  Metrics index: {len(index)} snapshots")

    # Extract open fills
    fills = extract_open_fills(trades)
    print(f"  Open fills: {len(fills)}")

    if not fills:
        print("ERROR: No open fills found")
        return

    buy_fills = sum(1 for f in fills if f["side"] == "BUY")
    sell_fills = sum(1 for f in fills if f["side"] == "SELL")
    print(f"  BUY: {buy_fills}, SELL: {sell_fills}")

    # Collateral change for comparison
    collateral_change = None
    collateral_vals = [float(m.get("collateral", 0)) for m in metrics
                       if m.get("collateral") and float(m.get("collateral", 0)) > 0]
    if len(collateral_vals) >= 2:
        collateral_change = collateral_vals[-1] - collateral_vals[0]

    # Run simulation for each offset
    all_results: dict[int, list[dict]] = {}
    for offset in CLOSE_OFFSETS:
        results = simulate_all(fills, index, offset)
        all_results[offset] = results
        print_report(results, offset, len(fills))

    # Comparison table
    print_comparison(all_results, collateral_change)

    print(f"\nDone.")


if __name__ == "__main__":
    main()
