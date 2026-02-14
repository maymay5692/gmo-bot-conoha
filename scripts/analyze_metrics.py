#!/usr/bin/env python3
"""Analyze bot metrics and trades CSVs from VPS via Bot Manager API.

Usage:
    python scripts/analyze_metrics.py                    # Today's data
    python scripts/analyze_metrics.py --date 2026-02-14  # Specific date
    python scripts/analyze_metrics.py --fetch             # Fetch from VPS first
    python scripts/analyze_metrics.py --dates             # List available dates
"""
import argparse
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
JST = timezone(timedelta(hours=9))


def fetch_csv(csv_type: str, date: str) -> Optional[list[dict]]:
    """Fetch CSV data from VPS Bot Manager API."""
    url = f"{VPS_URL}/api/{csv_type}/csv?date={date}"
    try:
        resp = requests.get(url, auth=AUTH, timeout=30)
        if resp.status_code == 404:
            print(f"  No {csv_type} data for {date}")
            return None
        resp.raise_for_status()
        data = resp.json()
        return data.get("rows", [])
    except requests.RequestException as e:
        print(f"  Failed to fetch {csv_type}: {e}")
        return None


def fetch_dates(csv_type: str = "metrics") -> list[str]:
    """List available dates from VPS."""
    url = f"{VPS_URL}/api/metrics/dates?type={csv_type}"
    try:
        resp = requests.get(url, auth=AUTH, timeout=10)
        resp.raise_for_status()
        return resp.json().get("dates", [])
    except requests.RequestException as e:
        print(f"Failed to fetch dates: {e}")
        return []


