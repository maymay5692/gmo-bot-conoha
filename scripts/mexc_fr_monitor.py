"""MEXC Funding Rate Monitor.

Monitors all perpetual pairs for extreme funding rates.
Logs observations to daily CSV (no paper trading).

Outputs:
  scripts/data_cache/mexc_fr_snapshots_{date}.csv   — extreme FR snapshots

Usage:
    python3 scripts/mexc_fr_monitor.py                    # default: poll every 5 min
    caffeinate -i python3 scripts/mexc_fr_monitor.py      # prevent Mac sleep
    python3 scripts/mexc_fr_monitor.py --interval 60      # poll every 60s
    python3 scripts/mexc_fr_monitor.py --report            # show summary of collected data
"""
import argparse
import csv
import json
import ssl
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "data_cache"
CACHE_DIR.mkdir(exist_ok=True)

FR_THRESHOLD = 0.001  # 0.1% per 8h
MEXC_API_URL = "https://contract.mexc.com"


_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def api_get(path: str) -> object:
    """GET from MEXC contract API and return parsed JSON."""
    url = f"{MEXC_API_URL}/{path}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "mexc-fr-monitor/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
        return json.loads(resp.read())


def get_all_tickers() -> list[dict]:
    """Return list of ticker dicts from MEXC ticker endpoint."""
    data = api_get("api/v1/contract/ticker")
    return data.get("data", [])


def parse_tickers(tickers: list[dict]) -> list[dict]:
    """Return list of dicts with FR and market data for all pairs.

    Each dict contains: symbol, funding_rate, last_price,
    open_interest, volume_24h, bid1, ask1.
    """
    results = []
    for t in tickers:
        try:
            results.append({
                "symbol": t.get("symbol", ""),
                "funding_rate": float(t.get("fundingRate", 0) or 0),
                "last_price": float(t.get("lastPrice", 0) or 0),
                "open_interest": float(t.get("openInterest", 0) or 0),
                "volume_24h": float(t.get("volume24", 0) or 0),
                "bid1": float(t.get("bid1", 0) or 0),
                "ask1": float(t.get("ask1", 0) or 0),
            })
        except (ValueError, TypeError):
            continue
    return results


def write_snapshot(rates: list[dict]) -> int:
    """Write extreme FR entries to daily CSV. Returns count written."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    path = CACHE_DIR / f"mexc_fr_snapshots_{date_str}.csv"

    is_new = not path.exists() or path.stat().st_size == 0

    count = 0
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow([
                "timestamp", "symbol", "funding_rate", "annualized",
                "volume_24h", "open_interest", "hedge_status",
                "last_price", "spread",
            ])

        for r in rates:
            fr = r["funding_rate"]
            if abs(fr) < FR_THRESHOLD:
                continue

            annualized = fr * 3 * 365 * 100
            bid1 = r["bid1"]
            ask1 = r["ask1"]
            spread = f"{ask1 - bid1:.6f}" if bid1 and ask1 else "0"

            writer.writerow([
                now.isoformat(),
                r["symbol"],
                f"{fr:.6f}",
                f"{annualized:.1f}",
                f"{r['volume_24h']:.0f}",
                f"{r['open_interest']:.4f}",
                "UNKNOWN",
                f"{r['last_price']}",
                spread,
            ])
            count += 1

    return count


def report():
    """Show summary of all collected MEXC FR data."""
    print("=" * 60)
    print("MEXC FR Monitor Report")
    print("=" * 60)

    snapshots = sorted(CACHE_DIR.glob("mexc_fr_snapshots_*.csv"))
    if not snapshots:
        print("\n  No data collected yet.")
        print(f"  Expected path: {CACHE_DIR}/mexc_fr_snapshots_YYYY-MM-DD.csv")
        return

    total_rows = 0
    for path in snapshots:
        with open(path) as f:
            rows = sum(1 for _ in f) - 1  # minus header
        total_rows += rows
        print(f"  {path.name}: {rows} extreme FR observations")

    print(f"\n  Total observations: {total_rows}")

    # Analyze latest file
    latest = snapshots[-1]
    with open(latest) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if rows:
        symbols = {r["symbol"] for r in rows}
        frs = [abs(float(r["funding_rate"])) for r in rows]
        print(f"\n  Latest file ({latest.name}):")
        print(f"    Unique tokens with extreme FR: {len(symbols)}")
        print(f"    Max |FR|: {max(frs)*100:.3f}%/8h")
        print(f"    Avg |FR|: {sum(frs)/len(frs)*100:.3f}%/8h")
        print(f"    Tokens: {', '.join(sorted(symbols))}")


def main():
    parser = argparse.ArgumentParser(description="MEXC FR Monitor")
    parser.add_argument("--interval", type=int, default=300, help="Poll interval in seconds")
    parser.add_argument("--report", action="store_true", help="Show report and exit")
    args = parser.parse_args()

    if args.report:
        report()
        return

    print("=" * 60)
    print("MEXC Funding Rate Monitor")
    print(f"  Threshold: |FR| > {FR_THRESHOLD*100:.1f}%/8h")
    print(f"  Poll interval: {args.interval}s")
    print(f"  Output: {CACHE_DIR}/mexc_fr_snapshots_*.csv")
    print("=" * 60)

    print("\nLoading ticker data...")
    tickers = get_all_tickers()
    print(f"  Total contracts: {len(tickers)}")

    poll_count = 0
    print("\nMonitoring... (Ctrl+C to stop)\n")

    try:
        while True:
            try:
                tickers = get_all_tickers()
                rates = parse_tickers(tickers)
                extreme_count = write_snapshot(rates)

                poll_count += 1
                now = datetime.now(timezone.utc).strftime("%H:%M:%S")
                print(
                    f"  [{now}] #{poll_count}: extreme={extreme_count}, "
                    f"total_pairs={len(rates)}"
                )

                # Refresh contract list every 100 polls (already fetched fresh each poll,
                # but log it explicitly to match hl_fr_monitor behaviour)
                if poll_count % 100 == 0:
                    print(f"  [refresh] contract list updated: {len(rates)} pairs")

            except Exception as e:
                print(f"  ERROR: {e}")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\nStopped after {poll_count} polls.")


if __name__ == "__main__":
    main()
