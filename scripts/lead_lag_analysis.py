"""Cross-exchange lead-lag analysis: bitFlyer FX_BTC_JPY vs GMO BTC_JPY.

Computes cross-correlation of returns at different lags to detect
whether bitFlyer leads GMO (or vice versa).

Usage:
    python3 scripts/lead_lag_analysis.py
"""
import csv
import json
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
from scipy import stats


def load_bitflyer(path: str) -> list[tuple[datetime, float]]:
    """Load bitFlyer ticker CSV -> [(timestamp, mid_price), ...]"""
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = datetime.fromisoformat(row["timestamp"])
            mid = float(row["mid_price"])
            rows.append((ts, mid))
    return rows


def load_gmo_json(path: str) -> list[tuple[datetime, float]]:
    """Load GMO metrics JSON -> [(timestamp, mid_price), ...]"""
    with open(path) as f:
        data = json.load(f)
    rows = []
    for r in data["rows"]:
        ts_str = r["timestamp"]
        ts = datetime.fromisoformat(ts_str)
        mid = float(r["mid_price"])
        rows.append((ts, mid))
    return rows


def align_series(
    bf: list[tuple[datetime, float]],
    gmo: list[tuple[datetime, float]],
    bucket_sec: int = 3,
) -> tuple[np.ndarray, np.ndarray, list[datetime]]:
    """Align two time series to common buckets.

    Rounds each timestamp to nearest bucket_sec boundary,
    then takes the last observation per bucket.
    Returns aligned numpy arrays of mid prices and timestamps.
    """

    def to_bucket(ts: datetime) -> datetime:
        epoch = ts.timestamp()
        rounded = round(epoch / bucket_sec) * bucket_sec
        return datetime.fromtimestamp(rounded, tz=timezone.utc)

    bf_dict: dict[datetime, float] = {}
    for ts, mid in bf:
        bf_dict[to_bucket(ts)] = mid

    gmo_dict: dict[datetime, float] = {}
    for ts, mid in gmo:
        gmo_dict[to_bucket(ts)] = mid

    common = sorted(set(bf_dict.keys()) & set(gmo_dict.keys()))
    if not common:
        return np.array([]), np.array([]), []

    bf_arr = np.array([bf_dict[t] for t in common])
    gmo_arr = np.array([gmo_dict[t] for t in common])
    return bf_arr, gmo_arr, common


def compute_returns(prices: np.ndarray) -> np.ndarray:
    """Log returns."""
    return np.diff(np.log(prices))


def cross_corr_with_stats(
    x: np.ndarray, y: np.ndarray, max_lag: int = 20
) -> list[dict]:
    """Compute cross-correlation corr(x[t], y[t+lag]) with t-stats.

    Positive lag: x leads y (x at time t predicts y at time t+lag).
    Negative lag: y leads x.
    """
    n = len(x)
    results = []
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            x_slice = x[: n - lag] if lag > 0 else x
            y_slice = y[lag:] if lag > 0 else y
        else:
            x_slice = x[-lag:]
            y_slice = y[: n + lag]

        if len(x_slice) < 30:
            continue

        corr, p_value = stats.pearsonr(x_slice, y_slice)
        n_eff = len(x_slice)
        t_stat = corr * np.sqrt(n_eff - 2) / np.sqrt(1 - corr**2 + 1e-15)

        results.append(
            {
                "lag": lag,
                "corr": corr,
                "t_stat": t_stat,
                "p_value": p_value,
                "n": n_eff,
            }
        )
    return results


