"""Measure cross-exchange lead-lag: Binance vs Bitget/MEXC/GMO.

Connects to all 4 exchanges via WebSocket (GMO via HTTP polling),
collects data for a specified duration, then runs lead-lag analysis.

Usage:
    python3 scripts/measure_latency.py [--duration 300]
"""
import argparse
import asyncio
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone

import numpy as np
import websockets
from scipy import stats


# ---------------------------------------------------------------------------
# Global data stores
# ---------------------------------------------------------------------------
ticks: dict[str, list[tuple[float, float]]] = {
    "binance": [],
    "bitget": [],
    "mexc": [],
    "gmo": [],
}
counts = {"binance": 0, "bitget": 0, "mexc": 0, "gmo": 0, "errors": 0}
stop_event = asyncio.Event()


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------

async def collect_binance():
    uri = "wss://stream.binance.com:9443/ws/btcusdt@bookTicker"
    try:
        async with websockets.connect(uri, ping_interval=20) as ws:
            async for raw in ws:
                if stop_event.is_set():
                    return
                data = json.loads(raw)
                bid = float(data.get("b", 0))
                ask = float(data.get("a", 0))
                mid = (bid + ask) / 2
                ticks["binance"].append((time.monotonic(), mid))
                counts["binance"] += 1
    except Exception as e:
        counts["errors"] += 1


async def collect_bitget():
    uri = "wss://ws.bitget.com/v2/ws/public"
    sub = json.dumps({
        "op": "subscribe",
        "args": [{"instType": "USDT-FUTURES", "channel": "ticker", "instId": "BTCUSDT"}],
    })
    try:
        async with websockets.connect(uri, ping_interval=20) as ws:
            await ws.send(sub)
            async for raw in ws:
                if stop_event.is_set():
                    return
                data = json.loads(raw)
                items = data.get("data", [])
                if not isinstance(items, list) or not items:
                    continue
                item = items[0]
                bid = float(item.get("bidPr", 0))
                ask = float(item.get("askPr", 0))
                if bid == 0 or ask == 0:
                    continue
                mid = (bid + ask) / 2
                ticks["bitget"].append((time.monotonic(), mid))
                counts["bitget"] += 1
    except Exception as e:
        counts["errors"] += 1


async def collect_mexc():
    """MEXC futures: try deal (trade) stream for higher frequency."""
    uri = "wss://contract.mexc.com/edge"
    # Subscribe to both ticker and deal for more data points
    subs = [
        json.dumps({"method": "sub.ticker", "param": {"symbol": "BTC_USDT"}}),
        json.dumps({"method": "sub.deal", "param": {"symbol": "BTC_USDT"}}),
    ]
    try:
        async with websockets.connect(uri, ping_interval=20) as ws:
            for s in subs:
                await ws.send(s)
            async for raw in ws:
                if stop_event.is_set():
                    return
                data = json.loads(raw)
                channel = data.get("channel", "")
                inner = data.get("data", {})

                if channel == "push.ticker" and isinstance(inner, dict):
                    bid = float(inner.get("bid1", 0))
                    ask = float(inner.get("ask1", 0))
                    if bid > 0 and ask > 0:
                        mid = (bid + ask) / 2
                        ticks["mexc"].append((time.monotonic(), mid))
                        counts["mexc"] += 1
                elif channel == "push.deal" and isinstance(inner, dict):
                    price = float(inner.get("p", 0))
                    if price > 0:
                        ticks["mexc"].append((time.monotonic(), price))
                        counts["mexc"] += 1
    except Exception as e:
        counts["errors"] += 1


async def collect_gmo():
    url = "https://api.coin.z.com/public/v1/ticker?symbol=BTC_JPY"
    loop = asyncio.get_event_loop()
    while not stop_event.is_set():
        try:
            data = await loop.run_in_executor(None, _fetch_gmo, url)
            if data:
                bid = float(data.get("bid", 0))
                ask = float(data.get("ask", 0))
                mid = (bid + ask) / 2
                ticks["gmo"].append((time.monotonic(), mid))
                counts["gmo"] += 1
        except Exception:
            counts["errors"] += 1
        await asyncio.sleep(0.5)


def _fetch_gmo(url):
    req = urllib.request.Request(url, headers={"User-Agent": "gmo-bot/1.0"})
    with urllib.request.urlopen(req, timeout=3) as resp:
        body = json.loads(resp.read())
    if body.get("status") == 0:
        for item in body.get("data", []):
            if item.get("symbol") == "BTC_JPY":
                return item
    return None


