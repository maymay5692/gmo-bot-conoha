"""Measure Bitget ORDER BOOK update frequency and lead-lag vs Binance.

This answers: are Bitget's actual bid/ask stale relative to Binance,
or is it only the ticker that's slow?

Usage:
    python3 scripts/measure_orderbook.py [--duration 300]
"""
import argparse
import asyncio
import json
import time
from datetime import datetime, timezone

import numpy as np
import websockets
from scipy import stats

ticks: dict[str, list[tuple[float, float, float, float]]] = {
    "binance": [],      # (monotonic_ts, mid, bid, ask)
    "bitget_book": [],  # (monotonic_ts, mid, bid, ask)
    "bitget_ticker": [],
}
counts = {"binance": 0, "bitget_book": 0, "bitget_ticker": 0}
stop_event = asyncio.Event()


async def collect_binance():
    uri = "wss://stream.binance.com:9443/ws/btcusdt@bookTicker"
    async with websockets.connect(uri, ping_interval=20) as ws:
        async for raw in ws:
            if stop_event.is_set():
                return
            data = json.loads(raw)
            bid = float(data.get("b", 0))
            ask = float(data.get("a", 0))
            mid = (bid + ask) / 2
            ticks["binance"].append((time.monotonic(), mid, bid, ask))
            counts["binance"] += 1


async def collect_bitget_book():
    uri = "wss://ws.bitget.com/v2/ws/public"
    sub = json.dumps({
        "op": "subscribe",
        "args": [{"instType": "USDT-FUTURES", "channel": "books5", "instId": "BTCUSDT"}],
    })
    async with websockets.connect(uri, ping_interval=20) as ws:
        await ws.send(sub)
        async for raw in ws:
            if stop_event.is_set():
                return
            data = json.loads(raw)
            items = data.get("data", [])
            if not isinstance(items, list) or not items:
                continue
            book = items[0]
            asks = book.get("asks", [])
            bids = book.get("bids", [])
            if not asks or not bids:
                continue
            best_ask = float(asks[0][0])
            best_bid = float(bids[0][0])
            mid = (best_ask + best_bid) / 2
            spread = best_ask - best_bid
            ticks["bitget_book"].append((time.monotonic(), mid, best_bid, best_ask))
            counts["bitget_book"] += 1


async def collect_bitget_ticker():
    uri = "wss://ws.bitget.com/v2/ws/public"
    sub = json.dumps({
        "op": "subscribe",
        "args": [{"instType": "USDT-FUTURES", "channel": "ticker", "instId": "BTCUSDT"}],
    })
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
            ticks["bitget_ticker"].append((time.monotonic(), mid, bid, ask))
            counts["bitget_ticker"] += 1


async def printer(duration):
    t0 = time.monotonic()
    while not stop_event.is_set():
        await asyncio.sleep(15)
        e = time.monotonic() - t0
        r = duration - e
        print(f"  [{e:.0f}s] bn={counts['binance']} bg_book={counts['bitget_book']} "
              f"bg_tick={counts['bitget_ticker']} (残り{r:.0f}s)")


async def run(duration):
    print(f"Collecting for {duration}s: Binance bookTicker + Bitget books5 + Bitget ticker\n")

    async def timer():
        await asyncio.sleep(duration)
        stop_event.set()

    await asyncio.gather(
        collect_binance(),
        collect_bitget_book(),
        collect_bitget_ticker(),
        printer(duration),
        timer(),
        return_exceptions=True,
    )


def align_returns(a_ticks, b_ticks, bucket_sec):
    a_dict = {round(t / bucket_sec) * bucket_sec: m for t, m, _, _ in a_ticks}
    b_dict = {round(t / bucket_sec) * bucket_sec: m for t, m, _, _ in b_ticks}
    common = sorted(set(a_dict) & set(b_dict))
    if len(common) < 30:
        return None, None, 0
    a = np.array([a_dict[t] for t in common])
    b = np.array([b_dict[t] for t in common])
    return np.diff(np.log(a)), np.diff(np.log(b)), len(common)


def cross_corr(x, y, max_lag=20):
    n = len(x)
    out = []
    for lag in range(-max_lag, max_lag + 1):
        xs = x[max(0, -lag):n - max(0, lag)]
        ys = y[max(0, lag):n - max(0, -lag)]
        if len(xs) < 20:
            continue
        c = np.corrcoef(xs, ys)[0, 1]
        ne = len(xs)
        t = c * np.sqrt(ne - 2) / np.sqrt(1 - c**2 + 1e-15)
        out.append({"lag": lag, "corr": c, "t": t, "n": ne})
    return out


