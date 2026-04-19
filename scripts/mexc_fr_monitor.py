"""MEXC Funding Rate Monitor + Paper Trade Logger.

Monitors all perpetual pairs for extreme funding rates.
Logs observations to daily CSV and simulates paper trades (no real orders).

Outputs:
  scripts/data_cache/mexc_fr_snapshots_{date}.csv — extreme FR snapshots
  scripts/data_cache/mexc_fr_paper_trades.csv    — paper trade log (persistent)

Usage:
    python3 scripts/mexc_fr_monitor.py                    # default: poll every 5 min
    caffeinate -i python3 scripts/mexc_fr_monitor.py      # prevent Mac sleep
    python3 scripts/mexc_fr_monitor.py --interval 60      # poll every 60s
    python3 scripts/mexc_fr_monitor.py --report            # show summary of collected data
"""
import argparse
import csv
import json
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _monitor_lock import acquire_lock  # noqa: E402

CACHE_DIR = Path(__file__).parent / "data_cache"
CACHE_DIR.mkdir(exist_ok=True)

PAPER_TRADES_FILE = CACHE_DIR / "mexc_fr_paper_trades.csv"
FR_THRESHOLD = 0.001  # 0.1% per 8h
MEXC_API_URL = "https://contract.mexc.com"
MEXC_SPOT_API = "https://api.mexc.com"


_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def api_get(path: str, base: str = MEXC_API_URL) -> object:
    """GET from a MEXC API base URL and return parsed JSON."""
    url = f"{base}/{path}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "mexc-fr-monitor/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
        return json.loads(resp.read())


def load_market_info() -> tuple[set, set]:
    """Fetch spot exchangeInfo and return (spot_set, margin_set).

    spot_set   — set of spot symbols like "BTCUSDT"
    margin_set — set of base assets where isMarginTradingAllowed is True

    MEXC v3 exchangeInfo encodes status as "1" (enabled) / "2" (disabled),
    not the legacy "ENABLED" string.
    """
    data = api_get("api/v3/exchangeInfo", base=MEXC_SPOT_API)
    symbols = data.get("symbols", [])
    spot_set: set[str] = set()
    margin_set: set[str] = set()
    for s in symbols:
        if s.get("status") == "1":
            symbol = s.get("symbol", "")
            if s.get("isSpotTradingAllowed"):
                spot_set.add(symbol)
            if s.get("isMarginTradingAllowed"):
                margin_set.add(s.get("baseAsset", ""))
    return spot_set, margin_set


def classify_opportunity(fr: float, coin: str, has_spot: bool, can_margin: bool) -> str:
    """Classify if an FR opportunity is hedgeable.

    Positive FR: SHORT perp + BUY spot (no borrowing needed).
    Negative FR: LONG perp + SHORT spot (needs margin/borrowing).
    """
    if fr > 0:
        return "HEDGE_OK" if has_spot else "NO_SPOT"
    else:
        if has_spot and can_margin:
            return "HEDGE_OK"
        elif has_spot:
            return "NO_BORROW"
        else:
            return "NO_SPOT"


def get_all_tickers() -> list[dict]:
    """Return list of ticker dicts from MEXC ticker endpoint."""
    data = api_get("api/v1/contract/ticker")
    return data.get("data", [])


def parse_tickers(tickers: list[dict]) -> list[dict]:
    """Return list of dicts with FR and market data for all pairs.

    Each dict contains: symbol, funding_rate, last_price,
    open_interest, volume_24h, bid1, ask1.
    """
    results = []
    for t in tickers:
        try:
            results.append({
                "symbol": t.get("symbol", ""),
                "funding_rate": float(t.get("fundingRate", 0) or 0),
                "last_price": float(t.get("lastPrice", 0) or 0),
                "open_interest": float(t.get("openInterest", 0) or 0),
                "volume_24h": float(t.get("volume24", 0) or 0),
                "bid1": float(t.get("bid1", 0) or 0),
                "ask1": float(t.get("ask1", 0) or 0),
            })
        except (ValueError, TypeError):
            continue
    return results


