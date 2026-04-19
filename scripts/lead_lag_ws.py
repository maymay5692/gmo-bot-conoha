"""Lead-lag analysis with WebSocket data (100ms resolution).

Analyzes: Binance → GMO, bitFlyer → GMO, Binance → bitFlyer
at 100ms bucket resolution to measure true sub-second lead-lag.

Usage:
    python3 scripts/lead_lag_ws.py [--date 2026-04-10] [--bucket-ms 100]
"""
import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy import stats

CACHE_DIR = Path(__file__).parent / "data_cache"


def load_csv(path: Path) -> list[tuple[float, float]]:
    """Load WS CSV → [(epoch_seconds, mid_price), ...]"""
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = datetime.fromisoformat(row["local_ts"])
            mid = float(row["mid_price"])
            rows.append((ts.timestamp(), mid))
    return rows


def load_csv_with_spread(path: Path) -> list[tuple[float, float, float]]:
    """Load WS CSV → [(epoch, mid, spread), ...]"""
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = datetime.fromisoformat(row["local_ts"])
            mid = float(row["mid_price"])
            spread = float(row["spread"])
            rows.append((ts.timestamp(), mid, spread))
    return rows


def bucket_align(
    series_a: list[tuple[float, float]],
    series_b: list[tuple[float, float]],
    bucket_sec: float = 0.1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Align two series to common time buckets using last-observation.

    Returns (timestamps, a_prices, b_prices) for common buckets.
    """
    def to_bucket(epoch):
        return round(epoch / bucket_sec) * bucket_sec

    a_dict: dict[float, float] = {}
    for epoch, mid in series_a:
        a_dict[to_bucket(epoch)] = mid

    b_dict: dict[float, float] = {}
    for epoch, mid in series_b:
        b_dict[to_bucket(epoch)] = mid

    common = sorted(set(a_dict.keys()) & set(b_dict.keys()))
    if not common:
        return np.array([]), np.array([]), np.array([])

    ts = np.array(common)
    a = np.array([a_dict[t] for t in common])
    b = np.array([b_dict[t] for t in common])
    return ts, a, b


def bucket_align_with_spread(
    series_a: list[tuple[float, float]],
    series_b: list[tuple[float, float, float]],
    bucket_sec: float = 0.1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Align series_a (mid only) with series_b (mid+spread) to common buckets."""
    def to_bucket(epoch):
        return round(epoch / bucket_sec) * bucket_sec

    a_dict = {}
    for epoch, mid in series_a:
        a_dict[to_bucket(epoch)] = mid

    b_dict = {}
    b_spread_dict = {}
    for epoch, mid, spread in series_b:
        b = to_bucket(epoch)
        b_dict[b] = mid
        b_spread_dict[b] = spread

    common = sorted(set(a_dict.keys()) & set(b_dict.keys()))
    if not common:
        return np.array([]), np.array([]), np.array([]), np.array([])

    ts = np.array(common)
    a = np.array([a_dict[t] for t in common])
    b = np.array([b_dict[t] for t in common])
    sp = np.array([b_spread_dict[t] for t in common])
    return ts, a, b, sp


def cross_corr(x: np.ndarray, y: np.ndarray, max_lag: int) -> list[dict]:
    """Cross-correlation of returns: corr(x[t], y[t+lag])."""
    n = len(x)
    results = []
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            xs = x[:n - lag] if lag > 0 else x
            ys = y[lag:] if lag > 0 else y
        else:
            xs = x[-lag:]
            ys = y[:n + lag]
        if len(xs) < 30:
            continue
        corr, p = stats.pearsonr(xs, ys)
        ne = len(xs)
        t = corr * np.sqrt(ne - 2) / np.sqrt(1 - corr**2 + 1e-15)
        results.append({"lag": lag, "corr": corr, "t_stat": t, "p": p, "n": ne})
    return results


def threshold_edge(
    signal_ret: np.ndarray,
    target_ret: np.ndarray,
    target_spread: np.ndarray,
    avg_mid: float,
    lag: int,
    thresholds: list[float],
) -> list[dict]:
    """Compute edge at different signal thresholds."""
    n = len(signal_ret)
    sigma = np.std(signal_ret)
    results = []

    for mult in thresholds:
        threshold = mult * sigma
        sig = signal_ret[:n - lag]
        tgt = target_ret[lag:]
        # Spread at target time
        spr = target_spread[lag + 1:lag + 1 + len(tgt)]
        if len(spr) < len(tgt):
            tgt = tgt[:len(spr)]
            sig = sig[:len(spr)]

        mask = np.abs(sig) > threshold
        count = np.sum(mask)
        if count < 10:
            break

        direction = np.sign(sig[mask])
        pnl = direction * tgt[mask]
        hit = np.sum(pnl > 0) / len(pnl)

        mean_pnl = np.mean(pnl)
        edge_jpy = mean_pnl * avg_mid * 0.001

        cond_spread = np.mean(spr[mask]) if np.sum(mask) <= len(spr) else np.mean(target_spread)
        half_spread_jpy = (cond_spread / 2) * 0.001

        t_stat = mean_pnl / (np.std(pnl, ddof=1) / np.sqrt(len(pnl))) if np.std(pnl, ddof=1) > 0 else 0

        results.append({
            "sigma": mult,
            "n": count,
            "pct": count / len(sig) * 100,
            "hit": hit,
            "edge_jpy": edge_jpy,
            "half_spread_jpy": half_spread_jpy,
            "net": edge_jpy - half_spread_jpy,
            "t": t_stat,
        })
    return results


def measure_response_delay(
    leader_ret: np.ndarray,
    follower_ret: np.ndarray,
    bucket_ms: int,
) -> dict:
    """Measure how quickly the follower responds to the leader.

    Computes cumulative R² at increasing lags to find where most
    information transfer is complete.
    """
    cum_r2 = []
    for lag in range(0, 31):
        n = len(leader_ret)
        if lag > 0:
            x = leader_ret[:n - lag]
            y = follower_ret[lag:]
        else:
            x = leader_ret
            y = follower_ret
        corr = np.corrcoef(x, y)[0, 1]
        cum_r2.append(corr**2)

    # Cumulative sum to find when total information transfer plateaus
    total_r2 = sum(cum_r2)
    running = 0
    pct_50 = pct_90 = None
    for i, r2 in enumerate(cum_r2):
        running += r2
        if pct_50 is None and running >= total_r2 * 0.5:
            pct_50 = i * bucket_ms
        if pct_90 is None and running >= total_r2 * 0.9:
            pct_90 = i * bucket_ms

    return {
        "r2_by_lag": cum_r2,
        "total_r2": total_r2,
        "ms_50pct": pct_50,
        "ms_90pct": pct_90,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-04-10")
    parser.add_argument("--bucket-ms", type=int, default=100)
    args = parser.parse_args()

    bucket_sec = args.bucket_ms / 1000.0
    date = args.date

    bf_path = CACHE_DIR / f"ws_bitflyer_{date}.csv"
    bn_path = CACHE_DIR / f"ws_binance_{date}.csv"
    gmo_path = CACHE_DIR / f"ws_gmo_{date}.csv"

    for p in [bf_path, bn_path, gmo_path]:
        if not p.exists():
            print(f"ERROR: {p} not found")
            sys.exit(1)

    print("=" * 70)
    print(f"Lead-Lag Analysis (WebSocket, {args.bucket_ms}ms buckets)")
    print("=" * 70)

    # Load data
    bf_raw = load_csv(bf_path)
    bn_raw = load_csv(bn_path)
    gmo_raw = load_csv_with_spread(gmo_path)
    gmo_mid_only = [(e, m) for e, m, s in gmo_raw]

    print(f"\nRaw ticks: bitFlyer={len(bf_raw)}, Binance={len(bn_raw)}, GMO={len(gmo_raw)}")

    # Align pairs
    ts_bn_gmo, bn_prices, gmo_prices, gmo_spread = bucket_align_with_spread(
        bn_raw, gmo_raw, bucket_sec
    )
    ts_bf_gmo, bf_prices, gmo_prices2, gmo_spread2 = bucket_align_with_spread(
        bf_raw, gmo_raw, bucket_sec
    )
    ts_bn_bf, bn_prices3, bf_prices3 = bucket_align(bn_raw, bf_raw, bucket_sec)

    print(f"Aligned: Binance-GMO={len(ts_bn_gmo)}, bitFlyer-GMO={len(ts_bf_gmo)}, Binance-bitFlyer={len(ts_bn_bf)}")

    if len(ts_bn_gmo) < 100:
        print("ERROR: Not enough aligned data")
        sys.exit(1)

    duration_min = (ts_bn_gmo[-1] - ts_bn_gmo[0]) / 60
    print(f"Duration: {duration_min:.1f} min")
    print(f"GMO avg spread: {np.mean(gmo_spread):.0f} JPY")

    # Compute returns
    bn_ret = np.diff(np.log(bn_prices))
    gmo_ret = np.diff(np.log(gmo_prices))
    gmo_spr = gmo_spread[1:]  # align with returns

    bf_ret2 = np.diff(np.log(bf_prices))
    gmo_ret2 = np.diff(np.log(gmo_prices2))
    gmo_spr2 = gmo_spread2[1:]

    bn_ret3 = np.diff(np.log(bn_prices3))
    bf_ret3 = np.diff(np.log(bf_prices3))

    avg_gmo_mid = np.mean(gmo_prices)

    # ===================================================================
    # A. Cross-Correlation Tables
    # ===================================================================
    max_lag = 20  # ±2 seconds at 100ms

    pairs = [
        ("Binance → GMO", bn_ret, gmo_ret, "Binance leads GMO"),
        ("bitFlyer → GMO", bf_ret2, gmo_ret2, "bitFlyer leads GMO"),
        ("Binance → bitFlyer", bn_ret3, bf_ret3, "Binance leads bitFlyer"),
    ]

    all_results = {}
    for name, x, y, desc in pairs:
        print(f"\n{'=' * 70}")
        print(f"Cross-Correlation: {name}")
        print(f"  Positive lag = {desc}")
        print(f"{'=' * 70}")

        res = cross_corr(x, y, max_lag)
        all_results[name] = res

        # Print key lags only (every 2 ticks = 200ms, plus lag 0 and 1)
        print(f"\n{'lag':>4} {'ms':>6} {'corr':>8} {'t':>8} {'sig':>4}")
        print("-" * 36)
        for r in res:
            if r["lag"] % 2 == 0 or abs(r["lag"]) <= 3:
                sig = "***" if abs(r["t_stat"]) > 3.29 else ("**" if abs(r["t_stat"]) > 2.58 else ("*" if abs(r["t_stat"]) > 1.96 else ""))
                ms = r["lag"] * args.bucket_ms
                print(f"{r['lag']:>4} {ms:>5}ms {r['corr']:>8.4f} {r['t_stat']:>8.2f} {sig:>4}")

    # ===================================================================
    # B. Response Delay Measurement
    # ===================================================================
    print(f"\n{'=' * 70}")
    print("Response Delay: How fast does GMO follow Binance?")
    print("=" * 70)

    delay = measure_response_delay(bn_ret, gmo_ret, args.bucket_ms)
    print(f"\n  50% of information transferred by: {delay['ms_50pct']} ms")
    print(f"  90% of information transferred by: {delay['ms_90pct']} ms")
    print(f"  Total R² (sum of lag 0-30): {delay['total_r2']:.4f}")

    print(f"\n  {'lag':>4} {'ms':>6} {'R²':>8} {'cumul%':>8}")
    print("  " + "-" * 32)
    running = 0
    for i, r2 in enumerate(delay["r2_by_lag"][:21]):
        running += r2
        pct = running / delay["total_r2"] * 100 if delay["total_r2"] > 0 else 0
        bar = "#" * int(pct / 5)
        print(f"  {i:>4} {i * args.bucket_ms:>5}ms {r2:>8.4f} {pct:>7.1f}% {bar}")

    # Same for bitFlyer → GMO
    delay_bf = measure_response_delay(bf_ret2, gmo_ret2, args.bucket_ms)
    print(f"\n  bitFlyer → GMO: 50%={delay_bf['ms_50pct']}ms, 90%={delay_bf['ms_90pct']}ms")

    # Binance → bitFlyer
    delay_bn_bf = measure_response_delay(bn_ret3, bf_ret3, args.bucket_ms)
    print(f"  Binance → bitFlyer: 50%={delay_bn_bf['ms_50pct']}ms, 90%={delay_bn_bf['ms_90pct']}ms")

    # ===================================================================
    # C. Threshold-Based Edge (Binance → GMO)
    # ===================================================================
    print(f"\n{'=' * 70}")
    print("Threshold Edge: Binance → GMO (best lead-lag pair)")
    print("=" * 70)

    # Find optimal lag (highest positive-lag correlation)
    bn_gmo_res = all_results["Binance → GMO"]
    best_lag_r = max([r for r in bn_gmo_res if r["lag"] > 0], key=lambda r: r["corr"])
    best_lag = best_lag_r["lag"]
    print(f"\n  Best lag: {best_lag} ({best_lag * args.bucket_ms}ms), corr={best_lag_r['corr']:.4f}")

    # Test multiple lags around the best
    for test_lag in [1, 2, 3, best_lag, 5, 10]:
        if test_lag > max_lag:
            continue
        print(f"\n  --- Lag {test_lag} ({test_lag * args.bucket_ms}ms) ---")
        thresh = threshold_edge(
            bn_ret, gmo_ret, gmo_spr, avg_gmo_mid, test_lag,
            [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
        )
        if not thresh:
            print("    No data")
            continue

        print(f"  {'σ':>5} {'N':>6} {'%':>5} {'hit':>6} {'edge':>8} {'spread':>8} {'net':>8} {'t':>6}")
        print("  " + "-" * 58)
        for r in thresh:
            sig = "**" if abs(r["t"]) > 2.58 else ("*" if abs(r["t"]) > 1.96 else "")
            print(f"  {r['sigma']:>5.1f} {r['n']:>6} {r['pct']:>4.1f}% {r['hit']:>5.1%} "
                  f"{r['edge_jpy']:>7.4f} {r['half_spread_jpy']:>7.3f} "
                  f"{r['net']:>7.4f} {r['t']:>5.2f} {sig}")

    # ===================================================================
    # D. Summary
    # ===================================================================
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print("=" * 70)

    # Information flow
    print(f"\n  Information flow:")
    print(f"    Binance → GMO:      50% by {delay['ms_50pct']}ms, 90% by {delay['ms_90pct']}ms")
    print(f"    bitFlyer → GMO:     50% by {delay_bf['ms_50pct']}ms, 90% by {delay_bf['ms_90pct']}ms")
    print(f"    Binance → bitFlyer: 50% by {delay_bn_bf['ms_50pct']}ms, 90% by {delay_bn_bf['ms_90pct']}ms")

    # Peak cross-correlation
    for name, res in all_results.items():
        pos_lags = [r for r in res if r["lag"] > 0]
        if pos_lags:
            peak = max(pos_lags, key=lambda r: r["corr"])
            print(f"\n  {name}: peak at lag {peak['lag']} ({peak['lag'] * args.bucket_ms}ms), corr={peak['corr']:.4f}, t={peak['t_stat']:.1f}")

    # Tradeable?
    print(f"\n  GMO API latency estimate: ~500ms = {int(500 / args.bucket_ms)} buckets")
    print(f"  GMO avg spread: {np.mean(gmo_spread):.0f} JPY/BTC = {np.mean(gmo_spread) * 0.001 / 2:.3f} JPY half-spread per 0.001 BTC")

    # Check if any threshold at executable lag gives positive net edge
    executable_lag = max(int(500 / args.bucket_ms), 1)  # API latency in buckets
    print(f"\n  Checking edge at executable lag ({executable_lag} = {executable_lag * args.bucket_ms}ms):")
    thresh_exec = threshold_edge(
        bn_ret, gmo_ret, gmo_spr, avg_gmo_mid, executable_lag,
        [0, 1.0, 1.5, 2.0, 2.5, 3.0],
    )
    found_positive = False
    for r in thresh_exec:
        if r["net"] > 0 and r["t"] > 1.96:
            print(f"    {r['sigma']:.1f}σ: edge={r['edge_jpy']:.4f}, spread={r['half_spread_jpy']:.3f}, "
                  f"net=+{r['net']:.4f} JPY, t={r['t']:.2f}, N={r['n']}")
            found_positive = True

    if found_positive:
        print("  --> POTENTIALLY TRADEABLE signals found at executable latency")
    else:
        print("  --> No tradeable signal at executable latency")

    print(f"\n  Data: {duration_min:.0f} min, {args.bucket_ms}ms buckets (in-sample only)")


if __name__ == "__main__":
    main()
