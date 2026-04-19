"""Bitget Funding Rate Monitor + Paper Trade Logger.

Monitors all 542 perpetual pairs for extreme funding rates.
Logs opportunities and simulates paper trades (no real orders).

Outputs:
  scripts/data_cache/fr_snapshots_{date}.csv   — all extreme FR snapshots
  scripts/data_cache/fr_paper_trades.csv       — paper trade log (persistent)

Usage:
    python3 scripts/fr_monitor.py                    # default: poll every 5 min
    caffeinate -i python3 scripts/fr_monitor.py      # prevent Mac sleep
    python3 scripts/fr_monitor.py --interval 60      # poll every 60s
    python3 scripts/fr_monitor.py --report            # show summary of collected data
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _monitor_lock import acquire_lock  # noqa: E402

CACHE_DIR = Path(__file__).parent / "data_cache"
CACHE_DIR.mkdir(exist_ok=True)

PAPER_TRADES_FILE = CACHE_DIR / "fr_paper_trades.csv"
FR_THRESHOLD = 0.001  # 0.1% per 8h

BITGET_BASE = "https://api.bitget.com/api/v2"
HEADERS = {"User-Agent": "fr-monitor/1.0"}


def api_get(path: str) -> dict:
    url = f"{BITGET_BASE}{path}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def load_market_info() -> tuple[set, dict]:
    """Load spot symbols and margin borrowability. Cached per session."""
    spot_data = api_get("/spot/public/symbols")
    spot_set = {s["symbol"] for s in spot_data.get("data", [])}

    margin_data = api_get("/margin/currencies")
    borrow_map = {}
    for m in margin_data.get("data", []):
        coin = m["baseCoin"]
        borrowable = (
            m.get("isBorrowable") in [True, "true"]
            or m.get("isIsolatedBaseBorrowable") in [True, "true"]
            or m.get("isCrossBorrowable") in [True, "true"]
        )
        borrow_map[coin] = borrowable

    return spot_set, borrow_map


def get_all_funding_rates() -> list[dict]:
    data = api_get("/mix/market/tickers?productType=USDT-FUTURES")
    return data.get("data", [])


def classify_opportunity(fr: float, coin: str, has_spot: bool, can_borrow: bool) -> str:
    """Classify if an FR opportunity is hedgeable."""
    if fr > 0:
        # Positive FR: SHORT perp + BUY spot (no borrowing needed)
        return "HEDGE_OK" if has_spot else "NO_SPOT"
    else:
        # Negative FR: LONG perp + SHORT spot (needs borrowing)
        if has_spot and can_borrow:
            return "HEDGE_OK"
        elif has_spot:
            return "NO_BORROW"
        else:
            return "NO_SPOT"


def write_snapshot(tickers: list[dict], spot_set: set, borrow_map: dict):
    """Write extreme FR snapshot to daily CSV."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    path = CACHE_DIR / f"fr_snapshots_{date_str}.csv"

    is_new = not path.exists() or path.stat().st_size == 0

    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow([
                "timestamp", "symbol", "funding_rate", "annualized",
                "volume_24h", "has_spot", "can_borrow", "hedge_status",
                "last_price", "spread",
            ])

        count = 0
        for t in tickers:
            fr = float(t.get("fundingRate", 0))
            if abs(fr) < FR_THRESHOLD:
                continue

            coin = t["symbol"].replace("USDT", "")
            has_spot = (coin + "USDT") in spot_set
            can_borrow = borrow_map.get(coin, False)
            hedge = classify_opportunity(fr, coin, has_spot, can_borrow)
            vol = float(t.get("quoteVolume", 0))
            last = float(t.get("lastPr", 0))
            bid = float(t.get("bidPr", 0))
            ask = float(t.get("askPr", 0))
            spread = ask - bid if bid > 0 else 0

            writer.writerow([
                now.isoformat(),
                t["symbol"],
                f"{fr:.6f}",
                f"{fr * 3 * 365 * 100:.1f}",
                f"{vol:.0f}",
                has_spot,
                can_borrow,
                hedge,
                f"{last}",
                f"{spread}",
            ])
            count += 1

    return count