def estimate_edge(
    bf_returns: np.ndarray,
    gmo_returns: np.ndarray,
    lag: int,
    avg_mid: float,
) -> dict:
    """Estimate the tradeable edge from a lead-lag signal.

    Strategy: at time t, observe bf_return[t].
    If positive, go long GMO; if negative, go short.
    Close at end of next tick (t+lag).

    Returns edge metrics in JPY per 0.001 BTC.
    """
    if lag <= 0:
        return {}

    n = len(bf_returns)
    signal = bf_returns[: n - lag]
    target = gmo_returns[lag:]

    # Direction-based P&L: trade in direction of signal
    direction = np.sign(signal)
    pnl_logret = direction * target  # positive = correct prediction
    nonzero = direction != 0
    pnl_logret = pnl_logret[nonzero]
    direction_nz = direction[nonzero]
    target_nz = target[nonzero[: len(target)] if len(nonzero) > len(target) else nonzero]

    n_trades = len(pnl_logret)
    correct = np.sum(pnl_logret > 0)
    hit_rate = correct / n_trades if n_trades > 0 else 0

    # Mean edge in log-return per trade
    mean_edge_logret = np.mean(pnl_logret)
    std_edge_logret = np.std(pnl_logret, ddof=1)

    # Convert to JPY per 0.001 BTC
    edge_jpy = mean_edge_logret * avg_mid * 0.001
    std_jpy = std_edge_logret * avg_mid * 0.001

    # t-test: is mean P&L significantly > 0?
    t_stat = mean_edge_logret / (std_edge_logret / np.sqrt(n_trades)) if std_edge_logret > 0 else 0

    # Alternative edge estimate: corr * std(target)
    # This is the theoretical expected move in the predicted direction
    corr = np.corrcoef(signal[nonzero], target_nz)[0, 1] if len(target_nz) == np.sum(nonzero) else 0
    theoretical_edge_logret = abs(corr) * np.std(target)
    theoretical_edge_jpy = theoretical_edge_logret * avg_mid * 0.001

    return {
        "n_trades": n_trades,
        "hit_rate": hit_rate,
        "mean_edge_logret": mean_edge_logret,
        "edge_jpy": edge_jpy,
        "std_jpy": std_jpy,
        "t_stat": t_stat,
        "theoretical_edge_jpy": theoretical_edge_jpy,
    }