def cache_data(csv_type: str, date: str, rows: list[dict]) -> None:
    """Cache fetched data locally."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{csv_type}-{date}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)


def load_cached(csv_type: str, date: str) -> Optional[list[dict]]:
    """Load cached data if available."""
    path = os.path.join(CACHE_DIR, f"{csv_type}-{date}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_data(csv_type: str, date: str, force_fetch: bool = False) -> Optional[list[dict]]:
    """Get data from cache or VPS."""
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
# Analysis functions
# ============================================================

def analyze_bayesian_fix(metrics: list[dict]) -> None:
    """Analyze whether the Bayesian fix is producing differentiated probabilities."""
    print("\n=== Bayesian Fix Effect ===")

    buy_probs = [float(m.get("buy_prob_avg", 0)) for m in metrics if m.get("buy_prob_avg")]
    sell_probs = [float(m.get("sell_prob_avg", 0)) for m in metrics if m.get("sell_prob_avg")]

    if not buy_probs or not sell_probs:
        print("  No probability data available")
        return

    print(f"  Data points: {len(buy_probs)}")
    print(f"  Buy prob  - avg: {sum(buy_probs)/len(buy_probs):.4f}, "
          f"min: {min(buy_probs):.4f}, max: {max(buy_probs):.4f}, "
          f"range: {max(buy_probs)-min(buy_probs):.4f}")
    print(f"  Sell prob - avg: {sum(sell_probs)/len(sell_probs):.4f}, "
          f"min: {min(sell_probs):.4f}, max: {max(sell_probs):.4f}, "
          f"range: {max(sell_probs)-min(sell_probs):.4f}")

    # Check if probabilities are varying (sign of working Bayesian update)
    buy_range = max(buy_probs) - min(buy_probs)
    sell_range = max(sell_probs) - min(sell_probs)

    if buy_range < 0.01 and sell_range < 0.01:
        print("  WARNING: Probabilities barely changing. Bayesian fix may not be effective.")
    else:
        print(f"  Probabilities are varying (buy range: {buy_range:.4f}, sell range: {sell_range:.4f})")


def analyze_spread_selection(metrics: list[dict]) -> None:
    """Analyze spread level selection patterns."""
    print("\n=== Spread Selection ===")

    buy_spreads = [float(m.get("buy_spread_pct", 0)) for m in metrics if m.get("buy_spread_pct")]
    sell_spreads = [float(m.get("sell_spread_pct", 0)) for m in metrics if m.get("sell_spread_pct")]

    if not buy_spreads:
        print("  No spread data available")
        return

    print(f"  Buy spread  - avg: {sum(buy_spreads)/len(buy_spreads):.5f}%, "
          f"min: {min(buy_spreads):.5f}%, max: {max(buy_spreads):.5f}%")
    print(f"  Sell spread - avg: {sum(sell_spreads)/len(sell_spreads):.5f}%, "
          f"min: {min(sell_spreads):.5f}%, max: {max(sell_spreads):.5f}%")

    # Spread level distribution (FloatingExp: rate 1..25 -> 0.001% to 0.025%)
    from collections import Counter
    buy_levels = Counter()
    sell_levels = Counter()
    for s in buy_spreads:
        level = round(s / 0.001)  # rate number (1-25)
        buy_levels[level] += 1
    for s in sell_spreads:
        level = round(s / 0.001)
        sell_levels[level] += 1

    print(f"\n  Buy spread level distribution (top 5):")
    for level, count in buy_levels.most_common(5):
        pct = count / len(buy_spreads) * 100
        print(f"    Level {level:2d} ({level*0.001:.3f}%): {count:5d} times ({pct:.1f}%)")

    print(f"  Sell spread level distribution (top 5):")
    for level, count in sell_levels.most_common(5):
        pct = count / len(sell_spreads) * 100
        print(f"    Level {level:2d} ({level*0.001:.3f}%): {count:5d} times ({pct:.1f}%)")

    unique_buy = len(buy_levels)
    unique_sell = len(sell_levels)
    print(f"\n  Unique buy levels: {unique_buy}/25, Unique sell levels: {unique_sell}/25")
    if unique_buy <= 3 and unique_sell <= 3:
        print("  WARNING: Bot is using very few spread levels. May indicate Bayesian update not differentiating.")


def analyze_ev(metrics: list[dict]) -> None:
    """Analyze Expected Value distribution."""
    print("\n=== Expected Value (EV) ===")

    evs = [float(m.get("best_ev", 0)) for m in metrics if m.get("best_ev")]

    if not evs:
        print("  No EV data available")
        return

    positive = sum(1 for e in evs if e > 0)
    negative = sum(1 for e in evs if e < 0)
    zero = sum(1 for e in evs if e == 0)

    print(f"  Total cycles: {len(evs)}")
    print(f"  EV > 0: {positive} ({positive/len(evs)*100:.1f}%)")
    print(f"  EV < 0: {negative} ({negative/len(evs)*100:.1f}%)")
    print(f"  EV = 0: {zero} ({zero/len(evs)*100:.1f}%)")
    print(f"  Average EV: {sum(evs)/len(evs):.2f}")
    print(f"  Max EV: {max(evs):.2f}, Min EV: {min(evs):.2f}")


def analyze_volatility(metrics: list[dict]) -> None:
    """Analyze volatility calculation patterns."""
    print("\n=== Volatility ===")

    vols = [float(m.get("volatility", 0)) for m in metrics if m.get("volatility")]

    if not vols:
        print("  No volatility data available")
        return

    zero_count = sum(1 for v in vols if v == 0)
    nonzero = [v for v in vols if v > 0]

    print(f"  Total: {len(vols)}, Zero: {zero_count} ({zero_count/len(vols)*100:.1f}%)")
    if nonzero:
        print(f"  Non-zero - avg: {sum(nonzero)/len(nonzero):.0f}, "
              f"min: {min(nonzero):.0f}, max: {max(nonzero):.0f}")
        # Check for outliers (>3x average)
        avg = sum(nonzero) / len(nonzero)
        outliers = sum(1 for v in nonzero if v > avg * 3)
        print(f"  Outliers (>3x avg): {outliers} ({outliers/len(nonzero)*100:.1f}%)")

    if zero_count / len(vols) > 0.2:
        print("  WARNING: High zero-volatility rate. Bot may be trading without risk assessment.")


def analyze_positions(metrics: list[dict]) -> None:
    """Analyze position holding patterns."""
    print("\n=== Position Analysis ===")

    longs = [float(m.get("long_size", 0)) for m in metrics if m.get("long_size")]
    shorts = [float(m.get("short_size", 0)) for m in metrics if m.get("short_size")]

    if not longs:
        print("  No position data available")
        return

    print(f"  Long  - avg: {sum(longs)/len(longs):.4f}, max: {max(longs):.4f}")
    print(f"  Short - avg: {sum(shorts)/len(shorts):.4f}, max: {max(shorts):.4f}")

    # Time at max position (0.002)
    max_pos = 0.002
    long_at_max = sum(1 for pos in longs if pos >= max_pos)
    short_at_max = sum(1 for pos in shorts if pos >= max_pos)
    print(f"  At max position - long: {long_at_max}/{len(longs)} ({long_at_max/len(longs)*100:.1f}%), "
          f"short: {short_at_max}/{len(shorts)} ({short_at_max/len(shorts)*100:.1f}%)")

    # One-sided exposure (long > 0 and short == 0, or vice versa)
    one_sided = sum(1 for l, s in zip(longs, shorts) if (l > 0 and s == 0) or (s > 0 and l == 0))
    print(f"  One-sided exposure: {one_sided}/{len(longs)} ({one_sided/len(longs)*100:.1f}%)")


def analyze_fill_rate(trades: list[dict]) -> None:
    """Analyze order fill rate."""
    print("\n=== Fill Rate ===")

    if not trades:
        print("  No trade data available")
        return

    sent = [t for t in trades if t.get("event") == "ORDER_SENT"]
    filled = [t for t in trades if t.get("event") == "ORDER_FILLED"]
    cancelled = [t for t in trades if t.get("event") == "ORDER_CANCELLED"]
    failed = [t for t in trades if t.get("event") == "ORDER_FAILED"]

    print(f"  Sent: {len(sent)}, Filled: {len(filled)}, Cancelled: {len(cancelled)}, Failed: {len(failed)}")

    if sent:
        fill_rate = len(filled) / len(sent) * 100
        print(f"  Fill rate: {fill_rate:.1f}%")

    # BUY vs SELL
    buy_sent = sum(1 for t in sent if t.get("side") == "BUY")
    sell_sent = sum(1 for t in sent if t.get("side") == "SELL")
    buy_filled = sum(1 for t in filled if t.get("side") == "BUY")
    sell_filled = sum(1 for t in filled if t.get("side") == "SELL")

    if buy_sent:
        print(f"  BUY  - sent: {buy_sent}, filled: {buy_filled} ({buy_filled/buy_sent*100:.1f}%)")
    if sell_sent:
        print(f"  SELL - sent: {sell_sent}, filled: {sell_filled} ({sell_filled/sell_sent*100:.1f}%)")

    # Close vs Open
    close_sent = sum(1 for t in sent if t.get("is_close") == "true")
    open_sent = len(sent) - close_sent
    print(f"  Close orders: {close_sent}, Open orders: {open_sent}")

    # Error analysis
    if failed:
        from collections import Counter
        error_counts = Counter(t.get("error", "unknown") for t in failed)
        print(f"\n  Error distribution:")
        for err, count in error_counts.most_common(5):
            print(f"    {err}: {count}")


def analyze_pnl_trend(metrics: list[dict]) -> None:
    """Analyze P&L trend from collateral changes."""
    print("\n=== Collateral Trend ===")

    collaterals = [(m.get("timestamp", ""), float(m.get("collateral", 0)))
                   for m in metrics if m.get("collateral") and float(m.get("collateral", 0)) > 0]

    if len(collaterals) < 2:
        print("  Insufficient collateral data")
        return

    first_val = collaterals[0][1]
    last_val = collaterals[-1][1]
    change = last_val - first_val

    print(f"  Start: {first_val:,.0f} JPY ({collaterals[0][0][:19]})")
    print(f"  End:   {last_val:,.0f} JPY ({collaterals[-1][0][:19]})")
    print(f"  Change: {change:+,.0f} JPY ({change/first_val*100:+.3f}%)")

    # Min/Max
    vals = [c[1] for c in collaterals]
    print(f"  Min: {min(vals):,.0f} JPY, Max: {max(vals):,.0f} JPY")


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Analyze bot metrics and trades")
    parser.add_argument("--date", help="Date to analyze (YYYY-MM-DD)", default=None)
    parser.add_argument("--fetch", action="store_true", help="Force fetch from VPS")
    parser.add_argument("--dates", action="store_true", help="List available dates")
    args = parser.parse_args()

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

    date = args.date or datetime.now(JST).strftime("%Y-%m-%d")
    print(f"Analyzing data for: {date}")

    metrics = get_data("metrics", date, force_fetch=args.fetch)
    trades = get_data("trades", date, force_fetch=args.fetch)

    if not metrics and not trades:
        print("\nNo data available. Use --fetch to download from VPS.")
        print(f"  export VPS_PASS=yourpass && python scripts/analyze_metrics.py --fetch --date {date}")
        return

    if metrics:
        print(f"\nMetrics: {len(metrics)} data points")
        analyze_bayesian_fix(metrics)
        analyze_spread_selection(metrics)
        analyze_ev(metrics)
        analyze_volatility(metrics)
        analyze_positions(metrics)
        analyze_pnl_trend(metrics)

    if trades:
        print(f"\nTrades: {len(trades)} events")
        analyze_fill_rate(trades)

    print("\n" + "=" * 50)
    print("Analysis complete.")


if __name__ == "__main__":
    main()
