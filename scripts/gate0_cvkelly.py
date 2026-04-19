"""Case C: Gate 0 dedup + CV-adjusted Kelly sizing.

Step 1 (Gate 0): deduplicate snapshot CSVs by (timestamp, symbol).
                 Duplicates arise when watchdog restarts at the same poll time.

Step 2 (CV Kelly): re-weight paper-trade P&L by per-coin CV of FR entry.
                   High CV → smaller position → lower weight in aggregate Sharpe.
                   Tests whether top-2 concentration (49%) drops and Sharpe rises.

Usage:
    python3 scripts/gate0_cvkelly.py
"""
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "data_cache"
PAPER = CACHE_DIR / "fr_paper_trades.csv"


def gate0_dedup():
    """Report and dedup snapshot CSVs. Writes *_dedup.csv alongside originals."""
    print("=== Gate 0: Snapshot dedup ===")
    patterns = [
        ("Bitget", "fr_snapshots_*.csv"),
        ("MEXC", "mexc_fr_snapshots_*.csv"),
        ("Hyperliquid", "hl_fr_snapshots_*.csv"),
    ]
    total_before, total_after = 0, 0
    for label, pattern in patterns:
        before_sum, after_sum = 0, 0
        for path in sorted(CACHE_DIR.glob(pattern)):
            if path.stem.endswith("_dedup"):
                continue
            with open(path) as f:
                rows = list(csv.DictReader(f))
            before = len(rows)
            seen = set()
            dedup_rows = []
            for r in rows:
                key = (r["timestamp"], r["symbol"])
                if key in seen:
                    continue
                seen.add(key)
                dedup_rows.append(r)
            after = len(dedup_rows)
            before_sum += before
            after_sum += after
            dup = before - after
            if dup > 0:
                print(f"  {path.name}: {before} → {after}  (dup={dup}, {dup/before*100:.1f}%)")
        total_before += before_sum
        total_after += after_sum
        print(f"  {label:<12} total: {before_sum} → {after_sum}  (dup={before_sum - after_sum})")
    print(f"  GRAND TOTAL: {total_before} → {total_after}  (dup={total_before - total_after}, "
          f"{(total_before - total_after)/total_before*100:.2f}%)")


def parse_note(note: str) -> dict:
    parts = {}
    for kv in note.split(", "):
        if "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        parts[k.strip()] = float(v.replace("$", "").strip())
    return parts


def erf_norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def inv_norm(p):
    a = [-39.69683028665376, 220.9460984245205, -275.9285104469687,
         138.3577518672690, -30.66479806614716, 2.506628277459239]
    b = [-54.47609879822406, 161.5858368580409, -155.6989798598866,
         66.80131188771972, -13.28068155288572]
    c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838,
         -2.549732539343734, 4.374664141464968, 2.938163982698783]
    d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996,
         3.754408661907416]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p <= ph:
        q = p - 0.5
        r = q * q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def dsr(pnls, n_trials=10, sr_var=0.25):
    n = len(pnls)
    if n < 2:
        return None
    m = statistics.mean(pnls)
    s = statistics.stdev(pnls)
    if s == 0:
        return None
    sr = m / s
    ps = statistics.pstdev(pnls)
    if ps == 0:
        return None
    skew = sum((p - m) ** 3 for p in pnls) / (n * ps ** 3)
    kurt = sum((p - m) ** 4 for p in pnls) / (n * ps ** 4)
    denom = math.sqrt(max(1e-9, 1 - skew * sr + ((kurt - 1) / 4) * sr ** 2))
    psr = erf_norm_cdf(sr * math.sqrt(n - 1) / denom)
    euler = 0.5772156649
    sr_star = math.sqrt(sr_var) * ((1 - euler) * inv_norm(1 - 1/n_trials) + euler * inv_norm(1 - 1/(n_trials * math.e)))
    dsr_val = erf_norm_cdf((sr - sr_star) * math.sqrt(n - 1) / denom)
    return {"n": n, "sr": sr, "psr": psr, "dsr": dsr_val, "sr_star": sr_star,
            "mean": m, "std": s, "skew": skew, "kurt": kurt}


