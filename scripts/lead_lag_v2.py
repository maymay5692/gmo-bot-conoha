"""Lead-lag analysis v2: Critical improvements over v1.

Improvements:
1. Threshold-based signal — only trade when bitFlyer moves > Nσ
2. Regression-based edge (β coefficient)
3. Conditional GMO spread at signal time
4. Spread mean-reversion (bf-gmo divergence) as alternative signal
5. Proper edge vs cost comparison with conditional spread
"""
import csv
import json
import sys
from datetime import datetime, timezone

import numpy as np
from scipy import stats


# ---------------------------------------------------------------------------
# Data loading (same as v1)
# ---------------------------------------------------------------------------

def load_bitflyer(path: str) -> list[tuple[datetime, float, float, float]]:
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = datetime.fromisoformat(row["timestamp"])
            bid = float(row["best_bid"])
            ask = float(row["best_ask"])
            mid = float(row["mid_price"])
            rows.append((ts, bid, ask, mid))
    return rows


def load_gmo_json(path: str) -> list[dict]:
    with open(path) as f:
        data = json.load(f)
    return data["rows"]


def align_to_buckets(
    bf_raw: list, gmo_raw: list, bucket_sec: int = 3
) -> dict:
    """Align both series to common time buckets. Return dict of arrays."""

    def to_bucket(ts):
        epoch = ts.timestamp()
        rounded = round(epoch / bucket_sec) * bucket_sec
        return datetime.fromtimestamp(rounded, tz=timezone.utc)

    bf_dict = {}
    for ts, bid, ask, mid in bf_raw:
        b = to_bucket(ts)
        bf_dict[b] = {"mid": mid, "bid": bid, "ask": ask, "spread": ask - bid}

    gmo_dict = {}
    for r in gmo_raw:
        ts = datetime.fromisoformat(r["timestamp"])
        b = to_bucket(ts)
        gmo_dict[b] = {
            "mid": float(r["mid_price"]),
            "spread": float(r["spread"]),
            "bid": float(r["best_bid"]),
            "ask": float(r["best_ask"]),
        }

    common = sorted(set(bf_dict.keys()) & set(gmo_dict.keys()))
    if len(common) < 100:
        print(f"ERROR: Only {len(common)} aligned points")
        sys.exit(1)

    return {
        "timestamps": common,
        "bf_mid": np.array([bf_dict[t]["mid"] for t in common]),
        "bf_spread": np.array([bf_dict[t]["spread"] for t in common]),
        "gmo_mid": np.array([gmo_dict[t]["mid"] for t in common]),
        "gmo_spread": np.array([gmo_dict[t]["spread"] for t in common]),
        "gmo_bid": np.array([gmo_dict[t]["bid"] for t in common]),
        "gmo_ask": np.array([gmo_dict[t]["ask"] for t in common]),
    }


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def regression_edge(signal: np.ndarray, target: np.ndarray) -> dict:
    """OLS regression: target = β * signal + ε. Returns β, R², edge stats."""
    slope, intercept, r_value, p_value, std_err = stats.linregress(signal, target)
    n = len(signal)
    t_stat = slope / std_err if std_err > 0 else 0
    return {
        "beta": slope,
        "r_squared": r_value**2,
        "t_stat": t_stat,
        "p_value": p_value,
        "n": n,
    }


