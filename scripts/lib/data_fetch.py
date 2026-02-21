"""Common data fetch/cache utilities for bot analysis scripts."""
import json
import os
from typing import Optional

import requests

VPS_URL = os.environ.get("VPS_URL", "http://160.251.219.3")
AUTH = (
    os.environ.get("VPS_USER", "admin"),
    os.environ.get("VPS_PASS", ""),
)
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache")


def fetch_csv(csv_type: str, date: str) -> Optional[list[dict]]:
    """Fetch CSV data from VPS Bot Manager API."""
    url = f"{VPS_URL}/api/{csv_type}/csv?date={date}"
    try:
        resp = requests.get(url, auth=AUTH, timeout=30)
        if resp.status_code == 404:
            print(f"  No {csv_type} data for {date}")
            return None
        resp.raise_for_status()
        data = resp.json()
        return data.get("rows", [])
    except requests.RequestException as e:
        print(f"  Failed to fetch {csv_type}: {e}")
        return None


def fetch_dates(csv_type: str = "metrics") -> list[str]:
    """List available dates from VPS."""
    url = f"{VPS_URL}/api/metrics/dates?type={csv_type}"
    try:
        resp = requests.get(url, auth=AUTH, timeout=10)
        resp.raise_for_status()
        return resp.json().get("dates", [])
    except requests.RequestException as e:
        print(f"Failed to fetch dates: {e}")
        return []


def cache_data(csv_type: str, date: str, rows: list[dict]) -> None:
    """Cache fetched data locally."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{csv_type}-{date}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)


def load_cached(csv_type: str, date: str) -> Optional[list[dict]]:
    """Load cached data if available."""
    path = os.path.join(CACHE_DIR, f"{csv_type}-{date}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_data(csv_type: str, date: str, force_fetch: bool = False) -> Optional[list[dict]]:
    """Get data from cache or VPS."""
    if not force_fetch:
        cached = load_cached(csv_type, date)
        if cached is not None:
            print(f"  Using cached {csv_type} data ({len(cached)} rows)")
            return cached

    print(f"  Fetching {csv_type} from VPS...")
    rows = fetch_csv(csv_type, date)
    if rows is not None:
        cache_data(csv_type, date, rows)
        print(f"  Fetched and cached {len(rows)} rows")
    return rows