class PaperTrader:
    """Simulate FR arbitrage trades without real orders."""

    def __init__(self, capital: float = 87.0, leverage: float = 5.0):
        self.capital = capital
        self.leverage = leverage
        self.positions: dict[str, dict] = {}  # symbol -> position info
        self.trade_log: list[dict] = []
        self._load_log()

    def _load_log(self):
        if PAPER_TRADES_FILE.exists():
            with open(PAPER_TRADES_FILE) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.trade_log.append(row)
            # Rebuild open positions from log
            for row in self.trade_log:
                sym = row["symbol"]
                if row["action"] == "OPEN":
                    self.positions[sym] = {
                        "entry_price": float(row["price"]),
                        "direction": row["direction"],
                        "size_usd": float(row["size_usd"]),
                        "entry_time": row["timestamp"],
                        "entry_fr": float(row["funding_rate"]),
                        "fr_collected": 0,
                    }
                elif row["action"] == "FR_COLLECT" and sym in self.positions:
                    self.positions[sym]["fr_collected"] += float(row["pnl"])
                elif row["action"] == "CLOSE" and sym in self.positions:
                    del self.positions[sym]

    def _append_log(self, row: dict):
        is_new = not PAPER_TRADES_FILE.exists() or PAPER_TRADES_FILE.stat().st_size == 0
        with open(PAPER_TRADES_FILE, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "timestamp", "symbol", "action", "direction", "price",
                "size_usd", "funding_rate", "pnl", "hedge_status", "note",
            ])
            if is_new:
                writer.writeheader()
            writer.writerow(row)
        self.trade_log.append(row)

    def check_opportunities(self, tickers: list[dict], spot_set: set, borrow_map: dict):
        now = datetime.now(timezone.utc)
        max_positions = 3
        position_size = self.capital / (max_positions * 1.2)  # split capital

        for t in tickers:
            sym = t["symbol"]
            fr = float(t.get("fundingRate", 0))
            coin = sym.replace("USDT", "")
            has_spot = (coin + "USDT") in spot_set
            can_borrow = borrow_map.get(coin, False)
            hedge = classify_opportunity(fr, coin, has_spot, can_borrow)
            vol = float(t.get("quoteVolume", 0))
            last = float(t.get("lastPr", 0))

            # Open new position if extreme FR + hedgeable + has volume
            if (
                sym not in self.positions
                and len(self.positions) < max_positions
                and abs(fr) > FR_THRESHOLD
                and hedge == "HEDGE_OK"
                and vol > 500000
                and last > 0
            ):
                direction = "SHORT" if fr > 0 else "LONG"
                self._append_log({
                    "timestamp": now.isoformat(),
                    "symbol": sym,
                    "action": "OPEN",
                    "direction": direction,
                    "price": f"{last}",
                    "size_usd": f"{position_size:.2f}",
                    "funding_rate": f"{fr:.6f}",
                    "pnl": "0",
                    "hedge_status": hedge,
                    "note": f"FR={fr*100:.3f}%/8h, vol=${vol:,.0f}",
                })
                self.positions[sym] = {
                    "entry_price": last,
                    "direction": direction,
                    "size_usd": position_size,
                    "entry_time": now.isoformat(),
                    "entry_fr": fr,
                    "fr_collected": 0,
                }
                print(f"  [PAPER] OPEN {direction} {sym} @ {last}, FR={fr*100:.3f}%")

            # Collect FR for open positions
            if sym in self.positions and abs(fr) > 0:
                pos = self.positions[sym]
                fr_income = abs(fr) * pos["size_usd"]
                pos["fr_collected"] += fr_income

            # Close if FR normalized
            if sym in self.positions and abs(fr) < FR_THRESHOLD * 0.5:
                pos = self.positions[sym]
                price_change = (last - pos["entry_price"]) / pos["entry_price"]
                if pos["direction"] == "SHORT":
                    price_change = -price_change
                price_pnl = price_change * pos["size_usd"]
                fr_pnl = pos["fr_collected"]
                fee = pos["size_usd"] * 0.0006 * 2  # entry + exit perp fee
                total_pnl = price_pnl + fr_pnl - fee

                self._append_log({
                    "timestamp": now.isoformat(),
                    "symbol": sym,
                    "action": "CLOSE",
                    "direction": pos["direction"],
                    "price": f"{last}",
                    "size_usd": f"{pos['size_usd']:.2f}",
                    "funding_rate": f"{fr:.6f}",
                    "pnl": f"{total_pnl:.4f}",
                    "hedge_status": "HEDGE_OK",
                    "note": f"price_pnl=${price_pnl:.2f}, fr=${fr_pnl:.4f}, fee=${fee:.4f}",
                })
                print(f"  [PAPER] CLOSE {sym} PnL=${total_pnl:.4f} (price=${price_pnl:.2f}, FR=${fr_pnl:.4f})")
                del self.positions[sym]

    def summary(self):
        closed = [r for r in self.trade_log if r["action"] == "CLOSE"]
        if not closed:
            print("  No closed paper trades yet.")
            return
        pnls = [float(r["pnl"]) for r in closed]
        print(f"  Closed trades: {len(closed)}")
        print(f"  Total P&L: ${sum(pnls):.4f}")
        print(f"  Avg P&L: ${sum(pnls)/len(pnls):.4f}")
        print(f"  Win rate: {sum(1 for p in pnls if p > 0)/len(pnls)*100:.0f}%")
        print(f"  Open positions: {len(self.positions)}")
        for sym, pos in self.positions.items():
            print(f"    {sym}: {pos['direction']} @ {pos['entry_price']}, FR collected=${pos['fr_collected']:.4f}")