def threshold_analysis(
    bf_ret: np.ndarray,
    gmo_ret: np.ndarray,
    gmo_spread: np.ndarray,
    avg_mid: float,
    lag: int = 1,
    thresholds_sigma: list[float] = [0, 0.5, 1.0, 1.5, 2.0, 2.5],
) -> list[dict]:
    """Analyze edge conditional on |bf_ret| > threshold * σ."""
    n = len(bf_ret)
    sigma = np.std(bf_ret)
    results = []

    for mult in thresholds_sigma:
        threshold = mult * sigma
        # Signal at time t, target at time t+lag
        sig = bf_ret[: n - lag]
        tgt = gmo_ret[lag:]
        # GMO spread at time of target (t+lag), aligned
        # spread array has same length as price array, returns have len-1
        spr = gmo_spread[lag + 1:]  # spread at time of target return's end
        if len(spr) > len(tgt):
            spr = spr[:len(tgt)]
        elif len(spr) < len(tgt):
            tgt = tgt[:len(spr)]
            sig = sig[:len(spr)]

        mask = np.abs(sig) > threshold
        if np.sum(mask) < 10:
            break

        sig_f = sig[mask]
        tgt_f = tgt[mask]
        spr_f = spr[mask] if len(spr) == len(mask) else gmo_spread[lag:lag+len(mask)][mask]

        direction = np.sign(sig_f)
        pnl = direction * tgt_f
        hit = np.sum(pnl > 0) / len(pnl)

        # Edge in JPY per 0.001 BTC
        mean_pnl = np.mean(pnl)
        edge_jpy = mean_pnl * avg_mid * 0.001
        std_jpy = np.std(pnl, ddof=1) * avg_mid * 0.001

        # Conditional spread
        avg_cond_spread = np.mean(spr_f) if len(spr_f) > 0 else np.mean(gmo_spread)
        half_spread_jpy = (avg_cond_spread / 2) * 0.001

        # t-test on P&L
        if np.std(pnl, ddof=1) > 0:
            t = mean_pnl / (np.std(pnl, ddof=1) / np.sqrt(len(pnl)))
        else:
            t = 0

        # Regression
        reg = regression_edge(sig_f, tgt_f)

        results.append({
            "threshold_sigma": mult,
            "threshold_abs": threshold,
            "n_signals": int(np.sum(mask)),
            "pct_of_ticks": np.sum(mask) / len(sig) * 100,
            "hit_rate": hit,
            "corr": np.corrcoef(sig_f, tgt_f)[0, 1] if len(sig_f) > 2 else 0,
            "beta": reg["beta"],
            "edge_jpy": edge_jpy,
            "std_jpy": std_jpy,
            "t_stat": t,
            "avg_cond_spread": avg_cond_spread,
            "half_spread_jpy": half_spread_jpy,
            "net_edge_jpy": edge_jpy - half_spread_jpy,
            "edge_to_spread": edge_jpy / half_spread_jpy if half_spread_jpy > 0 else 0,
        })

    return results


def spread_mean_reversion(data: dict) -> dict:
    """Analyze bf_mid - gmo_mid as mean-reverting spread.

    If the spread diverges, does it revert? Can we profit from reversion?
    """
    spread = data["bf_mid"] - data["gmo_mid"]
    mean_spread = np.mean(spread)
    std_spread = np.std(spread)

    # Spread returns (change in spread)
    d_spread = np.diff(spread)

    # Autocorrelation of spread level (should be positive, near 1 for persistent)
    ac1_level = np.corrcoef(spread[:-1], spread[1:])[0, 1]

    # Autocorrelation of spread changes (negative = mean reverting)
    ac1_change = np.corrcoef(d_spread[:-1], d_spread[1:])[0, 1]

    # Half-life of mean reversion: from AR(1) on spread level
    # spread[t] - mean = φ * (spread[t-1] - mean) + ε
    # half-life = -ln(2) / ln(φ)
    phi = ac1_level
    if 0 < phi < 1:
        half_life_ticks = -np.log(2) / np.log(phi)
        half_life_sec = half_life_ticks * 3  # 3s per tick
    else:
        half_life_ticks = float("inf")
        half_life_sec = float("inf")

    # Z-score based strategy: when z > threshold, short spread (sell bf, buy gmo)
    z = (spread - mean_spread) / std_spread

    results_by_z = []
    for z_thresh in [0.5, 1.0, 1.5, 2.0]:
        # Entry when |z| > threshold, exit when z crosses 0
        long_entries = np.where(z[:-1] < -z_thresh)[0]  # spread too low, buy spread
        short_entries = np.where(z[:-1] > z_thresh)[0]   # spread too high, sell spread

        # For each entry, compute return over next N ticks
        horizons = [1, 3, 5, 10, 20]
        for h in horizons:
            profits = []
            for idx in long_entries:
                if idx + h < len(spread):
                    profits.append(spread[idx + h] - spread[idx])
            for idx in short_entries:
                if idx + h < len(spread):
                    profits.append(spread[idx] - spread[idx + h])

            if len(profits) >= 5:
                profits = np.array(profits)
                mean_p = np.mean(profits)
                t_stat = mean_p / (np.std(profits, ddof=1) / np.sqrt(len(profits))) if np.std(profits, ddof=1) > 0 else 0
                results_by_z.append({
                    "z_threshold": z_thresh,
                    "horizon_ticks": h,
                    "horizon_sec": h * 3,
                    "n_trades": len(profits),
                    "mean_profit_jpy_btc": mean_p,
                    "mean_profit_001btc": mean_p * 0.001,
                    "t_stat": t_stat,
                })

    return {
        "mean": mean_spread,
        "std": std_spread,
        "ac1_level": ac1_level,
        "ac1_change": ac1_change,
        "half_life_ticks": half_life_ticks,
        "half_life_sec": half_life_sec,
        "z_results": results_by_z,
    }


