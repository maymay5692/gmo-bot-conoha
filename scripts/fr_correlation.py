"""Case A: Multi-exchange FR correlation analysis.

Loads FR snapshots from Bitget/MEXC/Hyperliquid, normalizes symbols to a
common base-coin key, aligns on 5-minute timestamps, and computes per-coin
FR correlation across exchanges.

Applies FLAM (IR = IC × √N) logic to estimate composite Sharpe upper bound.

Usage:
    python3 scripts/fr_correlation.py
    python3 scripts/fr_correlation.py --since 2026-04-15
"""
import argparse
import csv
import math
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "data_cache"


def normalize_symbol(exchange: str, sym: str) -> str:
    """Normalize to base coin key (e.g. 'ID', 'ZAMA', 'BIO')."""
    if exchange == "bitget":
        if sym.endswith("USDT"):
            return sym[:-4]
        return sym
    if exchange == "mexc":
        # '1000BTT_USDT' → '1000BTT'; 'BIO_USDC' → 'BIO_USDC' (keep quote currency if not USDT)
        if sym.endswith("_USDT"):
            return sym[:-5]
        return sym
    if exchange == "hyperliquid":
        return sym
    return sym


def bucket_5min(iso_ts: str) -> str:
    """Snap timestamp to the nearest 5-minute bucket key 'YYYY-MM-DDTHH:MM'."""
    dt = datetime.fromisoformat(iso_ts)
    minute = (dt.minute // 5) * 5
    return f"{dt.strftime('%Y-%m-%dT%H:')}{minute:02d}"


def load(exchange: str, pattern: str, since_date: str | None):
    """Load all CSVs matching pattern, return dict[(bucket, coin)] -> fr."""
    series: dict[tuple[str, str], float] = {}
    for path in sorted(CACHE_DIR.glob(pattern)):
        # Skip files older than since_date
        if since_date and path.stem.split("_")[-1] < since_date:
            continue
        with open(path) as f:
            reader = csv.DictReader(f)
            for r in reader:
                try:
                    fr = float(r["funding_rate"])
                    coin = normalize_symbol(exchange, r["symbol"])
                    bucket = bucket_5min(r["timestamp"])
                    # If duplicate (bucket,coin), keep the last seen
                    series[(bucket, coin)] = fr
                except (ValueError, KeyError):
                    continue
    return series


def correlation(xs, ys):
    if len(xs) < 3:
        return None
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    sx = statistics.pstdev(xs)
    sy = statistics.pstdev(ys)
    if sx == 0 or sy == 0:
        return None
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)
    return cov / (sx * sy)