def report():
    """Show summary of all collected data."""
    print("=" * 60)
    print("FR Monitor Report")
    print("=" * 60)

    # Count snapshot files
    snapshots = sorted(CACHE_DIR.glob("fr_snapshots_*.csv"))
    total_rows = 0
    for path in snapshots:
        with open(path) as f:
            rows = sum(1 for _ in f) - 1  # minus header
        total_rows += rows
        print(f"  {path.name}: {rows} extreme FR observations")

    print(f"\n  Total observations: {total_rows}")

    if snapshots:
        # Analyze latest file
        latest = snapshots[-1]
        with open(latest) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if rows:
            symbols = set(r["symbol"] for r in rows)
            hedge_ok = sum(1 for r in rows if r["hedge_status"] == "HEDGE_OK")
            print(f"\n  Latest file ({latest.name}):")
            print(f"    Unique tokens with extreme FR: {len(symbols)}")
            print(f"    Hedgeable observations: {hedge_ok}/{len(rows)}")

    # Paper trade summary
    print(f"\n  Paper Trades:")
    trader = PaperTrader()
    trader.summary()


def main():
    parser = argparse.ArgumentParser(description="Bitget FR Monitor")
    parser.add_argument("--interval", type=int, default=300, help="Poll interval in seconds")
    parser.add_argument("--report", action="store_true", help="Show report and exit")
    args = parser.parse_args()

    if args.report:
        report()
        return

    acquire_lock("fr_monitor")

    print("=" * 60)
    print("Bitget Funding Rate Monitor")
    print(f"  Threshold: |FR| > {FR_THRESHOLD*100:.1f}%/8h")
    print(f"  Poll interval: {args.interval}s")
    print(f"  Output: {CACHE_DIR}/fr_snapshots_*.csv")
    print(f"  Paper trades: {PAPER_TRADES_FILE}")
    print("=" * 60)

    print("\nLoading market info (spot symbols, margin borrowability)...")
    spot_set, borrow_map = load_market_info()
    print(f"  Spot pairs: {len(spot_set)}, Borrowable coins: {sum(borrow_map.values())}")

    trader = PaperTrader()
    print(f"  Open paper positions: {len(trader.positions)}")

    poll_count = 0
    print("\nMonitoring... (Ctrl+C to stop)\n")

    try:
        while True:
            try:
                tickers = get_all_funding_rates()
                count = write_snapshot(tickers, spot_set, borrow_map)
                trader.check_opportunities(tickers, spot_set, borrow_map)

                poll_count += 1
                now = datetime.now(timezone.utc).strftime("%H:%M:%S")
                extreme = sum(1 for t in tickers if abs(float(t.get("fundingRate", 0))) > FR_THRESHOLD)
                hedgeable = sum(
                    1 for t in tickers
                    if abs(float(t.get("fundingRate", 0))) > FR_THRESHOLD
                    and classify_opportunity(
                        float(t.get("fundingRate", 0)),
                        t["symbol"].replace("USDT", ""),
                        (t["symbol"].replace("USDT", "") + "USDT") in spot_set,
                        borrow_map.get(t["symbol"].replace("USDT", ""), False),
                    ) == "HEDGE_OK"
                )

                print(f"  [{now}] #{poll_count}: extreme={extreme}, hedgeable={hedgeable}, "
                      f"paper_open={len(trader.positions)}")

                # Refresh market info every 100 polls
                if poll_count % 100 == 0:
                    spot_set, borrow_map = load_market_info()

            except Exception as e:
                print(f"  ERROR: {e}")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\nStopped after {poll_count} polls.")
        print("\nFinal summary:")
        trader.summary()


if __name__ == "__main__":
    main()
