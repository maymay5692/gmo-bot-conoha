"""DSR check for FR paper trades (enhanced 2026-04-20).

Applies Gate 1 of 3-Gate Review to FR arbitrage paper trades, with:

  - Sharpe / PSR / DSR (trade-based)
  - N_trials multi-scenario (conservative / moderate; both must PASS)
  - Protocol Incentive replay (`--fee-rate` re-computes PnL with new fee)
  - BH-FDR on per-segment Sharpe p-values (advisory)
  - Concentration penalty (top-2 contribution)
  - IS/OOS split
  - Structured JSON output (`--output`) recording trial_count_N and fee params

Input CSV schema (from {bitget,mexc}_fr_monitor.py paper trader):
  timestamp, symbol, action, direction, price, size_usd,
  funding_rate, pnl, hedge_status, note

CLOSE rows use pnl = price_pnl + fr_pnl - (size * orig_fee_rate * 2).
`--fee-rate X` reverses the baked-in fee and applies X instead, enabling
Protocol Incentive replay (e.g. MEXC fee-free pairs → --fee-rate 0).

N_trials operating rules (per wiki/analyses/dsr-protocol-incentive-operations-guide-2026-04-20.md):

  - Universe-fixed basket strategies (same params across many symbols):
    N_trials = parameter-candidate count ONLY. Do NOT include symbol count.
  - Symbol universe MUST be selected ex-ante (objective threshold or pre-declared
    list). Ex-post selection by Sharpe introduces a selection bias; it has to be
    added as a separate `log2(prior_universe/final_universe) + 1` uplift to N.
  - Per-symbol parameter tuning: N = symbol_count * per_symbol_trial_count.
  - EXP_SUMMARY must record: n_params, universe_filter_source (ex-ante|ex-post),
    prior_universe_size, final_universe_size, n_trials_effective.

Protocol Incentive recording rule (analyses Topic 2):

  - Always report BOTH `incentive on` (fee overridden) AND `incentive off`
    (baseline) Sharpe/DSR. The two-scenario record goes into the strategy's
    Gate 2 Tail Safety documentation as a formal artefact.
  - Do NOT bolt the incentive onto an already-computed Sharpe; re-compute from
    the PnL stream. This script's `--fee-rate` implements the correct order.

Usage:
    # Baseline (incentive off)
    python3 scripts/dsr_check.py --path scripts/data_cache/mexc_fr_paper_trades.csv \\
                                 --output /tmp/mexc-gate1-baseline.json

    # Incentive on (fee-free pairs)
    python3 scripts/dsr_check.py --path scripts/data_cache/mexc_fr_paper_trades.csv \\
                                 --fee-rate 0.0 --output /tmp/mexc-gate1-incentive.json

    # Custom trial scenarios
    python3 scripts/dsr_check.py --trial-scenarios 10,50,100
"""
import argparse
import csv
import json
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
    """PSR: P(true SR > sr_benchmark | observed SR = sr).

    Returns a probability in [0, 1]. Bailey & Lopez de Prado (2012).
    """
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


def bh_fdr(p_values):
    """Benjamini-Hochberg FDR adjusted p-values.

    Input: list of raw p-values.
    Output: list of BH-adjusted p-values (same order).
    Monotonicity is enforced from largest rank downward.
    """
    n = len(p_values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: p_values[i])
    adj = [0.0] * n
    prev = 1.0
    for rank_rev in range(n - 1, -1, -1):
        i = order[rank_rev]
        raw = p_values[i] * n / (rank_rev + 1)
        val = min(raw, prev)
        adj[i] = val
        prev = val
    return adj


def load_closes(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if r["action"] == "CLOSE"]