def effective_n_flam(correlations):
    """Effective N from FLAM under pairwise correlation.
    If all pairwise rho are equal and N original streams: effective = N / (1 + (N-1)*rho).
    For heterogeneous rhos, use average.
    """
    if not correlations:
        return 1.0
    avg_rho = sum(correlations) / len(correlations)
    n = 3  # 3 exchanges
    if avg_rho <= 0:
        return float(n)
    eff = n / (1 + (n - 1) * avg_rho)
    return max(1.0, eff)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-04-15", help="YYYY-MM-DD earliest file to include")
    args = ap.parse_args()

    print(f"Loading FR snapshots since {args.since}...")
    bitget = load("bitget", "fr_snapshots_*.csv", args.since)
    mexc = load("mexc", "mexc_fr_snapshots_*.csv", args.since)
    hl = load("hyperliquid", "hl_fr_snapshots_*.csv", args.since)
    print(f"  Bitget:       {len(bitget):>6} obs, unique coins: {len({c for _, c in bitget})}")
    print(f"  MEXC:         {len(mexc):>6} obs, unique coins: {len({c for _, c in mexc})}")
    print(f"  Hyperliquid:  {len(hl):>6} obs, unique coins: {len({c for _, c in hl})}")

    # Find common coins across exchanges
    coins_bit = {c for _, c in bitget}
    coins_mex = {c for _, c in mexc}
    coins_hl = {c for _, c in hl}

    tri = coins_bit & coins_mex & coins_hl
    bit_mex = (coins_bit & coins_mex) - coins_hl
    bit_hl = (coins_bit & coins_hl) - coins_mex
    mex_hl = (coins_mex & coins_hl) - coins_bit
    print(f"\nCommon coins (≥2 exchanges):")
    print(f"  all 3:        {sorted(tri)}  (n={len(tri)})")
    print(f"  Bitget+MEXC:  {sorted(bit_mex)[:15]}{'...' if len(bit_mex) > 15 else ''}  (n={len(bit_mex)})")
    print(f"  Bitget+HL:    {sorted(bit_hl)}  (n={len(bit_hl)})")
    print(f"  MEXC+HL:      {sorted(mex_hl)}  (n={len(mex_hl)})")

    # Per-coin correlation for coins in ≥2 exchanges
    print("\n--- Per-coin FR correlation (min 10 aligned buckets) ---")
    corrs_bm, corrs_bh, corrs_mh = [], [], []

    def align(s1, s2, coin):
        b1 = {b for b, c in s1 if c == coin}
        b2 = {b for b, c in s2 if c == coin}
        common = sorted(b1 & b2)
        return [s1[(b, coin)] for b in common], [s2[(b, coin)] for b in common]

    all_pairs_coins = (coins_bit & coins_mex) | (coins_bit & coins_hl) | (coins_mex & coins_hl)
    rows = []
    for coin in sorted(all_pairs_coins):
        row = {"coin": coin}
        if coin in coins_bit and coin in coins_mex:
            xs, ys = align(bitget, mexc, coin)
            row["bm"] = correlation(xs, ys)
            row["bm_n"] = len(xs)
            if row["bm"] is not None and len(xs) >= 10:
                corrs_bm.append(row["bm"])
        if coin in coins_bit and coin in coins_hl:
            xs, ys = align(bitget, hl, coin)
            row["bh"] = correlation(xs, ys)
            row["bh_n"] = len(xs)
            if row["bh"] is not None and len(xs) >= 10:
                corrs_bh.append(row["bh"])
        if coin in coins_mex and coin in coins_hl:
            xs, ys = align(mexc, hl, coin)
            row["mh"] = correlation(xs, ys)
            row["mh_n"] = len(xs)
            if row["mh"] is not None and len(xs) >= 10:
                corrs_mh.append(row["mh"])
        rows.append(row)

    # Print table
    print(f"  {'coin':<12} {'ρ(B-M)':>10} {'n':>5}  {'ρ(B-H)':>10} {'n':>5}  {'ρ(M-H)':>10} {'n':>5}")
    for r in rows:
        def fmt(key):
            v = r.get(key)
            n = r.get(f"{key}_n", 0)
            if v is None:
                return f"{'—':>10} {'—':>5}"
            return f"{v:>10.3f} {n:>5}"
        print(f"  {r['coin']:<12} {fmt('bm')}  {fmt('bh')}  {fmt('mh')}")

    # Aggregate stats
    print("\n--- Aggregate correlation (pairs with n ≥ 10) ---")
    def summary(lst, label):
        if not lst:
            print(f"  {label:<12}  n=0 (no pairs)")
            return
        print(f"  {label:<12}  n_pairs={len(lst):>2}  mean_ρ={sum(lst)/len(lst):+.3f}  "
              f"median_ρ={statistics.median(lst):+.3f}  min={min(lst):+.3f}  max={max(lst):+.3f}")
    summary(corrs_bm, "Bitget-MEXC")
    summary(corrs_bh, "Bitget-HL")
    summary(corrs_mh, "MEXC-HL")

    # FLAM application: estimate composite Sharpe
    all_corrs = corrs_bm + corrs_bh + corrs_mh
    if all_corrs:
        avg_rho = sum(all_corrs) / len(all_corrs)
        eff_n = effective_n_flam(all_corrs)
        print(f"\n--- FLAM composite Sharpe (IR = IC × √N) ---")
        print(f"  Average pairwise ρ:    {avg_rho:+.3f}")
        print(f"  Effective independent streams: {eff_n:.2f} / 3")
        print(f"  Multiplier (√eff_n):   {math.sqrt(eff_n):.3f}")
        single_sharpe = 0.418  # Bitget observed
        composite = single_sharpe * math.sqrt(eff_n)
        sr_star = 0.787
        print(f"  Single-exchange Sharpe: {single_sharpe:.3f}")
        print(f"  Composite Sharpe (est): {composite:.3f}")
        print(f"  SR* (DSR gate):         {sr_star:.3f}")
        verdict = "PASS" if composite >= sr_star else "FAIL"
        print(f"  Gate 1 projected:       {verdict}")
        if composite < sr_star:
            gap = sr_star - composite
            needed_rho = 1 - (3 * (single_sharpe / sr_star) ** 2 - 1) / 2
            print(f"  Gap:                    {gap:+.3f}")
            print(f"  Needed avg_ρ for pass:  ≤ {needed_rho:+.3f}")


if __name__ == "__main__":
    main()
