#!/usr/bin/env python3
"""Daily health check using GMO Coin's real execution history.

Fetches the real (i.e. exchange-truth) trade history for a given JST date
via the bot-manager `/api/gmo/executions` proxy and prints/persists a
summary. Replaces the bot-internal `trades.csv` calculation, which is
known to drop fills and miscount SL slippage.

IMPORTANT — GMO API 24h limit:
    GMO Coin's `/v1/latestExecutions` only retains roughly the most recent
    ~1000 executions (~24 hours at this bot's trade rate). Querying older
    dates returns 0 fills. To preserve historical truth, run this script
    DAILY at JST 23:59 so each day's data is captured before it ages out.
    For dates older than the API window, fall back to scripts/verify_version.py
    which reads bot-internal trade.csv (less accurate but covers history).

Usage:
    # Today (auto-snapshot for daily cron)
    python3 scripts/daily_healthcheck.py --date $(date +%Y-%m-%d)

    # Single day
    python3 scripts/daily_healthcheck.py --date 2026-04-08

    # Backfill range (inclusive) — only works for last ~24h!
    python3 scripts/daily_healthcheck.py --start 2026-04-08 --end 2026-04-09

    # Force re-fetch (bypass cache)
    python3 scripts/daily_healthcheck.py --date 2026-04-08 --force

Output JSON is cached at `scripts/.cache/healthcheck-<DATE>.json`.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date as Date
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# bot-manager Basic Auth
DEFAULT_HOST = os.environ.get("BOT_MANAGER_HOST", "http://160.251.219.3")
DEFAULT_USER = os.environ.get("BOT_MANAGER_USER", "admin")
DEFAULT_PASS = os.environ.get("BOT_MANAGER_PASS")

CACHE_DIR = Path(__file__).parent / ".cache"


def fetch_executions(
    date_jst: str,
    host: str = DEFAULT_HOST,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASS,
    max_pages: int = 50,
) -> dict:
    """Call /api/gmo/executions on the bot-manager and return parsed JSON."""
    url = f"{host}/api/gmo/executions?date={date_jst}&max_pages={max_pages}"
    creds = base64.b64encode(f"{user}:{password}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {creds}"})

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(
            f"HTTP {e.code} from {url}: {body}"
        ) from e


def cache_path(date_jst: str) -> Path:
    return CACHE_DIR / f"healthcheck-{date_jst}.json"


def load_or_fetch(
    date_jst: str,
    force: bool = False,
    **kwargs,
) -> dict:
    """Return cached result if present, else fetch + cache."""
    path = cache_path(date_jst)
    if path.exists() and not force:
        with path.open() as f:
            return json.load(f)

    data = fetch_executions(date_jst, **kwargs)
    CACHE_DIR.mkdir(exist_ok=True)
    with path.open("w") as f:
        json.dump(data, f, indent=2)
    return data


def format_summary(data: dict) -> str:
    """Format a single-day summary as a one-line table row."""
    summary = data.get("summary") or {}
    return (
        f"{data['date']:>10} | "
        f"fills={summary.get('total_fills', 0):>4} "
        f"(open={summary.get('open_fills', 0):>3}, close={summary.get('close_fills', 0):>3}) | "
        f"realized={summary.get('realized_pnl', 0):>+8.0f} | "
        f"fee={summary.get('total_fee', 0):>+6.0f} | "
        f"net={summary.get('net_pnl', 0):>+8.0f} JPY | "
        f"pages={data.get('pages_fetched', '?'):>2} "
        f"complete={data.get('complete', '?')}"
    )


def daterange(start: str, end: str) -> list[str]:
    """Inclusive list of YYYY-MM-DD strings between start and end."""
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end, "%Y-%m-%d").date()
    if e < s:
        raise ValueError(f"end {end} is before start {start}")
    days: list[str] = []
    cur = s
    while cur <= e:
        days.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return days


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--date", help="Single JST date YYYY-MM-DD")
    g.add_argument("--start", help="Start of backfill range (with --end)")
    p.add_argument("--end", help="End of backfill range (inclusive)")
    p.add_argument("--force", action="store_true", help="Bypass cache")
    p.add_argument(
        "--max-pages", type=int, default=50, help="Pagination cap (default 50)"
    )
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--user", default=DEFAULT_USER)
    p.add_argument("--password", default=DEFAULT_PASS)
    args = p.parse_args()
    if args.start and not args.end:
        p.error("--start requires --end")
    return args


def main() -> int:
    if not DEFAULT_PASS:
        print("error: BOT_MANAGER_PASS env var required", file=sys.stderr)
        return 2

    args = parse_args()

    if args.date:
        dates = [args.date]
    else:
        dates = daterange(args.start, args.end)

    print(
        f"{'date':>10} | {'fills':<22} | {'realized':<10} | "
        f"{'fee':<8} | {'net':<14} | pagination"
    )
    print("-" * 110)

    results: list[dict] = []
    total_realized = 0.0
    total_fee = 0.0
    total_net = 0.0
    total_fills = 0

    for d in dates:
        try:
            data = load_or_fetch(
                d,
                force=args.force,
                host=args.host,
                user=args.user,
                password=args.password,
                max_pages=args.max_pages,
            )
        except RuntimeError as e:
            print(f"{d:>10} | ERROR: {e}")
            continue

        results.append(data)
        print(format_summary(data))
        if data.get("total", 0) == 0 and data.get("complete"):
            try:
                target = datetime.strptime(d, "%Y-%m-%d").date()
                age_days = (Date.today() - target).days
                if age_days >= 2:
                    print(
                        f"           ↳ WARN: 0 fills on {d} ({age_days}d ago). "
                        "GMO API only retains ~24h of history. "
                        "Use scripts/verify_version.py for older dates."
                    )
            except ValueError:
                pass
        s = data.get("summary") or {}
        total_realized += float(s.get("realized_pnl", 0) or 0)
        total_fee += float(s.get("total_fee", 0) or 0)
        total_net += float(s.get("net_pnl", 0) or 0)
        total_fills += int(s.get("total_fills", 0) or 0)

    if len(results) > 1:
        print("-" * 110)
        n = len(results)
        print(
            f"{'TOTAL':>10} | fills={total_fills:>4}"
            f" {' ' * 17} | "
            f"realized={total_realized:>+8.0f} | "
            f"fee={total_fee:>+6.0f} | "
            f"net={total_net:>+8.0f} JPY"
        )
        print(
            f"{'AVG/day':>10} | fills={total_fills/n:>5.1f}"
            f" {' ' * 16} | "
            f"realized={total_realized/n:>+8.1f} | "
            f"fee={total_fee/n:>+6.1f} | "
            f"net={total_net/n:>+8.1f} JPY"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