def apply_fee_override(closes, orig_fee_rate, new_fee_rate):
    """Replay PnL with a different fee rate (Protocol Incentive mode).

    The paper-trade CSV was written as:
        pnl = price_pnl + fr_pnl - size_usd * orig_fee_rate * 2

    We reverse out `orig_fee_rate` and apply `new_fee_rate`:
        new_pnl = pnl + size_usd*orig*2 - size_usd*new*2
    """
    if new_fee_rate is None or new_fee_rate == orig_fee_rate:
        return closes
    replayed = []
    for r in closes:
        size = float(r["size_usd"])
        orig_fee = size * orig_fee_rate * 2
        new_fee = size * new_fee_rate * 2
        new_pnl = float(r["pnl"]) + orig_fee - new_fee
        replayed.append({**r, "pnl": f"{new_pnl:.6f}"})
    return replayed


def analyze(closes, label):
    pnls = [float(r["pnl"]) for r in closes]
    n = len(pnls)
    if n < 2:
        return {"label": label, "n": n, "too_few": True}
    m = statistics.mean(pnls)
    s = statistics.stdev(pnls)
    sr = m / s if s > 0 else 0.0
    sk = skewness(pnls)
    kt = kurtosis(pnls)
    wins = sum(1 for p in pnls if p > 0)
    total = sum(pnls)
    sorted_pnls = sorted(pnls, reverse=True)
    top2 = sum(sorted_pnls[:2])
    conc = top2 / total if total != 0 else 0
    return {
        "label": label, "n": n, "total": total, "mean": m, "std": s,
        "sr": sr, "skew": sk, "kurt": kt, "wins": wins,
        "concentration_top2": conc,
        "pnls": pnls,
    }


def dsr_scenarios(stats, trial_scenarios, sr_variance):
    """Compute DSR for each N_trials scenario.

    Returns dict: {N_trials: {"dsr": x, "sr_star": y, "pass": bool}}.
    Gate 1 (Sharpe+DSR) passes iff ALL scenarios pass.
    """
    out = {}
    for n_trials in trial_scenarios:
        dsr, sr_star = deflated_sr(
            stats["sr"], stats["n"], stats["skew"], stats["kurt"],
            n_trials, sr_variance,
        )
        out[n_trials] = {
            "dsr": dsr,
            "sr_star": sr_star,
            "pass": dsr >= 0.95,
        }
    return out


def segment_summary(stats, trial_scenarios, sr_variance):
    """Produce a JSON-serialisable summary for one segment."""
    if stats.get("too_few"):
        return {"label": stats["label"], "n": stats["n"], "too_few": True}
    psr = probabilistic_sr(stats["sr"], stats["n"], stats["skew"], stats["kurt"])
    dsr_map = dsr_scenarios(stats, trial_scenarios, sr_variance)
    # concentration-trimmed: remove top-2 and recompute SR
    sorted_pnls = sorted(stats["pnls"], reverse=True)
    trimmed = sorted_pnls[2:]
    if len(trimmed) >= 2:
        m2 = statistics.mean(trimmed)
        s2 = statistics.stdev(trimmed)
        sr_trim = m2 / s2 if s2 > 0 else 0.0
        total_trim = sum(trimmed)
    else:
        sr_trim, total_trim = 0.0, 0.0
    # Gate 1 verdict: PSR pass AND all DSR scenarios pass AND SR threshold
    sr_ok = stats["sr"] >= 0.5
    psr_ok = psr >= 0.95
    dsr_all_ok = all(v["pass"] for v in dsr_map.values())
    verdict = "PASS" if (sr_ok and psr_ok and dsr_all_ok) else "FAIL"
    return {
        "label": stats["label"],
        "n": stats["n"],
        "total": stats["total"],
        "mean": stats["mean"],
        "std": stats["std"],
        "sr": stats["sr"],
        "skew": stats["skew"],
        "kurt": stats["kurt"],
        "wins": stats["wins"],
        "win_rate": stats["wins"] / stats["n"],
        "concentration_top2": stats["concentration_top2"],
        "psr": psr,
        "dsr_scenarios": dsr_map,
        "sr_trimmed": sr_trim,
        "total_trimmed": total_trim,
        "sr_pass": sr_ok,
        "psr_pass": psr_ok,
        "dsr_all_pass": dsr_all_ok,
        "verdict": verdict,
    }


