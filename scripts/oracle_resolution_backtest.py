"""Case B: Oracle Resolution backtest on Hyperliquid (no lookahead).

Hypothesis: when perp mark_price diverges from oracle_price, the gap mean-reverts.
- gap_t = (mark_t - oracle_t) / oracle_t
- If gap > threshold: SHORT perp (expect mark to fall to oracle)
- If gap < -threshold: LONG perp (expect mark to rise to oracle)

Strict no-lookahead rule:
- Entry decision at time t uses ONLY snapshot at time t.
- Exit at the very next snapshot of the same symbol (no peeking further).
- Realized P&L from actual mark_price change between t and t+1.

Usage:
    python3 scripts/oracle_resolution_backtest.py
    python3 scripts/oracle_resolution_backtest.py --threshold 0.005
"""
import argparse
import csv
import math
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "data_cache"


def load_hl():
    """Load all HL snapshots, dedup by (symbol, timestamp)."""
    rows = []
    for path in sorted(CACHE_DIR.glob("hl_fr_snapshots_*.csv")):
        with open(path) as f:
            for r in csv.DictReader(f):
                try:
                    rows.append({
                        "symbol": r["symbol"],
                        "ts": datetime.fromisoformat(r["timestamp"]),
                        "fr": float(r["funding_rate"]),
                        "mark": float(r["mark_price"]),
                        "oracle": float(r["oracle_price"]),
                    })
                except (ValueError, KeyError):
                    continue
    # Dedup: (symbol, ts) keeps first
    seen = set()
    out = []
    for r in rows:
        k = (r["symbol"], r["ts"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return sorted(out, key=lambda r: (r["symbol"], r["ts"]))


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


def dsr(rets, n_trials=10, sr_var=0.25):
    n = len(rets)
    if n < 2:
        return None
    m = statistics.mean(rets)
    s = statistics.stdev(rets)
    if s == 0:
        return None
    sr = m / s
    ps = statistics.pstdev(rets)
    skew = sum((r - m) ** 3 for r in rets) / (n * ps ** 3) if ps > 0 else 0
    kurt = sum((r - m) ** 4 for r in rets) / (n * ps ** 4) if ps > 0 else 3
    denom = math.sqrt(max(1e-9, 1 - skew * sr + ((kurt - 1) / 4) * sr ** 2))
    psr = erf_norm_cdf(sr * math.sqrt(n - 1) / denom)
    euler = 0.5772156649
    sr_star = math.sqrt(sr_var) * ((1 - euler) * inv_norm(1 - 1/n_trials) + euler * inv_norm(1 - 1/(n_trials * math.e)))
    dsr_val = erf_norm_cdf((sr - sr_star) * math.sqrt(n - 1) / denom)
    return {"n": n, "sr": sr, "psr": psr, "dsr": dsr_val, "sr_star": sr_star,
            "mean": m, "std": s, "skew": skew, "kurt": kurt}


def simulate(rows, threshold, max_hold_min, taker_bps):
    """Run strict forward simulation. Returns list of trade returns (after fees)."""
    # Group by symbol, preserving temporal order
    by_sym = defaultdict(list)
    for r in rows:
        by_sym[r["symbol"]].append(r)

    trades = []
    for sym, snaps in by_sym.items():
        # Only pair adjacent snapshots
        for i in range(len(snaps) - 1):
            entry = snaps[i]
            exit_ = snaps[i + 1]
            dt_min = (exit_["ts"] - entry["ts"]).total_seconds() / 60
            if dt_min > max_hold_min:
                # Too long a gap — skip (no confident exit window)
                continue
            if entry["oracle"] <= 0:
                continue
            gap = (entry["mark"] - entry["oracle"]) / entry["oracle"]
            if abs(gap) < threshold:
                continue
            # Entry decision: only uses entry's own fields
            direction = "SHORT" if gap > 0 else "LONG"
            # Exit P&L: realized mark_price change (not using exit's gap)
            price_return = (exit_["mark"] - entry["mark"]) / entry["mark"]
            if direction == "SHORT":
                price_return = -price_return
            # Taker fees both sides
            net = price_return - 2 * (taker_bps / 10000)
            trades.append({
                "symbol": sym,
                "entry_ts": entry["ts"],
                "exit_ts": exit_["ts"],
                "dt_min": dt_min,
                "direction": direction,
                "gap": gap,
                "raw_return": price_return,
                "net_return": net,
            })
    return trades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.005,
                    help="Min |gap| to enter (e.g. 0.005 = 0.5%%)")
    ap.add_argument("--max-hold-min", type=float, default=20.0,
                    help="Skip if next snapshot >X min away")
    ap.add_argument("--taker-bps", type=float, default=4.5,
                    help="HL taker fee (round trip applied as 2x)")
    args = ap.parse_args()

    rows = load_hl()
    symbols = {r["symbol"] for r in rows}
    print(f"Loaded {len(rows)} HL snapshots ({len(symbols)} symbols)")
    print(f"Threshold: |gap| > {args.threshold*100:.2f}%   Max hold: {args.max_hold_min} min   "
          f"Taker fee: {args.taker_bps} bps/side")
    print()

    trades = simulate(rows, args.threshold, args.max_hold_min, args.taker_bps)
    if not trades:
        print("No trades triggered.")
        return

    nets = [t["net_return"] for t in trades]
    raws = [t["raw_return"] for t in trades]
    longs = [t for t in trades if t["direction"] == "LONG"]
    shorts = [t for t in trades if t["direction"] == "SHORT"]

    stats = dsr(nets)
    print(f"=== Results (all trades) ===")
    print(f"  n trades: {len(trades)}")
    print(f"  Σ raw ret:  {sum(raws)*100:+.2f}%  (before fees)")
    print(f"  Σ net ret:  {sum(nets)*100:+.2f}%")
    print(f"  mean net:   {statistics.mean(nets)*100:+.4f}%")
    print(f"  std net:    {statistics.stdev(nets)*100:.4f}%")
    print(f"  Sharpe (per-trade): {stats['sr']:.3f}")
    print(f"  DSR:              {stats['dsr']:.4f}  (SR*={stats['sr_star']:.3f})")
    win = sum(1 for n in nets if n > 0)
    print(f"  Win rate:   {win}/{len(nets)} = {win/len(nets)*100:.1f}%")
    print()

    # By direction
    for label, trs in [("LONG", longs), ("SHORT", shorts)]:
        if not trs:
            continue
        n_net = [t["net_return"] for t in trs]
        w = sum(1 for r in n_net if r > 0)
        s_d = dsr(n_net) or {"sr": 0, "dsr": 0}
        print(f"  {label:<5}  n={len(trs)}  Σ={sum(n_net)*100:+.2f}%  mean={statistics.mean(n_net)*100:+.4f}%  "
              f"SR={s_d['sr']:.3f}  win={w}/{len(trs)}")

    # By symbol (top 5)
    print()
    by_sym = defaultdict(list)
    for t in trades:
        by_sym[t["symbol"]].append(t["net_return"])
    ranked = sorted(by_sym.items(), key=lambda kv: -sum(kv[1]))
    print("  Per-symbol (by Σ net):")
    for sym, nets_s in ranked:
        w = sum(1 for r in nets_s if r > 0)
        print(f"    {sym:<10}  n={len(nets_s):>3}  Σ={sum(nets_s)*100:+.3f}%  mean={statistics.mean(nets_s)*100:+.4f}%  win={w}/{len(nets_s)}")

    # Sensitivity: also test threshold doubling / halving
    print()
    print("=== Threshold sensitivity ===")
    for th in [0.002, 0.005, 0.010, 0.020, 0.050]:
        t2 = simulate(rows, th, args.max_hold_min, args.taker_bps)
        if not t2:
            print(f"  th={th*100:.2f}%   n=0")
            continue
        n2 = [t["net_return"] for t in t2]
        s2 = dsr(n2)
        if s2 is None:
            print(f"  th={th*100:.2f}%   n={len(n2)}  (too few)")
            continue
        print(f"  th={th*100:.2f}%   n={len(n2):>4}  Σ={sum(n2)*100:+7.2f}%  "
              f"mean={statistics.mean(n2)*100:+.4f}%  SR={s2['sr']:+.3f}  DSR={s2['dsr']:.4f}")


if __name__ == "__main__":
    main()