async def status_printer(duration):
    t0 = time.monotonic()
    while not stop_event.is_set():
        await asyncio.sleep(10)
        elapsed = time.monotonic() - t0
        remaining = duration - elapsed
        print(f"  [{elapsed:.0f}s / {duration}s] "
              f"bn={counts['binance']} bg={counts['bitget']} "
              f"mx={counts['mexc']} gmo={counts['gmo']} "
              f"err={counts['errors']} (残り{remaining:.0f}s)")


async def run_collection(duration: int, skip_mexc: bool = False):
    exchanges = "Binance (WS), Bitget (WS), GMO (HTTP 500ms)"
    if not skip_mexc:
        exchanges += ", MEXC (WS)"
    print(f"Collecting from exchanges for {duration}s...")
    print(f"  {exchanges}\n")

    async def timer():
        await asyncio.sleep(duration)
        stop_event.set()

    task_list = [
        asyncio.create_task(collect_binance()),
        asyncio.create_task(collect_bitget()),
        asyncio.create_task(collect_gmo()),
        asyncio.create_task(status_printer(duration)),
        asyncio.create_task(timer()),
    ]
    if not skip_mexc:
        task_list.insert(2, asyncio.create_task(collect_mexc()))
    await asyncio.gather(*task_list, return_exceptions=True)


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def bucket_and_returns(
    ticks_a: list[tuple[float, float]],
    ticks_b: list[tuple[float, float]],
    bucket_sec: float = 0.1,
) -> tuple[np.ndarray, np.ndarray]:
    """Align two tick series to common time buckets, return log returns."""
    if not ticks_a or not ticks_b:
        return np.array([]), np.array([])

    def to_bucket(t):
        return round(t / bucket_sec) * bucket_sec

    a_dict = {to_bucket(t): m for t, m in ticks_a}
    b_dict = {to_bucket(t): m for t, m in ticks_b}

    common = sorted(set(a_dict) & set(b_dict))
    if len(common) < 50:
        return np.array([]), np.array([])

    a_arr = np.array([a_dict[t] for t in common])
    b_arr = np.array([b_dict[t] for t in common])

    return np.diff(np.log(a_arr)), np.diff(np.log(b_arr))


def cross_corr(x, y, max_lag=30):
    n = len(x)
    results = []
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            xs = x[:n - lag] if lag > 0 else x
            ys = y[lag:] if lag > 0 else y
        else:
            xs = x[-lag:]
            ys = y[:n + lag]
        if len(xs) < 20:
            continue
        c = np.corrcoef(xs, ys)[0, 1]
        ne = len(xs)
        t = c * np.sqrt(ne - 2) / np.sqrt(1 - c**2 + 1e-15)
        results.append({"lag": lag, "corr": c, "t": t, "n": ne})
    return results


def find_peak_lag(results, bucket_ms):
    pos = [r for r in results if r["lag"] > 0 and r["t"] > 1.96]
    if not pos:
        return None
    return max(pos, key=lambda r: r["corr"])


def response_delay(x, y, bucket_ms, max_lag=30):
    n = len(x)
    cum = 0
    total = 0
    for lag in range(max_lag + 1):
        xs = x[:n - lag] if lag > 0 else x
        ys = y[lag:] if lag > 0 else y
        if len(xs) < 20:
            break
        r2 = np.corrcoef(xs, ys)[0, 1] ** 2
        total += r2
    if total == 0:
        return {"ms_50": None, "ms_90": None}

    cum = 0
    ms_50 = ms_90 = None
    for lag in range(max_lag + 1):
        xs = x[:n - lag] if lag > 0 else x
        ys = y[lag:] if lag > 0 else y
        if len(xs) < 20:
            break
        r2 = np.corrcoef(xs, ys)[0, 1] ** 2
        cum += r2
        if ms_50 is None and cum >= total * 0.5:
            ms_50 = lag * bucket_ms
        if ms_90 is None and cum >= total * 0.9:
            ms_90 = lag * bucket_ms
    return {"ms_50": ms_50, "ms_90": ms_90}