def write_snapshot(rates: list[dict], spot_set: set, margin_set: set) -> int:
    """Write extreme FR entries to daily CSV. Returns count written."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    path = CACHE_DIR / f"mexc_fr_snapshots_{date_str}.csv"

    is_new = not path.exists() or path.stat().st_size == 0

    count = 0
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow([
                "timestamp", "symbol", "funding_rate", "annualized",
                "volume_24h", "open_interest", "hedge_status",
                "last_price", "spread",
            ])

        for r in rates:
            fr = r["funding_rate"]
            if abs(fr) < FR_THRESHOLD:
                continue

            # Futures symbol is "BTC_USDT"; convert to spot lookup "BTCUSDT"
            coin = r["symbol"].replace("_USDT", "")
            spot_symbol = coin + "USDT"
            has_spot = spot_symbol in spot_set
            can_margin = coin in margin_set
            hedge = classify_opportunity(fr, coin, has_spot, can_margin)

            annualized = fr * 3 * 365 * 100
            bid1 = r["bid1"]
            ask1 = r["ask1"]
            spread = f"{ask1 - bid1:.6f}" if bid1 and ask1 else "0"

            writer.writerow([
                now.isoformat(),
                r["symbol"],
                f"{fr:.6f}",
                f"{annualized:.1f}",
                f"{r['volume_24h']:.0f}",
                f"{r['open_interest']:.4f}",
                hedge,
                f"{r['last_price']}",
                spread,
            ])
            count += 1

    return count


class PaperTrader:
    """Simulate FR arbitrage trades without real orders."""

    def __init__(self, capital: float = 87.0, max_positions: int = 3):
        self.capital = capital
        self.max_positions = max_positions
        self.positions: dict[str, dict] = {}
        self.trade_log: list[dict] = []
        self._load_log()

    def _load_log(self):
        if PAPER_TRADES_FILE.exists():
            with open(PAPER_TRADES_FILE) as f:
                for row in csv.DictReader(f):
                    self.trade_log.append(row)
            for row in self.trade_log:
                sym = row["symbol"]
                if row["action"] == "OPEN":
                    self.positions[sym] = {
                        "entry_price": float(row["price"]),
                        "direction": row["direction"],
                        "size_usd": float(row["size_usd"]),
                        "entry_time": row["timestamp"],
                        "entry_fr": float(row["funding_rate"]),
                        "fr_collected": 0.0,
                    }
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

    def check_opportunities(self, rates: list[dict], spot_set: set, margin_set: set):
        now = datetime.now(timezone.utc)
        size = self.capital / (self.max_positions * 1.2)

        for r in rates:
            sym = r["symbol"]
            fr = r["funding_rate"]
            last = r["last_price"]
            vol = r["volume_24h"]
            coin = sym.replace("_USDT", "")
            spot_symbol = coin + "USDT"
            has_spot = spot_symbol in spot_set
            can_margin = coin in margin_set
            hedge = classify_opportunity(fr, coin, has_spot, can_margin)

            # Open new position
            if (
                sym not in self.positions
                and len(self.positions) < self.max_positions
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
                    "size_usd": f"{size:.2f}",
                    "funding_rate": f"{fr:.6f}",
                    "pnl": "0",
                    "hedge_status": hedge,
                    "note": f"FR={fr*100:.3f}%/8h, vol=${vol:,.0f}",
                })
                self.positions[sym] = {
                    "entry_price": last,
                    "direction": direction,
                    "size_usd": size,
                    "entry_time": now.isoformat(),
                    "entry_fr": fr,
                    "fr_collected": 0.0,
                }
                print(f"  [PAPER] OPEN {direction} {sym} @ {last}, FR={fr*100:.3f}%")

            # Accrue FR on open position
            if sym in self.positions and abs(fr) > 0:
                pos = self.positions[sym]
                # MEXC FR settles every 8h; per-poll accrual = fr * size * (interval/8h)
                # We use abs(fr)*size per poll as in Bitget variant to keep comparability.
                pos["fr_collected"] += abs(fr) * pos["size_usd"]

            # Close when FR normalizes
            if sym in self.positions and abs(fr) < FR_THRESHOLD * 0.5:
                pos = self.positions[sym]
                price_change = (last - pos["entry_price"]) / pos["entry_price"] if pos["entry_price"] else 0
                if pos["direction"] == "SHORT":
                    price_change = -price_change
                price_pnl = price_change * pos["size_usd"]
                fr_pnl = pos["fr_collected"]
                # MEXC 2026: futures taker 0.02% (default); many pairs 0%.
                # Spot leg fee is 0% (all spot pairs fee-free in 2026).
                # We use 0.02% round-trip as worst-case (non-zero-fee pair, no MX discount).
                perp_fee = pos["size_usd"] * 0.0002 * 2
                total_pnl = price_pnl + fr_pnl - perp_fee

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
                    "note": f"price_pnl=${price_pnl:.2f}, fr=${fr_pnl:.4f}, fee=${perp_fee:.4f}",
                })
                print(f"  [PAPER] CLOSE {sym} PnL=${total_pnl:.4f}")
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
            print(f"    {sym}: {pos['direction']} @ {pos['entry_price']}, "
                  f"FR collected=${pos['fr_collected']:.4f}")


def report():
    """Show summary of all collected MEXC FR data."""
    print("=" * 60)
    print("MEXC FR Monitor Report")
    print("=" * 60)

    snapshots = sorted(CACHE_DIR.glob("mexc_fr_snapshots_*.csv"))
    if not snapshots:
        print("\n  No data collected yet.")
        print(f"  Expected path: {CACHE_DIR}/mexc_fr_snapshots_YYYY-MM-DD.csv")
        return

    total_rows = 0
    for path in snapshots:
        with open(path) as f:
            rows = sum(1 for _ in f) - 1  # minus header
        total_rows += rows
        print(f"  {path.name}: {rows} extreme FR observations")

    print(f"\n  Total observations: {total_rows}")

    # Analyze latest file
    latest = snapshots[-1]
    with open(latest) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if rows:
        symbols = {r["symbol"] for r in rows}
        frs = [abs(float(r["funding_rate"])) for r in rows]
        print(f"\n  Latest file ({latest.name}):")
        print(f"    Unique tokens with extreme FR: {len(symbols)}")
        print(f"    Max |FR|: {max(frs)*100:.3f}%/8h")
        print(f"    Avg |FR|: {sum(frs)/len(frs)*100:.3f}%/8h")
        print(f"    Tokens: {', '.join(sorted(symbols))}")

    # Paper trade summary
    print(f"\n  Paper Trades:")
    trader = PaperTrader()
    trader.summary()


def main():
    parser = argparse.ArgumentParser(description="MEXC FR Monitor")
    parser.add_argument("--interval", type=int, default=300, help="Poll interval in seconds")
    parser.add_argument("--report", action="store_true", help="Show report and exit")
    args = parser.parse_args()

    if args.report:
        report()
        return

    acquire_lock("mexc_fr_monitor")

    print("=" * 60)
    print("MEXC Funding Rate Monitor")
    print(f"  Threshold: |FR| > {FR_THRESHOLD*100:.1f}%/8h")
    print(f"  Poll interval: {args.interval}s")
    print(f"  Output: {CACHE_DIR}/mexc_fr_snapshots_*.csv")
    print(f"  Paper trades: {PAPER_TRADES_FILE}")
    print("=" * 60)

    print("\nLoading market info...")
    spot_set, margin_set = load_market_info()
    print(f"  Spot pairs: {len(spot_set)}, Margin coins: {len(margin_set)}")

    trader = PaperTrader()
    print(f"  Open paper positions: {len(trader.positions)}")

    poll_count = 0
    print("\nMonitoring... (Ctrl+C to stop)\n")

    try:
        while True:
            try:
                tickers = get_all_tickers()
                rates = parse_tickers(tickers)
                extreme_count = write_snapshot(rates, spot_set, margin_set)
                trader.check_opportunities(rates, spot_set, margin_set)

                poll_count += 1
                now = datetime.now(timezone.utc).strftime("%H:%M:%S")
                print(
                    f"  [{now}] #{poll_count}: extreme={extreme_count}, "
                    f"total_pairs={len(rates)}, paper_open={len(trader.positions)}"
                )

                # Refresh market info every 100 polls
                if poll_count % 100 == 0:
                    spot_set, margin_set = load_market_info()
                    print(f"  [refresh] spot={len(spot_set)}, margin_coins={len(margin_set)}")

            except Exception as e:
                print(f"  ERROR: {e}")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\nStopped after {poll_count} polls.")
        print("\nFinal summary:")
        trader.summary()


if __name__ == "__main__":
    main()