def asymmetry_test(bf_ret: np.ndarray, gmo_ret: np.ndarray) -> dict:
    """Test the asymmetry of lead-lag: does bf lead gmo more than gmo leads bf?

    Compute: H_a = corr(bf[t], gmo[t+1]) - corr(gmo[t], bf[t+1])
    Bootstrap CI for the difference.
    """
    n = len(bf_ret)
    bf_leads = np.corrcoef(bf_ret[:n-1], gmo_ret[1:])[0, 1]
    gmo_leads = np.corrcoef(gmo_ret[:n-1], bf_ret[1:])[0, 1]
    diff = bf_leads - gmo_leads

    # Bootstrap CI
    rng = np.random.default_rng(42)
    n_boot = 5000
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n - 1, size=n - 1)
        bf_b = bf_ret[idx]
        gmo_b = gmo_ret[idx]
        bf_next = bf_ret[idx + 1] if np.all(idx + 1 < n) else bf_ret[np.minimum(idx + 1, n - 1)]
        gmo_next = gmo_ret[idx + 1] if np.all(idx + 1 < n) else gmo_ret[np.minimum(idx + 1, n - 1)]

        # Block bootstrap: use contiguous blocks
        block_start = rng.integers(0, n - 2, size=n - 1)
        bf_b = bf_ret[block_start]
        gmo_b = gmo_ret[block_start]
        bf_n = bf_ret[np.minimum(block_start + 1, n - 1)]
        gmo_n = gmo_ret[np.minimum(block_start + 1, n - 1)]

        c1 = np.corrcoef(bf_b, gmo_n)[0, 1]
        c2 = np.corrcoef(gmo_b, bf_n)[0, 1]
        diffs[i] = c1 - c2

    ci_lo, ci_hi = np.percentile(diffs, [2.5, 97.5])

    return {
        "bf_leads_gmo": bf_leads,
        "gmo_leads_bf": gmo_leads,
        "difference": diff,
        "ci_95": (ci_lo, ci_hi),
        "significant": ci_lo > 0 or ci_hi < 0,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    bf_path = "scripts/data_cache/bitflyer_ticker_2026-04-10.csv"
    gmo_path = "/tmp/gmo_metrics_raw.json"

    print("=" * 70)
    print("Lead-Lag Analysis v2: Critical Improvements")
    print("=" * 70)

    bf_raw = load_bitflyer(bf_path)
    gmo_raw = load_gmo_json(gmo_path)
    data = align_to_buckets(bf_raw, gmo_raw, bucket_sec=3)

    n = len(data["timestamps"])
    duration = (data["timestamps"][-1] - data["timestamps"][0]).total_seconds() / 60
    print(f"Aligned: {n} ticks, {duration:.1f} min")
    print(f"Time: {data['timestamps'][0].isoformat()} to {data['timestamps'][-1].isoformat()}")

    bf_ret = np.diff(np.log(data["bf_mid"]))
    gmo_ret = np.diff(np.log(data["gmo_mid"]))
    avg_mid = np.mean(data["gmo_mid"])

    # ===================================================================
    # TEST 1: Asymmetry — does bitFlyer truly lead GMO?
    # ===================================================================
    print("\n" + "=" * 70)
    print("TEST 1: Lead-Lag Asymmetry (Bootstrap)")
    print("=" * 70)

    asym = asymmetry_test(bf_ret, gmo_ret)
    print(f"  corr(bf[t], gmo[t+1]) = {asym['bf_leads_gmo']:.4f}")
    print(f"  corr(gmo[t], bf[t+1]) = {asym['gmo_leads_bf']:.4f}")
    print(f"  Difference = {asym['difference']:.4f}")
    print(f"  95% CI = [{asym['ci_95'][0]:.4f}, {asym['ci_95'][1]:.4f}]")
    print(f"  Significant: {'YES' if asym['significant'] else 'NO'}")
    if asym['significant']:
        if asym['difference'] > 0:
            print("  --> bitFlyer LEADS GMO (statistically significant)")
        else:
            print("  --> GMO LEADS bitFlyer (statistically significant)")
    else:
        print("  --> No significant directional lead-lag")

    # ===================================================================
    # TEST 2: Regression-based edge at lag 1
    # ===================================================================
    print("\n" + "=" * 70)
    print("TEST 2: Regression Edge (gmo_ret[t+1] = β * bf_ret[t] + ε)")
    print("=" * 70)

    for lag in [1, 2, 3]:
        sig = bf_ret[:len(bf_ret) - lag]
        tgt = gmo_ret[lag:]
        reg = regression_edge(sig, tgt)
        # Expected edge per trade: β * E[|bf_ret|]
        expected_move = reg["beta"] * np.mean(np.abs(sig))
        edge_jpy = expected_move * avg_mid * 0.001
        print(f"\n  Lag {lag} ({lag*3}s):")
        print(f"    β = {reg['beta']:.4f}, R² = {reg['r_squared']:.6f}, t = {reg['t_stat']:.2f}")
        print(f"    E[|bf_ret|] = {np.mean(np.abs(sig)):.8f}")
        print(f"    Expected edge = β × E[|bf_ret|] = {expected_move:.10f} (log-ret)")
        print(f"    Edge per 0.001 BTC = {edge_jpy:.4f} JPY")

    # ===================================================================
    # TEST 3: Threshold-conditioned signal (key improvement)
    # ===================================================================
    print("\n" + "=" * 70)
    print("TEST 3: Threshold-Conditioned Signal (lag=1)")
    print("  Only trade when |bf_ret| > N × σ")
    print("=" * 70)

    thresh_results = threshold_analysis(
        bf_ret, gmo_ret, data["gmo_spread"][1:],  # align with returns
        avg_mid, lag=1,
        thresholds_sigma=[0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
    )

    print(f"\n{'σ mult':>6} {'N sig':>6} {'%ticks':>6} {'hit%':>6} {'corr':>7} {'β':>7} "
          f"{'edge':>8} {'spread':>8} {'net':>8} {'e/s':>5} {'t':>6}")
    print("-" * 90)
    for r in thresh_results:
        sig = ""
        if abs(r["t_stat"]) > 2.58: sig = "**"
        elif abs(r["t_stat"]) > 1.96: sig = "*"
        print(f"{r['threshold_sigma']:>6.1f} {r['n_signals']:>6d} {r['pct_of_ticks']:>5.1f}% "
              f"{r['hit_rate']:>5.1%} {r['corr']:>7.4f} {r['beta']:>7.4f} "
              f"{r['edge_jpy']:>7.4f} {r['half_spread_jpy']:>7.3f} "
              f"{r['net_edge_jpy']:>7.4f} {r['edge_to_spread']:>5.1%} {r['t_stat']:>5.2f} {sig}")

    # ===================================================================
    # TEST 4: Conditional spread — does GMO spread widen when bf moves?
    # ===================================================================
    print("\n" + "=" * 70)
    print("TEST 4: Conditional GMO Spread")
    print("  Does GMO spread widen when bitFlyer moves?")
    print("=" * 70)

    sigma_bf = np.std(bf_ret)
    for mult in [0, 0.5, 1.0, 1.5, 2.0, 2.5]:
        threshold = mult * sigma_bf
        mask = np.abs(bf_ret) > threshold
        n_ticks = np.sum(mask)
        if n_ticks < 5:
            break
        cond_spread = data["gmo_spread"][1:][mask]  # spread at same tick as bf return
        # Also check next-tick spread (when we'd actually trade)
        next_spread = data["gmo_spread"][2:][mask[:len(mask)-1]] if len(mask) > 1 else cond_spread
        print(f"  |bf_ret| > {mult:.1f}σ: N={n_ticks:>4d}, "
              f"spread_same={np.mean(cond_spread):>7.0f}, "
              f"spread_next={np.mean(next_spread):>7.0f} "
              f"(vs avg {np.mean(data['gmo_spread']):>.0f})")

    # ===================================================================
    # TEST 5: Spread Mean-Reversion (alternative strategy)
    # ===================================================================
    print("\n" + "=" * 70)
    print("TEST 5: Spread Mean-Reversion (bf_mid - gmo_mid)")
    print("=" * 70)

    mr = spread_mean_reversion(data)
    print(f"  Spread (bf-gmo): mean={mr['mean']:.0f}, std={mr['std']:.0f}")
    print(f"  AC(1) level:  {mr['ac1_level']:.4f} (persistence)")
    print(f"  AC(1) change: {mr['ac1_change']:.4f} (negative = mean-reverting)")
    print(f"  Half-life:    {mr['half_life_ticks']:.1f} ticks = {mr['half_life_sec']:.0f} sec")

    if mr["z_results"]:
        print(f"\n  Z-Score Strategy (trade when |z| > threshold, profit from reversion):")
        print(f"  {'z_thr':>5} {'horizon':>8} {'N':>5} {'profit/BTC':>11} {'profit/0.001':>12} {'t':>6}")
        print("  " + "-" * 55)
        for r in mr["z_results"]:
            sig = ""
            if abs(r["t_stat"]) > 2.58: sig = "**"
            elif abs(r["t_stat"]) > 1.96: sig = "*"
            print(f"  {r['z_threshold']:>5.1f} {r['horizon_sec']:>6d}s {r['n_trades']:>5d} "
                  f"{r['mean_profit_jpy_btc']:>10.1f} {r['mean_profit_001btc']:>11.4f} "
                  f"{r['t_stat']:>5.2f} {sig}")

    # ===================================================================
    # TEST 6: Resolution sensitivity — what if true lead is sub-second?
    # ===================================================================
    print("\n" + "=" * 70)
    print("TEST 6: Resolution Sensitivity Estimate")
    print("=" * 70)

    # At 3s resolution, lag-1 corr = 0.24
    # If true lead is T seconds, proportion that falls in lag-1 at 3s buckets:
    # p ≈ T/3 for T < 3
    # So "corrected" same-lag correlation ≈ 0.24 / (T/3) = 0.24 * 3 / T
    lag1_corr = 0.2387
    print("  Hypothetical: if true lead-lag is concentrated at sub-3s timescale,")
    print("  the lag-1 correlation at finer resolution would be higher.")
    print()
    print(f"  {'True lead':>10} {'Corrected corr':>15} {'Note':>30}")
    print("  " + "-" * 60)
    for true_lead in [0.1, 0.2, 0.5, 1.0, 1.5, 2.0, 3.0]:
        if true_lead <= 3:
            p_in_lag1 = min(true_lead / 3, 1.0)
            corrected = lag1_corr / p_in_lag1 if p_in_lag1 > 0 else lag1_corr
            corrected = min(corrected, 1.0)
            note = ""
            if true_lead < 0.3:
                note = "sub-ms execution needed"
            elif true_lead < 1.0:
                note = "GMO API too slow (~500ms)"
            else:
                note = "possibly executable"
            print(f"  {true_lead:>8.1f}s {corrected:>14.3f} {note:>30}")

    # ===================================================================
    # VERDICT
    # ===================================================================
    print("\n" + "=" * 70)
    print("OVERALL VERDICT")
    print("=" * 70)

    # Find best threshold result
    best_thresh = None
    for r in thresh_results:
        if r["n_signals"] >= 20 and r["net_edge_jpy"] > 0:
            if best_thresh is None or r["net_edge_jpy"] > best_thresh["net_edge_jpy"]:
                best_thresh = r

    print(f"\n  1. Asymmetry test: {'bitFlyer leads' if asym['significant'] and asym['difference'] > 0 else 'inconclusive'}")
    print(f"     (diff={asym['difference']:.4f}, CI=[{asym['ci_95'][0]:.4f}, {asym['ci_95'][1]:.4f}])")

    if best_thresh:
        print(f"\n  2. Best threshold signal: {best_thresh['threshold_sigma']:.1f}σ")
        print(f"     Edge={best_thresh['edge_jpy']:.4f}, Spread={best_thresh['half_spread_jpy']:.3f}, "
              f"Net={best_thresh['net_edge_jpy']:.4f}")
        print(f"     N={best_thresh['n_signals']}, hit={best_thresh['hit_rate']:.1%}")
    else:
        print(f"\n  2. No threshold level produces net-positive edge at 3s resolution")

    print(f"\n  3. Spread mean-reversion half-life: {mr['half_life_sec']:.0f}s")
    if mr['ac1_change'] < -0.1:
        print(f"     Strong mean-reversion (AC change={mr['ac1_change']:.3f})")
    else:
        print(f"     Weak/no mean-reversion (AC change={mr['ac1_change']:.3f})")

    print(f"\n  4. Key limitation: 3s resolution masks true sub-second dynamics")
    print(f"     Need WebSocket data (100ms resolution) for definitive answer")

    print(f"\n  5. Data: {duration:.0f} min only. Generalization uncertain.")


if __name__ == "__main__":
    main()