def analyze(bucket_ms=100):
    bucket_sec = bucket_ms / 1000

    print(f"\n{'=' * 70}")
    print(f"Analysis ({bucket_ms}ms buckets)")
    print(f"{'=' * 70}")

    print(f"\nTick counts: " + ", ".join(f"{k}={len(v)}" for k, v in ticks.items()))

    # Tick rate
    for name, data in ticks.items():
        if len(data) >= 2:
            duration = data[-1][0] - data[0][0]
            rate = len(data) / duration if duration > 0 else 0
            print(f"  {name}: {rate:.1f} ticks/s")

    pairs = [
        ("Binance", "Bitget", ticks["binance"], ticks["bitget"]),
        ("Binance", "MEXC", ticks["binance"], ticks["mexc"]),
        ("Binance", "GMO", ticks["binance"], ticks["gmo"]),
    ]

    for leader_name, follower_name, leader_ticks, follower_ticks in pairs:
        print(f"\n{'=' * 70}")
        print(f"{leader_name} → {follower_name}")
        print(f"{'=' * 70}")

        x_ret, y_ret = bucket_and_returns(leader_ticks, follower_ticks, bucket_sec)
        if len(x_ret) < 50:
            print(f"  Insufficient aligned data ({len(x_ret)} points)")
            continue

        print(f"  Aligned returns: {len(x_ret)}")

        # Cross-correlation
        results = cross_corr(x_ret, y_ret, max_lag=20)

        print(f"\n  {'lag':>4} {'ms':>6} {'corr':>8} {'t':>8} {'sig':>4}")
        print("  " + "-" * 36)
        for r in results:
            if r["lag"] % 2 == 0 or abs(r["lag"]) <= 3:
                sig = "***" if abs(r["t"]) > 3.29 else ("**" if abs(r["t"]) > 2.58 else ("*" if abs(r["t"]) > 1.96 else ""))
                print(f"  {r['lag']:>4} {r['lag'] * bucket_ms:>5}ms {r['corr']:>8.4f} {r['t']:>8.2f} {sig:>4}")

        # Peak lag
        peak = find_peak_lag(results, bucket_ms)
        if peak:
            print(f"\n  Peak positive lag: {peak['lag']} ({peak['lag'] * bucket_ms}ms), "
                  f"corr={peak['corr']:.4f}, t={peak['t']:.1f}")

        # Response delay
        delay = response_delay(x_ret, y_ret, bucket_ms)
        print(f"  Info transfer: 50% by {delay['ms_50']}ms, 90% by {delay['ms_90']}ms")

    # ===================================================================
    # Summary comparison
    # ===================================================================
    print(f"\n{'=' * 70}")
    print("SUMMARY: Which exchange can we snipe?")
    print(f"{'=' * 70}")

    for leader_name, follower_name, leader_ticks, follower_ticks in pairs:
        x_ret, y_ret = bucket_and_returns(leader_ticks, follower_ticks, bucket_sec)
        if len(x_ret) < 50:
            print(f"\n  {follower_name}: insufficient data")
            continue

        results = cross_corr(x_ret, y_ret, max_lag=20)
        peak = find_peak_lag(results, bucket_ms)
        delay = response_delay(x_ret, y_ret, bucket_ms)

        # Estimate API latency for the follower exchange
        api_latency = {"Bitget": 50, "MEXC": 50, "GMO": 500}[follower_name]

        # What's the correlation at the API-latency lag?
        api_lag_buckets = max(int(api_latency / bucket_ms), 1)
        api_lag_corr = next((r for r in results if r["lag"] == api_lag_buckets), None)

        print(f"\n  {follower_name}:")
        peak_ms = f"{peak['lag'] * bucket_ms}ms" if peak else "?"
        peak_corr = f"{peak['corr']:.3f}" if peak else "N/A"
        print(f"    Peak lag: {peak_ms} (corr={peak_corr})")
        print(f"    90% info by: {delay['ms_90']}ms")
        print(f"    Est. API latency: ~{api_latency}ms ({api_lag_buckets} buckets)")
        if api_lag_corr:
            print(f"    Corr at API lag: {api_lag_corr['corr']:.4f} (t={api_lag_corr['t']:.1f})")
        if peak and delay["ms_90"] is not None:
            tradeable = delay["ms_90"] > api_latency
            print(f"    Signal outlives API latency: {'YES' if tradeable else 'NO'}")
            if tradeable:
                print(f"    --> POTENTIALLY SNIPING CANDIDATE")
            else:
                print(f"    --> Signal too fast for this exchange")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=180, help="Collection duration in seconds")
    parser.add_argument("--bucket-ms", type=int, default=100)
    parser.add_argument("--skip-mexc", action="store_true", help="Skip MEXC collection")
    args = parser.parse_args()

    print("=" * 70)
    print("Cross-Exchange Latency Measurement")
    print("  Binance (leader) vs Bitget / MEXC / GMO")
    print("=" * 70)

    try:
        asyncio.run(run_collection(args.duration, skip_mexc=args.skip_mexc))
    except KeyboardInterrupt:
        pass

    analyze(args.bucket_ms)


if __name__ == "__main__":
    main()