def cv_kelly_reweight():
    """Apply CV-adjusted Kelly sizing retroactively.

    CV is computed per-coin from the spread of its paper P&L values.
    Weight_i = (1 - normalized_CV_i). Renormalize so total notional is preserved.
    """
    print("\n=== CV-adjusted Kelly reweight ===")
    rows = list(csv.DictReader(open(PAPER)))
    closes = [r for r in rows if r["action"] == "CLOSE"]
    if not closes:
        print("  No closed trades")
        return

    # Baseline
    base = [float(r["pnl"]) for r in closes]
    base_stats = dsr(base)
    print(f"Baseline (flat size $24):")
    print(f"  n={base_stats['n']}  Total=${sum(base):.2f}  mean=${sum(base)/len(base):.3f}  "
          f"SR={base_stats['sr']:.3f}  DSR={base_stats['dsr']:.3f} (SR*={base_stats['sr_star']:.3f})")

    # Per-coin CV
    per_coin = defaultdict(list)
    for r in closes:
        per_coin[r["symbol"]].append(float(r["pnl"]))
    coin_cv = {}
    for coin, pnls in per_coin.items():
        if len(pnls) >= 2:
            m = statistics.mean(pnls)
            s = statistics.stdev(pnls)
            # CV normalized by typical size $24
            cv = s / 24.0
        else:
            # Single trade: use |pnl|/size as proxy "volatility"
            cv = abs(pnls[0]) / 24.0
        coin_cv[coin] = cv

    # Normalize CV to [0, 1]
    if not coin_cv:
        return
    cv_vals = list(coin_cv.values())
    cv_min, cv_max = min(cv_vals), max(cv_vals)
    if cv_max == cv_min:
        # All equal → CV Kelly has no effect
        print("  All CVs equal — CV Kelly no-op")
        return
    coin_weight = {c: max(0.01, 1 - (cv - cv_min) / (cv_max - cv_min)) for c, cv in coin_cv.items()}

    # Renormalize so total notional preserved (mean weight = 1)
    w_mean = sum(coin_weight.values()) / len(coin_weight)
    coin_weight = {c: w / w_mean for c, w in coin_weight.items()}

    # Apply to P&L
    weighted = []
    for r in closes:
        w = coin_weight.get(r["symbol"], 1.0)
        weighted.append(float(r["pnl"]) * w)

    w_stats = dsr(weighted)
    print(f"\nCV-Kelly weighted (normalized):")
    print(f"  n={w_stats['n']}  Total=${sum(weighted):.2f}  mean=${sum(weighted)/len(weighted):.3f}  "
          f"SR={w_stats['sr']:.3f}  DSR={w_stats['dsr']:.3f} (SR*={w_stats['sr_star']:.3f})")

    # Top-2 concentration
    base_sorted = sorted(base, reverse=True)
    w_sorted = sorted(weighted, reverse=True)
    base_top2 = sum(base_sorted[:2]) / sum(base) if sum(base) != 0 else 0
    w_top2 = sum(w_sorted[:2]) / sum(weighted) if sum(weighted) != 0 else 0
    print(f"\nTop-2 concentration:")
    print(f"  Baseline:   {base_top2*100:.1f}%")
    print(f"  CV-Kelly:   {w_top2*100:.1f}%")
    print(f"  Change:     {(w_top2 - base_top2)*100:+.1f}pt")

    # Show weights
    print(f"\nPer-coin weight (first 20 by weight desc):")
    for coin, w in sorted(coin_weight.items(), key=lambda kv: -kv[1])[:20]:
        n = len(per_coin[coin])
        cv = coin_cv[coin]
        print(f"  {coin:<14}  n={n:>2}  CV={cv:.2f}  weight={w:.3f}")

    # Composite projection with multi-exchange idea (from Case A)
    if w_stats["sr"] >= base_stats["sr"]:
        print(f"\n→ CV-Kelly improved Sharpe: {base_stats['sr']:.3f} → {w_stats['sr']:.3f} (+{w_stats['sr'] - base_stats['sr']:.3f})")
    else:
        print(f"\n→ CV-Kelly degraded Sharpe: {base_stats['sr']:.3f} → {w_stats['sr']:.3f}")