def print_segment(seg):
    if seg.get("too_few"):
        print(f"{seg['label']}: n={seg['n']} (too few)")
        print()
        return
    print(f"=== {seg['label']} ===")
    print(f"  n             : {seg['n']}")
    print(f"  Total P&L     : ${seg['total']:.2f}")
    print(f"  Mean/trade    : ${seg['mean']:.3f}")
    print(f"  Std/trade     : ${seg['std']:.3f}")
    print(f"  Sharpe (trade): {seg['sr']:.3f}  (gate: >= 0.5)")
    print(f"  Skewness      : {seg['skew']:.3f}")
    print(f"  Kurtosis      : {seg['kurt']:.3f}  (excess={seg['kurt']-3:.3f})")
    print(f"  Win rate      : {seg['wins']}/{seg['n']} = {seg['win_rate']*100:.1f}%")
    print(f"  PSR           : {seg['psr']:.4f}  (gate: >= 0.95)")
    for n_trials, v in seg["dsr_scenarios"].items():
        flag = "PASS" if v["pass"] else "FAIL"
        print(f"  DSR(N={n_trials:>4}): {v['dsr']:.4f}  SR*={v['sr_star']:.3f}  [{flag}]")
    print(f"  Top-2 concentration: {seg['concentration_top2']*100:.1f}% of total")
    print(f"  Without top-2      : total=${seg['total_trimmed']:.2f}, SR_trim={seg['sr_trimmed']:.3f}")
    print(f"  Gate 1 verdict     : {seg['verdict']}")
    print()


def split_is_oos(closes, is_until_str):
    is_until = datetime.fromisoformat(is_until_str + "T23:59:59+00:00")
    is_rows, oos_rows = [], []
    for r in closes:
        ts = datetime.fromisoformat(r["timestamp"])
        (is_rows if ts <= is_until else oos_rows).append(r)
    return is_rows, oos_rows


