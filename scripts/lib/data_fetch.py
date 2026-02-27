"""Common data fetch/cache utilities for bot analysis scripts."""
import json
import os
from typing import Optional

import requests

VPS_DIRECT = "http://160.251.219.3"
AUTH = (
    os.environ.get("VPS_USER", "admin"),
    os.environ.get("VPS_PASS", ""),
)
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache")
_TUNNEL_URL_CACHE = os.path.join(CACHE_DIR, ".tunnel_url")


def _read_cached_tunnel_url() -> Optional[str]:
    """Read cached tunnel URL from disk."""
    if os.path.isfile(_TUNNEL_URL_CACHE):
        with open(_TUNNEL_URL_CACHE, "r") as f:
            return f.read().strip() or None
    return None


def _write_cached_tunnel_url(url: str) -> None:
    """Write tunnel URL to disk cache."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_TUNNEL_URL_CACHE, "w") as f:
        f.write(url)


def _resolve_tunnel_url(base_url: str) -> Optional[str]:
    """Fetch tunnel URL from bot-manager's /api/tunnel-url endpoint."""
    try:
        resp = requests.get(
            f"{base_url}/api/tunnel-url", auth=AUTH, timeout=5,
        )
        if resp.ok:
            data = resp.json()
            return data.get("tunnel_url")
    except requests.RequestException:
        pass
    return None


def resolve_vps_url() -> str:
    """Resolve the VPS URL, trying direct IP first then tunnel.

    Priority:
    1. VPS_URL env var (explicit override)
    2. Direct IP (fastest, works if ISP routing is OK)
    3. Cached tunnel URL
    4. Discover tunnel URL via direct IP -> /api/tunnel-url
    """
    explicit = os.environ.get("VPS_URL")
    if explicit:
        return explicit

    # Try direct IP
    try:
        resp = requests.get(
            f"{VPS_DIRECT}/api/status", auth=AUTH, timeout=3,
        )
        if resp.ok:
            # Direct IP works - also refresh tunnel URL cache
            tunnel = _resolve_tunnel_url(VPS_DIRECT)
            if tunnel:
                _write_cached_tunnel_url(tunnel)
            return VPS_DIRECT
    except requests.RequestException:
        pass

    # Direct IP failed - try cached tunnel URL
    cached = _read_cached_tunnel_url()
    if cached:
        try:
            resp = requests.get(
                f"{cached}/api/status", auth=AUTH, timeout=5,
            )
            if resp.ok:
                return cached
        except requests.RequestException:
            pass

    # All failed
    print("WARNING: Cannot reach VPS (direct IP or cached tunnel URL)")
    print("  Set VPS_URL=https://xxx.trycloudflare.com manually")
    return VPS_DIRECT  # fallback, will fail on fetch


VPS_URL = resolve_vps_url()


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