def cluster_dedup_paper():
    """Cluster paper-trade duplicates caused by overlapping monitor instances.

    Rule: group CLOSE rows by (symbol, direction) where successive timestamps
    are within 30 seconds of each other. Keep ONE representative (the one with
    the median pnl, to be conservative).
    """
    from datetime import datetime
    print("\n=== Cluster dedup of paper trades ===")
    rows = list(csv.DictReader(open(PAPER)))
    closes = [r for r in rows if r["action"] == "CLOSE"]
    if not closes:
        print("  No closes")
        return

    # Sort by symbol/direction/timestamp
    closes_sorted = sorted(closes, key=lambda r: (r["symbol"], r["direction"], r["timestamp"]))

    clusters = []
    cur = [closes_sorted[0]]
    for prev, nxt in zip(closes_sorted, closes_sorted[1:]):
        same_key = prev["symbol"] == nxt["symbol"] and prev["direction"] == nxt["direction"]
        t1 = datetime.fromisoformat(prev["timestamp"])
        t2 = datetime.fromisoformat(nxt["timestamp"])
        dt = (t2 - t1).total_seconds()
        if same_key and dt < 30:
            cur.append(nxt)
        else:
            clusters.append(cur)
            cur = [nxt]
    clusters.append(cur)

    phantom = sum(len(c) - 1 for c in clusters)
    print(f"  Original CLOSEs:   {len(closes)}")
    print(f"  Clusters (logical): {len(clusters)}")
    print(f"  Phantom duplicates: {phantom}  ({phantom/len(closes)*100:.1f}%)")

    # Pick representative: median pnl within cluster
    dedup_closes = []
    for c in clusters:
        if len(c) == 1:
            dedup_closes.append(c[0])
            continue
        # sort by pnl, pick median
        s = sorted(c, key=lambda r: float(r["pnl"]))
        dedup_closes.append(s[len(s) // 2])

    pnls = [float(r["pnl"]) for r in dedup_closes]
    stats = dsr(pnls)
    print(f"\nDedup closes:")
    print(f"  n={stats['n']}  Total=${sum(pnls):.2f}  mean=${sum(pnls)/len(pnls):.3f}  "
          f"SR={stats['sr']:.3f}  DSR={stats['dsr']:.3f} (SR*={stats['sr_star']:.3f})")
    wins = sum(1 for p in pnls if p > 0)
    print(f"  Win rate: {wins}/{len(pnls)} = {wins/len(pnls)*100:.0f}%")

    sorted_pnls = sorted(pnls, reverse=True)
    if sum(pnls) > 0:
        top2 = sum(sorted_pnls[:2]) / sum(pnls)
        print(f"  Top-2 concentration: {top2*100:.1f}%")

    # By direction
    long_pnls = [float(r["pnl"]) for r in dedup_closes if r["direction"] == "LONG"]
    short_pnls = [float(r["pnl"]) for r in dedup_closes if r["direction"] == "SHORT"]
    print(f"\n  LONG  n={len(long_pnls)}  sum=${sum(long_pnls):+.2f}  mean=${statistics.mean(long_pnls) if long_pnls else 0:+.3f}  "
          f"win={sum(1 for p in long_pnls if p > 0)}/{len(long_pnls)}")
    print(f"  SHORT n={len(short_pnls)} sum=${sum(short_pnls):+.2f}  mean=${statistics.mean(short_pnls) if short_pnls else 0:+.3f}  "
          f"win={sum(1 for p in short_pnls if p > 0)}/{len(short_pnls)}")

    return dedup_closes


if __name__ == "__main__":
    gate0_dedup()
    cv_kelly_reweight()
    cluster_dedup_paper()
