"""Hyperliquid Funding Rate Monitor.

Monitors all perpetual pairs for extreme funding rates.
Logs observations to daily CSV (no paper trading).

Outputs:
  scripts/data_cache/hl_fr_snapshots_{date}.csv   — extreme FR snapshots

Usage:
    python3 scripts/hl_fr_monitor.py                    # default: poll every 5 min
    caffeinate -i python3 scripts/hl_fr_monitor.py      # prevent Mac sleep
    python3 scripts/hl_fr_monitor.py --interval 60      # poll every 60s
    python3 scripts/hl_fr_monitor.py --report            # show summary of collected data
"""
import argparse
import csv
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "data_cache"
CACHE_DIR.mkdir(exist_ok=True)

FR_THRESHOLD = 0.001  # 0.1% per 8h
HL_API_URL = "https://api.hyperliquid.xyz/info"


def api_post(body: dict) -> object:
    """POST to Hyperliquid info API and return parsed JSON."""
    req = urllib.request.Request(
        HL_API_URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def load_perp_meta() -> list[str]:
    """Return list of perp pair names from Hyperliquid meta endpoint."""
    data = api_post({"type": "meta"})
    # Response: [{"universe": [{"name": "ETH", ...}, ...]}]
    universe = data[0].get("universe", []) if isinstance(data, list) else data.get("universe", [])
    return [coin["name"] for coin in universe]


def get_all_funding_rates(pair_names: list[str]) -> list[dict]:
    """Return list of dicts with FR and market data for all pairs.

    Each dict contains: symbol, funding_rate, mark_price, oracle_price,
    open_interest, volume_24h.
    """
    data = api_post({"type": "metaAndAssetCtxs"})
    # Response: [meta_dict, [asset_ctx_1, asset_ctx_2, ...]]
    asset_ctxs = data[1] if isinstance(data, list) and len(data) > 1 else []

    results = []
    for i, ctx in enumerate(asset_ctxs):
        if i >= len(pair_names):
            break
        name = pair_names[i]
        results.append({
            "symbol": name,
            "funding_rate": float(ctx.get("funding", 0)),
            "mark_price": float(ctx.get("markPx", 0)),
            "oracle_price": float(ctx.get("oraclePx", 0)),
            "open_interest": float(ctx.get("openInterest", 0)),
            "volume_24h": float(ctx.get("dayNtlVlm", 0)),
        })
    return results


def write_snapshot(rates: list[dict]) -> int:
    """Write extreme FR entries to daily CSV. Returns count written."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    path = CACHE_DIR / f"hl_fr_snapshots_{date_str}.csv"

    is_new = not path.exists() or path.stat().st_size == 0

    count = 0
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow([
                "timestamp", "symbol", "funding_rate", "annualized",
                "volume_24h", "open_interest", "hedge_status",
                "mark_price", "oracle_price",
            ])

        for r in rates:
            fr = r["funding_rate"]
            if abs(fr) < FR_THRESHOLD:
                continue

            annualized = fr * 3 * 365 * 100
            writer.writerow([
                now.isoformat(),
                r["symbol"],
                f"{fr:.6f}",
                f"{annualized:.1f}",
                f"{r['volume_24h']:.0f}",
                f"{r['open_interest']:.4f}",
                "UNKNOWN",
                f"{r['mark_price']}",
                f"{r['oracle_price']}",
            ])
            count += 1

    return count


def report():
    """Show summary of all collected Hyperliquid FR data."""
    print("=" * 60)
    print("Hyperliquid FR Monitor Report")
    print("=" * 60)

    snapshots = sorted(CACHE_DIR.glob("hl_fr_snapshots_*.csv"))
    if not snapshots:
        print("\n  No data collected yet.")
        print(f"  Expected path: {CACHE_DIR}/hl_fr_snapshots_YYYY-MM-DD.csv")
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
    parser = argparse.ArgumentParser(description="Hyperliquid FR Monitor")
    parser.add_argument("--interval", type=int, default=300, help="Poll interval in seconds")
    parser.add_argument("--report", action="store_true", help="Show report and exit")
    args = parser.parse_args()

    if args.report:
        report()
        return

    print("=" * 60)
    print("Hyperliquid Funding Rate Monitor")
    print(f"  Threshold: |FR| > {FR_THRESHOLD*100:.1f}%/8h")
    print(f"  Poll interval: {args.interval}s")
    print(f"  Output: {CACHE_DIR}/hl_fr_snapshots_*.csv")
    print("=" * 60)

    print("\nLoading perp metadata...")
    pair_names = load_perp_meta()
    print(f"  Total perps: {len(pair_names)}")

    poll_count = 0
    print("\nMonitoring... (Ctrl+C to stop)\n")

    try:
        while True:
            try:
                rates = get_all_funding_rates(pair_names)
                extreme_count = write_snapshot(rates)

                poll_count += 1
                now = datetime.now(timezone.utc).strftime("%H:%M:%S")
                print(
                    f"  [{now}] #{poll_count}: extreme={extreme_count}, "
                    f"total_pairs={len(rates)}"
                )

                # Refresh perp list every 100 polls
                if poll_count % 100 == 0:
                    pair_names = load_perp_meta()
                    print(f"  [refresh] perp list updated: {len(pair_names)} pairs")

            except Exception as e:
                print(f"  ERROR: {e}")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\nStopped after {poll_count} polls.")


if __name__ == "__main__":
    main()
