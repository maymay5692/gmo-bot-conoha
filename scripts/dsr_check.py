"""DSR check for FR paper trades.

Applies Gate 1 of 3-Gate Review to scripts/data_cache/fr_paper_trades.csv.

Metrics:
  - Sharpe (trade-based, not time-based)
  - PSR  (Probabilistic SR, Bailey & Lopez de Prado 2012)
  - DSR  (Deflated SR, with configurable N trials)
  - Concentration penalty (top-2 contribution to total P&L)
  - IS/OOS split gate (Gate 3 preview)

Usage:
    python3 scripts/dsr_check.py
    python3 scripts/dsr_check.py --n-trials 20
    python3 scripts/dsr_check.py --is-until 2026-04-13
"""
import argparse
import csv
import math
import statistics
from pathlib import Path
from datetime import datetime

PAPER_TRADES = Path(__file__).parent / "data_cache" / "fr_paper_trades.csv"
SR_BENCHMARK = 0.0
EULER_MASCHERONI = 0.5772156649


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_inv_cdf(p: float) -> float:
    # Beasley-Springer-Moro approximation
    if p <= 0.0 or p >= 1.0:
        raise ValueError("p out of range")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl = 0.02425
    ph = 1 - pl
    if p < pl:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p <= ph:
        q = p - 0.5
        r = q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2.0 * math.log(1 - p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def skewness(xs):
    n = len(xs)
    if n < 3:
        return 0.0
    m = statistics.mean(xs)
    s = statistics.pstdev(xs)
    if s == 0:
        return 0.0
    return sum((x - m) ** 3 for x in xs) / (n * s ** 3)


def kurtosis(xs):
    n = len(xs)
    if n < 4:
        return 3.0
    m = statistics.mean(xs)
    s = statistics.pstdev(xs)
    if s == 0:
        return 3.0
    return sum((x - m) ** 4 for x in xs) / (n * s ** 4)


def probabilistic_sr(sr, n, skew, kurt, sr_benchmark=0.0):
    """PSR: P(true SR > sr_benchmark | observed SR = sr)."""
    if n <= 1:
        return 0.0
    denom = math.sqrt(1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr)
    if denom <= 0:
        return 0.0
    z = (sr - sr_benchmark) * math.sqrt(n - 1) / denom
    return norm_cdf(z)


def deflated_sr_threshold(n_trials, sr_variance):
    """Expected max SR across N independent trials with given SR variance."""
    if n_trials <= 1:
        return 0.0
    sigma_sr = math.sqrt(sr_variance)
    gamma = EULER_MASCHERONI
    term1 = (1.0 - gamma) * norm_inv_cdf(1.0 - 1.0 / n_trials)
    term2 = gamma * norm_inv_cdf(1.0 - 1.0 / (n_trials * math.e))
    return sigma_sr * (term1 + term2)


def deflated_sr(sr, n_obs, skew, kurt, n_trials, sr_variance):
    """DSR: PSR with benchmark replaced by expected max SR of N trials."""
    sr_star = deflated_sr_threshold(n_trials, sr_variance)
    return probabilistic_sr(sr, n_obs, skew, kurt, sr_benchmark=sr_star), sr_star


def load_closes(path):
    rows = list(csv.DictReader(open(path)))
    return [r for r in rows if r["action"] == "CLOSE"]


def analyze(closes, label):
    pnls = [float(r["pnl"]) for r in closes]
    n = len(pnls)
    if n < 2:
        print(f"{label}: n={n} (too few)")
        return None
    m = statistics.mean(pnls)
    s = statistics.stdev(pnls)
    sr = m / s if s > 0 else 0.0
    sk = skewness(pnls)
    kt = kurtosis(pnls)
    wins = sum(1 for p in pnls if p > 0)
    total = sum(pnls)
    # top-2 concentration
    sorted_pnls = sorted(pnls, reverse=True)
    top2 = sum(sorted_pnls[:2])
    conc = top2 / total if total != 0 else 0
    return {
        "label": label, "n": n, "total": total, "mean": m, "std": s,
        "sr": sr, "skew": sk, "kurt": kt, "wins": wins,
        "concentration_top2": conc,
        "pnls": pnls,
    }


def fmt(stats, n_trials=10, sr_trial_var=0.25):
    if stats is None:
        return
    s = stats
    psr = probabilistic_sr(s["sr"], s["n"], s["skew"], s["kurt"])
    dsr, sr_star = deflated_sr(s["sr"], s["n"], s["skew"], s["kurt"], n_trials, sr_trial_var)
    # concentration-adjusted: remove top-2 and recompute
    sorted_pnls = sorted(s["pnls"], reverse=True)
    trimmed = sorted_pnls[2:]
    if len(trimmed) >= 2:
        m2 = statistics.mean(trimmed)
        s2 = statistics.stdev(trimmed)
        sr_trim = m2 / s2 if s2 > 0 else 0.0
        total_trim = sum(trimmed)
    else:
        sr_trim, total_trim = 0.0, 0.0

    print(f"=== {s['label']} ===")
    print(f"  n             : {s['n']}")
    print(f"  Total P&L     : ${s['total']:.2f}")
    print(f"  Mean/trade    : ${s['mean']:.3f}")
    print(f"  Std/trade     : ${s['std']:.3f}")
    print(f"  Sharpe (trade): {s['sr']:.3f}")
    print(f"  Skewness      : {s['skew']:.3f}")
    print(f"  Kurtosis      : {s['kurt']:.3f}  (excess={s['kurt']-3:.3f})")
    print(f"  Win rate      : {s['wins']}/{s['n']} = {s['wins']/s['n']*100:.1f}%")
    print(f"  PSR           : {psr:.4f}  (gate: >= 0.95)")
    print(f"  DSR           : {dsr:.4f}  (gate: >= 0.95, N_trials={n_trials}, sigma_SR^2={sr_trial_var})")
    print(f"  SR* (threshold): {sr_star:.3f}")
    print(f"  Top-2 concentration: {s['concentration_top2']*100:.1f}% of total")
    print(f"  Without top-2:  n={len(trimmed)}, total=${total_trim:.2f}, SR_trim={sr_trim:.3f}")
    # verdict
    gate1_pass = (psr >= 0.95) and (dsr >= 0.95)
    verdict = "PASS" if gate1_pass else "FAIL"
    print(f"  Gate 1 verdict : {verdict}")
    print()
    return dsr, psr, gate1_pass


def split_is_oos(closes, is_until_str):
    is_until = datetime.fromisoformat(is_until_str + "T23:59:59+00:00")
    is_rows, oos_rows = [], []
    for r in closes:
        ts = datetime.fromisoformat(r["timestamp"])
        (is_rows if ts <= is_until else oos_rows).append(r)
    return is_rows, oos_rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=str(PAPER_TRADES))
    ap.add_argument("--n-trials", type=int, default=10,
                    help="Number of strategy variants tried (multi-testing)")
    ap.add_argument("--sr-variance", type=float, default=0.25,
                    help="Variance of SR across trials")
    ap.add_argument("--is-until", default="2026-04-13",
                    help="In-sample ends at YYYY-MM-DD (UTC)")
    args = ap.parse_args()

    closes = load_closes(args.path)
    print(f"Loaded {len(closes)} CLOSE trades from {args.path}")
    print()

    # full
    fmt(analyze(closes, "Full sample"), args.n_trials, args.sr_variance)

    # IS/OOS split
    is_rows, oos_rows = split_is_oos(closes, args.is_until)
    print(f"--- IS/OOS split at {args.is_until} ---")
    print(f"IS={len(is_rows)}, OOS={len(oos_rows)}")
    print()
    fmt(analyze(is_rows, f"IS (<= {args.is_until})"), args.n_trials, args.sr_variance)
    fmt(analyze(oos_rows, f"OOS (> {args.is_until})"), args.n_trials, args.sr_variance)

    # by direction
    longs = [r for r in closes if r["direction"] == "LONG"]
    shorts = [r for r in closes if r["direction"] == "SHORT"]
    print("--- By direction ---")
    fmt(analyze(longs, "LONG only"), args.n_trials, args.sr_variance)
    fmt(analyze(shorts, "SHORT only"), args.n_trials, args.sr_variance)


if __name__ == "__main__":
    main()
