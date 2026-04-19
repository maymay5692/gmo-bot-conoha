"""WebSocket ticker collector: bitFlyer FX + Binance BTC/USDT + GMO BTC_JPY.

Sub-second resolution for cross-exchange lead-lag analysis.
Each exchange writes to its own CSV with microsecond timestamps.

Usage:
    python3 scripts/collect_ws.py                  # default
    caffeinate -i python3 scripts/collect_ws.py    # prevent Mac sleep

Output:
    scripts/data_cache/ws_bitflyer_{date}.csv
    scripts/data_cache/ws_binance_{date}.csv
    scripts/data_cache/ws_gmo_{date}.csv
"""
import asyncio
import csv
import json
import os
import signal
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import websockets

CACHE_DIR = Path(__file__).parent / "data_cache"
CACHE_DIR.mkdir(exist_ok=True)

# GMO polling interval (they don't have public WebSocket for BTC_JPY ticker)
GMO_POLL_INTERVAL = 0.5  # 500ms — much faster than old 3s
GMO_URL = "https://api.coin.z.com/public/v1/ticker?symbol=BTC_JPY"

# Stats tracking
stats = {"bitflyer": 0, "binance": 0, "gmo": 0, "errors": 0}
start_time = time.time()


class CsvWriter:
    """Date-rotating CSV writer."""

    def __init__(self, prefix: str, columns: list[str]):
        self.prefix = prefix
        self.columns = columns
        self._current_date = None
        self._file = None
        self._writer = None

    def write(self, row: dict):
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")

        if date_str != self._current_date:
            self._rotate(date_str)

        self._writer.writerow([row.get(c, "") for c in self.columns])
        self._file.flush()

    def _rotate(self, date_str: str):
        if self._file:
            self._file.close()
        path = CACHE_DIR / f"{self.prefix}_{date_str}.csv"
        is_new = not path.exists() or path.stat().st_size == 0
        self._file = open(path, "a", newline="")
        self._writer = csv.writer(self._file)
        if is_new:
            self._writer.writerow(self.columns)
        self._current_date = date_str

    def close(self):
        if self._file:
            self._file.close()


# ---------------------------------------------------------------------------
# bitFlyer FX_BTC_JPY (WebSocket, event-driven)
# ---------------------------------------------------------------------------

async def collect_bitflyer(writer: CsvWriter):
    uri = "wss://ws.lightstream.bitflyer.com/json-rpc"
    subscribe = json.dumps({
        "method": "subscribe",
        "params": {"channel": "lightning_ticker_FX_BTC_JPY"},
    })

    while True:
        try:
            async with websockets.connect(uri, ping_interval=20) as ws:
                await ws.send(subscribe)
                async for raw in ws:
                    data = json.loads(raw)
                    msg = data.get("params", {}).get("message", {})
                    if not msg:
                        continue

                    now = datetime.now(timezone.utc)
                    bid = msg.get("best_bid", 0)
                    ask = msg.get("best_ask", 0)
                    mid = (bid + ask) / 2
                    ltp = msg.get("ltp", 0)

                    writer.write({
                        "local_ts": now.isoformat(),
                        "exchange_ts": msg.get("timestamp", ""),
                        "best_bid": f"{bid:.0f}",
                        "best_ask": f"{ask:.0f}",
                        "mid_price": f"{mid:.0f}",
                        "ltp": f"{ltp:.0f}",
                        "spread": f"{ask - bid:.0f}",
                    })
                    stats["bitflyer"] += 1

        except Exception as e:
            stats["errors"] += 1
            print(f"  [bitFlyer] reconnect: {e}")
            await asyncio.sleep(1)


# ---------------------------------------------------------------------------
# Binance BTC/USDT (WebSocket, event-driven)
# ---------------------------------------------------------------------------