def main():
    bf_path = "scripts/data_cache/bitflyer_ticker_2026-04-10.csv"
    gmo_path = "/tmp/gmo_metrics_raw.json"

    print("=" * 70)
    print("Cross-Exchange Lead-Lag Analysis: bitFlyer FX vs GMO BTC_JPY")
    print("=" * 70)

    # Load data
    bf_raw = load_bitflyer(bf_path)
    gmo_raw = load_gmo_json(gmo_path)
    print(f"\nbitFlyer raw ticks: {len(bf_raw)}")
    print(f"GMO raw ticks:      {len(gmo_raw)}")

    # Align to 3-second buckets
    bf_prices, gmo_prices, timestamps = align_series(bf_raw, gmo_raw, bucket_sec=3)
    print(f"Aligned ticks:      {len(timestamps)}")
    if len(timestamps) < 100:
        print("ERROR: Not enough aligned data points. Need at least 100.")
        sys.exit(1)

    duration_min = (timestamps[-1] - timestamps[0]).total_seconds() / 60
    print(f"Duration:           {duration_min:.1f} minutes")
    print(f"Time range:         {timestamps[0].isoformat()} to {timestamps[-1].isoformat()}")

    # Price summary
    print(f"\nbitFlyer mid range: {bf_prices.min():.0f} - {bf_prices.max():.0f}")
    print(f"GMO mid range:      {gmo_prices.min():.0f} - {gmo_prices.max():.0f}")
    price_diff = bf_prices - gmo_prices
    print(f"Price diff (bF-GMO): mean={price_diff.mean():.0f}, std={price_diff.std():.0f}")

    # Compute returns
    bf_ret = compute_returns(bf_prices)
    gmo_ret = compute_returns(gmo_prices)
    print(f"\nReturn stats (log, per 3s tick):")
    print(f"  bitFlyer: mean={bf_ret.mean():.8f}, std={bf_ret.std():.6f}")
    print(f"  GMO:      mean={gmo_ret.mean():.8f}, std={gmo_ret.std():.6f}")

    # Cross-correlation analysis
    print("\n" + "=" * 70)
    print("Cross-Correlation: corr(bf_return[t], gmo_return[t+lag])")
    print("  Positive lag: bitFlyer LEADS GMO")
    print("  Negative lag: GMO LEADS bitFlyer")
    print("=" * 70)

    results = cross_corr_with_stats(bf_ret, gmo_ret, max_lag=10)

    print(f"\n{'lag':>4s}  {'corr':>8s}  {'t-stat':>8s}  {'p-value':>10s}  {'n':>5s}  {'sig':>5s}")
    print("-" * 50)

    significant_leads = []
    for r in results:
        sig = ""
        if abs(r["t_stat"]) > 3.29:
            sig = "***"
        elif abs(r["t_stat"]) > 2.58:
            sig = "**"
        elif abs(r["t_stat"]) > 1.96:
            sig = "*"
        print(
            f"{r['lag']:>4d}  {r['corr']:>8.4f}  {r['t_stat']:>8.2f}  {r['p_value']:>10.6f}  {r['n']:>5d}  {sig:>5s}"
        )
        if r["lag"] > 0 and abs(r["t_stat"]) > 1.96:
            significant_leads.append(r)

    # Compute actual GMO spread from data
    avg_gmo_mid = gmo_prices.mean()

    # Get actual spread from GMO JSON
    spreads = [float(r["spread"]) for r in json.load(open(gmo_path))["rows"]
               if "02:09" <= r["timestamp"][11:16] <= "03:12"]
    avg_spread = np.mean(spreads) if spreads else 1000
    half_spread_jpy_per_001 = (avg_spread / 2) * 0.001

    print(f"\nGMO actual spread (overlap period):")
    print(f"  Mean: {avg_spread:.0f} JPY/BTC, Half-spread per 0.001 BTC: {half_spread_jpy_per_001:.3f} JPY")

    # Edge estimation for significant positive lags
    if significant_leads:
        print("\n" + "=" * 70)
        print("Edge Estimation for Significant Positive Lags")
        print("  (bitFlyer leads GMO)")
        print("=" * 70)

        for r in significant_leads:
            lag = r["lag"]
            edge = estimate_edge(bf_ret, gmo_ret, lag, avg_gmo_mid)

            print(f"\n  Lag {lag} ({lag * 3}s):")
            print(f"    Correlation:       {r['corr']:.4f} (t={r['t_stat']:.2f})")
            print(f"    N trades:          {edge['n_trades']}")
            print(f"    Hit rate:          {edge['hit_rate']:.1%}")
            print(f"    Mean edge:         {edge['mean_edge_logret']:.10f} (log-return)")
            print(f"    Edge per 0.001 BTC:  {edge['edge_jpy']:.4f} JPY (empirical)")
            print(f"    Theoretical edge:    {edge['theoretical_edge_jpy']:.4f} JPY")
            print(f"    Std per trade:       {edge['std_jpy']:.4f} JPY")
            print(f"    Edge t-stat:         {edge['t_stat']:.2f}")
            print(f"    GMO half-spread:     {half_spread_jpy_per_001:.3f} JPY")
            tradeable = edge['edge_jpy'] > half_spread_jpy_per_001
            print(f"    Edge > half-spread:  {'YES' if tradeable else 'NO'}")
            net = edge['edge_jpy'] - half_spread_jpy_per_001
            print(f"    Net edge:            {net:.4f} JPY per 0.001 BTC per trade")

    # Also check reverse: GMO leads bitFlyer
    reverse_leads = [r for r in results if r["lag"] < 0 and abs(r["t_stat"]) > 1.96]
    if reverse_leads:
        print("\n" + "=" * 70)
        print("Significant Negative Lags (GMO leads bitFlyer)")
        print("=" * 70)
        for r in reverse_leads:
            print(f"  Lag {r['lag']} ({abs(r['lag']) * 3}s): corr={r['corr']:.4f}, t={r['t_stat']:.2f}")

    # Autocorrelation of individual series
    print("\n" + "=" * 70)
    print("Autocorrelation (sanity check)")
    print("=" * 70)
    for name, ret in [("bitFlyer", bf_ret), ("GMO", gmo_ret)]:
        ac1 = np.corrcoef(ret[:-1], ret[1:])[0, 1]
        ac2 = np.corrcoef(ret[:-2], ret[2:])[0, 1]
        print(f"  {name}: AC(1)={ac1:.4f}, AC(2)={ac2:.4f}")

    # Contemporaneous correlation
    contemp = [r for r in results if r["lag"] == 0][0]
    print(f"\n  Contemporaneous corr(bf, gmo): {contemp['corr']:.4f} (t={contemp['t_stat']:.2f})")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    if significant_leads:
        best = max(significant_leads, key=lambda r: abs(r["t_stat"]))
        edge = estimate_edge(bf_ret, gmo_ret, best["lag"], avg_gmo_mid)
        print(f"  Best lead-lag signal: lag={best['lag']} ({best['lag']*3}s)")
        print(f"  Correlation: {best['corr']:.4f}, t-stat: {best['t_stat']:.2f}")
        print(f"  Edge: {edge['edge_jpy']:.4f} JPY vs half-spread: {half_spread_jpy_per_001:.3f} JPY")
        if edge['edge_jpy'] > half_spread_jpy_per_001:
            print("  VERDICT: POTENTIALLY TRADEABLE - edge exceeds half-spread")
        else:
            print("  VERDICT: NOT TRADEABLE - edge below half-spread")
            print(f"  Edge is {edge['edge_jpy'] / half_spread_jpy_per_001 * 100:.1f}% of half-spread")
    else:
        print("  No significant lead-lag found at any positive lag.")
        print("  VERDICT: bitFlyer does not lead GMO at 3-second resolution.")

    print(f"\n  NOTE: Based on {duration_min:.0f} minutes of data.")
    print("  Longer data collection recommended for robust conclusion.")


if __name__ == "__main__":
    main()