def parse_trial_scenarios(s):
    parts = [int(x.strip()) for x in s.split(",") if x.strip()]
    if not parts:
        raise ValueError("--trial-scenarios must be non-empty CSV ints")
    return parts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--path", default=str(PAPER_TRADES))
    ap.add_argument("--trial-scenarios", type=parse_trial_scenarios, default=[10, 50],
                    help="Comma-separated N_trials values (default: 10,50). "
                         "Gate 1 passes iff ALL scenarios pass.")
    ap.add_argument("--sr-variance", type=float, default=0.25,
                    help="Variance of SR across trials (default: 0.25)")
    ap.add_argument("--is-until", default="2026-04-13",
                    help="In-sample ends at YYYY-MM-DD (UTC)")
    ap.add_argument("--fee-rate", type=float, default=None,
                    help="Override fee rate for Protocol Incentive replay. "
                         "Set to 0.0 for fee-free pairs. Default: use CSV as-is.")
    ap.add_argument("--orig-fee-rate", type=float, default=0.0002,
                    help="Fee rate baked into the CSV pnl (default: 0.0002 = 0.02%% MEXC taker)")
    ap.add_argument("--output", default=None,
                    help="Write JSON result to this path")
    args = ap.parse_args()

    closes_raw = load_closes(args.path)
    closes = apply_fee_override(closes_raw, args.orig_fee_rate, args.fee_rate)
    effective_fee = args.orig_fee_rate if args.fee_rate is None else args.fee_rate

    print(f"Loaded {len(closes)} CLOSE trades from {args.path}")
    if args.fee_rate is not None:
        print(f"Protocol Incentive replay: fee_rate {args.orig_fee_rate} -> {args.fee_rate}")
    print(f"Trial scenarios: {args.trial_scenarios}  (sigma_SR^2 = {args.sr_variance})")
    print()

    # full
    full_seg = segment_summary(analyze(closes, "Full sample"), args.trial_scenarios, args.sr_variance)
    print_segment(full_seg)

    # IS/OOS split
    is_rows, oos_rows = split_is_oos(closes, args.is_until)
    print(f"--- IS/OOS split at {args.is_until} ---")
    print(f"IS={len(is_rows)}, OOS={len(oos_rows)}\n")
    is_seg = segment_summary(analyze(is_rows, f"IS (<= {args.is_until})"), args.trial_scenarios, args.sr_variance)
    oos_seg = segment_summary(analyze(oos_rows, f"OOS (> {args.is_until})"), args.trial_scenarios, args.sr_variance)
    print_segment(is_seg)
    print_segment(oos_seg)

    # by direction
    longs = [r for r in closes if r["direction"] == "LONG"]
    shorts = [r for r in closes if r["direction"] == "SHORT"]
    print("--- By direction ---")
    long_seg = segment_summary(analyze(longs, "LONG only"), args.trial_scenarios, args.sr_variance)
    short_seg = segment_summary(analyze(shorts, "SHORT only"), args.trial_scenarios, args.sr_variance)
    print_segment(long_seg)
    print_segment(short_seg)

    # BH-FDR on per-segment p-values (advisory; segments are not independent)
    segments = [full_seg, is_seg, oos_seg, long_seg, short_seg]
    live = [s for s in segments if not s.get("too_few")]
    if len(live) >= 2:
        raw_p = [1.0 - s["psr"] for s in live]
        adj_p = bh_fdr(raw_p)
        print("--- BH-FDR on per-segment PSR (advisory; segments are correlated) ---")
        print(f"  {'segment':<28} {'raw p':>10} {'BH-adj p':>10}")
        for s, rp, ap_val in zip(live, raw_p, adj_p):
            print(f"  {s['label']:<28} {rp:>10.4f} {ap_val:>10.4f}")
        print()
    else:
        adj_p = []

    # Combined Gate 1 verdict (full sample is the primary gate)
    gate1 = full_seg.get("verdict", "FAIL") if not full_seg.get("too_few") else "INSUFFICIENT_DATA"
    print(f"=== Combined Gate 1 verdict: {gate1} ===")
    print()

    if args.output:
        payload = {
            "schema_version": "1.0",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "data_path": args.path,
            "n_closes": len(closes),
            "params": {
                "trial_scenarios": args.trial_scenarios,
                "sr_variance": args.sr_variance,
                "is_until": args.is_until,
                "orig_fee_rate": args.orig_fee_rate,
                "fee_rate_applied": effective_fee,
                "protocol_incentive_replayed": args.fee_rate is not None,
            },
            "segments": {
                "full": strip_pnls(full_seg),
                "is": strip_pnls(is_seg),
                "oos": strip_pnls(oos_seg),
                "long": strip_pnls(long_seg),
                "short": strip_pnls(short_seg),
            },
            "bh_fdr_advisory": [
                {"label": s["label"], "raw_p": rp, "bh_adj_p": ap_val}
                for s, rp, ap_val in zip(live, [1.0 - x["psr"] for x in live], adj_p)
            ],
            "gate1_combined": gate1,
        }
        Path(args.output).write_text(json.dumps(payload, indent=2, default=_json_default))
        print(f"JSON written: {args.output}")


def strip_pnls(seg):
    """Drop raw pnls list before JSON serialisation to keep output compact."""
    if not isinstance(seg, dict):
        return seg
    return {k: v for k, v in seg.items() if k != "pnls"}


def _json_default(o):
    if isinstance(o, (set, tuple)):
        return list(o)
    raise TypeError(f"not serialisable: {type(o)}")


if __name__ == "__main__":
    main()