async def collect_binance(writer: CsvWriter, min_interval_ms: int = 100):
    """Collect Binance bookTicker with throttle (default 100ms min interval).

    At ~50 updates/s, unthrottled = ~4.5M rows/day (~450MB).
    100ms throttle → ~10/s → ~864K rows/day (~86MB).
    """
    uri = "wss://stream.binance.com:9443/ws/btcusdt@bookTicker"
    min_interval = min_interval_ms / 1000.0

    while True:
        last_write = 0.0
        try:
            async with websockets.connect(uri, ping_interval=20) as ws:
                async for raw in ws:
                    now_mono = time.monotonic()
                    if now_mono - last_write < min_interval:
                        continue
                    last_write = now_mono

                    data = json.loads(raw)
                    now = datetime.now(timezone.utc)

                    bid = float(data.get("b", 0))
                    ask = float(data.get("a", 0))
                    mid = (bid + ask) / 2

                    writer.write({
                        "local_ts": now.isoformat(),
                        "update_id": str(data.get("u", "")),
                        "best_bid": f"{bid:.2f}",
                        "best_ask": f"{ask:.2f}",
                        "mid_price": f"{mid:.2f}",
                        "spread": f"{ask - bid:.2f}",
                    })
                    stats["binance"] += 1

        except Exception as e:
            stats["errors"] += 1
            print(f"  [Binance] reconnect: {e}")
            await asyncio.sleep(1)


# ---------------------------------------------------------------------------
# GMO BTC_JPY (HTTP polling — no public WS for ticker)
# ---------------------------------------------------------------------------

async def collect_gmo(writer: CsvWriter):
    while True:
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, _fetch_gmo)
            if data:
                now = datetime.now(timezone.utc)
                bid = float(data.get("bid", 0))
                ask = float(data.get("ask", 0))
                mid = (bid + ask) / 2
                ltp = float(data.get("last", 0))

                writer.write({
                    "local_ts": now.isoformat(),
                    "exchange_ts": data.get("timestamp", ""),
                    "best_bid": f"{bid:.0f}",
                    "best_ask": f"{ask:.0f}",
                    "mid_price": f"{mid:.0f}",
                    "ltp": f"{ltp:.0f}",
                    "spread": f"{ask - bid:.0f}",
                })
                stats["gmo"] += 1

        except Exception as e:
            stats["errors"] += 1

        await asyncio.sleep(GMO_POLL_INTERVAL)


def _fetch_gmo():
    req = urllib.request.Request(GMO_URL, headers={"User-Agent": "gmo-bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = json.loads(resp.read())
        if body.get("status") == 0:
            items = body.get("data", [])
            for item in items:
                if item.get("symbol") == "BTC_JPY":
                    return item
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Status printer
# ---------------------------------------------------------------------------

async def print_status():
    while True:
        await asyncio.sleep(30)
        elapsed = time.time() - start_time
        bf_rate = stats["bitflyer"] / elapsed if elapsed > 0 else 0
        bn_rate = stats["binance"] / elapsed if elapsed > 0 else 0
        gmo_rate = stats["gmo"] / elapsed if elapsed > 0 else 0
        print(
            f"  [{datetime.now(timezone.utc).strftime('%H:%M:%S')}] "
            f"bf={stats['bitflyer']:>6d} ({bf_rate:.1f}/s) "
            f"bn={stats['binance']:>6d} ({bn_rate:.1f}/s) "
            f"gmo={stats['gmo']:>6d} ({gmo_rate:.1f}/s) "
            f"err={stats['errors']}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print("WebSocket Ticker Collector — bitFlyer FX + Binance + GMO")
    print(f"Output: {CACHE_DIR}/ws_*_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.csv")
    print("Press Ctrl+C to stop.\n")

    bf_writer = CsvWriter("ws_bitflyer", [
        "local_ts", "exchange_ts", "best_bid", "best_ask", "mid_price", "ltp", "spread",
    ])
    bn_writer = CsvWriter("ws_binance", [
        "local_ts", "update_id", "best_bid", "best_ask", "mid_price", "spread",
    ])
    gmo_writer = CsvWriter("ws_gmo", [
        "local_ts", "exchange_ts", "best_bid", "best_ask", "mid_price", "ltp", "spread",
    ])

    try:
        await asyncio.gather(
            collect_bitflyer(bf_writer),
            collect_binance(bn_writer),
            collect_gmo(gmo_writer),
            print_status(),
        )
    except asyncio.CancelledError:
        pass
    finally:
        bf_writer.close()
        bn_writer.close()
        gmo_writer.close()
        elapsed = time.time() - start_time
        print(f"\nStopped after {elapsed:.0f}s. "
              f"bf={stats['bitflyer']} bn={stats['binance']} gmo={stats['gmo']}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print(f"\nStopped after {elapsed:.0f}s. "
              f"bf={stats['bitflyer']} bn={stats['binance']} gmo={stats['gmo']}")