def analyze():
    print(f"\n{'=' * 70}")
    print("RESULTS")
    print("=" * 70)

    # Update frequency comparison
    print("\n--- Update Frequency ---")
    for name, data in ticks.items():
        if len(data) < 2:
            print(f"  {name}: insufficient data ({len(data)} ticks)")
            continue
        duration = data[-1][0] - data[0][0]
        rate = len(data) / duration if duration > 0 else 0
        intervals = np.diff([t for t, _, _, _ in data]) * 1000
        print(f"  {name}: {len(data)} ticks, {rate:.1f}/s")
        print(f"    interval: mean={np.mean(intervals):.0f}ms, "
              f"median={np.median(intervals):.0f}ms, "
              f"p10={np.percentile(intervals, 10):.0f}ms, "
              f"p90={np.percentile(intervals, 90):.0f}ms")

    # Spread comparison
    print("\n--- Bitget Spread ---")
    for name in ["bitget_book", "bitget_ticker"]:
        data = ticks[name]
        if len(data) < 2:
            continue
        spreads = np.array([ask - bid for _, _, bid, ask in data])
        print(f"  {name}: mean=${np.mean(spreads):.2f}, "
              f"median=${np.median(spreads):.2f}, "
              f"p90=${np.percentile(spreads, 90):.2f}")

    # Bucket-size sensitivity: THE critical test
    print(f"\n--- Bucket-Size Sensitivity (Binance → Bitget book) ---")
    print(f"  If peak is always 'lag 1' → artifact. If peak_ms is stable → real lag.")
    print(f"\n  {'bucket':>8} {'N':>6} {'peak_lag':>8} {'peak_ms':>8} {'corr':>8}")
    print("  " + "-" * 45)
    for bms in [50, 100, 150, 200, 300, 500, 1000]:
        x, y, n = align_returns(ticks["binance"], ticks["bitget_book"], bms / 1000)
        if x is None:
            print(f"  {bms:>7}ms   insufficient data")
            continue
        res = cross_corr(x, y, max_lag=10)
        pos = [r for r in res if r["lag"] >= 0]
        best = max(pos, key=lambda r: r["corr"])
        sig = "***" if abs(best["t"]) > 3.29 else ("**" if abs(best["t"]) > 2.58 else "*" if abs(best["t"]) > 1.96 else "")
        print(f"  {bms:>7}ms {n:>6} {best['lag']:>8} {best['lag'] * bms:>7}ms {best['corr']:>8.4f} {sig}")

    # Same for ticker (for comparison)
    print(f"\n--- Bucket-Size Sensitivity (Binance → Bitget TICKER) ---")
    print(f"  {'bucket':>8} {'N':>6} {'peak_lag':>8} {'peak_ms':>8} {'corr':>8}")
    print("  " + "-" * 45)
    for bms in [50, 100, 150, 200, 300, 500, 1000]:
        x, y, n = align_returns(ticks["binance"], ticks["bitget_ticker"], bms / 1000)
        if x is None:
            print(f"  {bms:>7}ms   insufficient data")
            continue
        res = cross_corr(x, y, max_lag=10)
        pos = [r for r in res if r["lag"] >= 0]
        best = max(pos, key=lambda r: r["corr"])
        sig = "***" if abs(best["t"]) > 3.29 else ("**" if abs(best["t"]) > 2.58 else "*" if abs(best["t"]) > 1.96 else "")
        print(f"  {bms:>7}ms {n:>6} {best['lag']:>8} {best['lag'] * bms:>7}ms {best['corr']:>8.4f} {sig}")

    # Full cross-correlation at 100ms (book vs ticker comparison)
    print(f"\n--- Cross-Correlation at 100ms: Book vs Ticker ---")
    for name, data in [("bitget_book", ticks["bitget_book"]),
                       ("bitget_ticker", ticks["bitget_ticker"])]:
        x, y, n = align_returns(ticks["binance"], data, 0.1)
        if x is None:
            print(f"  {name}: insufficient data")
            continue
        res = cross_corr(x, y, max_lag=15)
        print(f"\n  Binance → {name} (N={n})")
        print(f"  {'lag':>4} {'ms':>6} {'corr':>8} {'t':>8} {'sig':>4}")
        print("  " + "-" * 36)
        for r in res:
            if r["lag"] % 2 == 0 or abs(r["lag"]) <= 3:
                sig = "***" if abs(r["t"]) > 3.29 else ("**" if abs(r["t"]) > 2.58 else ("*" if abs(r["t"]) > 1.96 else ""))
                print(f"  {r['lag']:>4} {r['lag'] * 100:>5}ms {r['corr']:>8.4f} {r['t']:>8.2f} {sig:>4}")

    # Verdict
    print(f"\n{'=' * 70}")
    print("VERDICT")
    print("=" * 70)

    x_book, y_book, n_book = align_returns(ticks["binance"], ticks["bitget_book"], 0.1)
    x_tick, y_tick, n_tick = align_returns(ticks["binance"], ticks["bitget_ticker"], 0.1)

    if x_book is not None:
        res_book = cross_corr(x_book, y_book, 10)
        lag0_book = next((r for r in res_book if r["lag"] == 0), None)
        lag1_book = next((r for r in res_book if r["lag"] == 1), None)
        if lag0_book and lag1_book:
            ratio = lag0_book["corr"] / lag1_book["corr"] if lag1_book["corr"] > 0 else 0
            print(f"\n  Book:   lag0={lag0_book['corr']:.4f}, lag1={lag1_book['corr']:.4f}, ratio={ratio:.2f}")
            if lag0_book["corr"] > lag1_book["corr"]:
                print("  --> Book is FAST: most info absorbed at lag 0 (contemporaneous)")
                print("  --> Sniping is NOT viable — MM quotes are not stale")
            else:
                print("  --> Book is SLOW: info still arriving at lag 1+")
                print("  --> Stale quotes MAY exist — sniping POTENTIALLY viable")

    if x_tick is not None:
        res_tick = cross_corr(x_tick, y_tick, 10)
        lag0_tick = next((r for r in res_tick if r["lag"] == 0), None)
        lag1_tick = next((r for r in res_tick if r["lag"] == 1), None)
        if lag0_tick and lag1_tick:
            ratio = lag0_tick["corr"] / lag1_tick["corr"] if lag1_tick["corr"] > 0 else 0
            print(f"\n  Ticker: lag0={lag0_tick['corr']:.4f}, lag1={lag1_tick['corr']:.4f}, ratio={ratio:.2f}")
            print("  (Ticker is slower than book — expected)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=300)
    args = parser.parse_args()

    print("=" * 70)
    print("Bitget Order Book vs Ticker: True Update Speed")
    print("=" * 70)

    try:
        asyncio.run(run(args.duration))
    except KeyboardInterrupt:
        pass

    analyze()


if __name__ == "__main__":
    main()
