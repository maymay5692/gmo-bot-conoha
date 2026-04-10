"""bitFlyer FX_BTC_JPY ticker を3秒間隔で収集して CSV に保存。

VPS 上で bot と並行して実行:
  python3 scripts/collect_bitflyer.py

GMO の metrics.csv と同じ時間軸で bitFlyer の価格を記録し、
cross-exchange lead-lag 分析に使用する。

出力: scripts/data_cache/bitflyer_ticker_{date}.csv
"""
import csv
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

INTERVAL_S = 3
URL = "https://api.bitflyer.com/v1/getboard?product_code=FX_BTC_JPY"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "data_cache")


def fetch_ticker():
    req = urllib.request.Request(URL, headers={"User-Agent": "gmo-bot-conoha/1.0"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
    bids = data.get("bids", [])
    asks = data.get("asks", [])
    best_bid = bids[0]["price"] if bids else 0
    best_ask = asks[0]["price"] if asks else 0
    mid = data.get("mid_price", (best_bid + best_ask) / 2)
    return best_bid, best_ask, mid


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)

    current_date = None
    writer = None
    f = None
    tick_count = 0

    print(f"bitFlyer FX_BTC_JPY ticker collector (interval={INTERVAL_S}s)")
    print(f"Output: {CACHE_DIR}/bitflyer_ticker_YYYY-MM-DD.csv")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            now = datetime.now(timezone.utc)
            date_str = now.strftime("%Y-%m-%d")

            if date_str != current_date:
                if f:
                    f.close()
                path = os.path.join(CACHE_DIR, f"bitflyer_ticker_{date_str}.csv")
                f = open(path, "a", newline="")
                writer = csv.writer(f)
                if os.path.getsize(path) == 0:
                    writer.writerow(["timestamp", "best_bid", "best_ask", "mid_price"])
                current_date = date_str
                print(f"Writing to {path}")

            try:
                bid, ask, mid = fetch_ticker()
                ts = now.isoformat()
                writer.writerow([ts, f"{bid:.0f}", f"{ask:.0f}", f"{mid:.0f}"])
                f.flush()
                tick_count += 1
                if tick_count % 100 == 0:
                    print(f"  {ts} mid={mid:.0f} spread={ask-bid:.0f} ({tick_count} ticks)")
            except Exception as e:
                print(f"  {now.isoformat()} ERROR: {e}")

            time.sleep(INTERVAL_S)

    except KeyboardInterrupt:
        print(f"\nStopped. {tick_count} ticks collected.")
    finally:
        if f:
            f.close()


if __name__ == "__main__":
    main()
