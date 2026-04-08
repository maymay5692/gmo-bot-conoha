"""GMO Coin API service for fetching account data."""
import hashlib
import hmac
import os
import time

import requests

BASE_URL = "https://api.coin.z.com/private"


class GmoApiError(Exception):
    """GMO API error with status code and messages."""

    def __init__(self, status: int, messages: list):
        self.status = status
        self.messages = messages
        msg_str = "; ".join(
            f"{m.get('message_code', '?')}: {m.get('message_string', '?')}"
            for m in messages
        )
        super().__init__(f"GMO API error (status={status}): {msg_str}")


def _get_credentials() -> tuple[str, str]:
    """Get API key and secret from environment variables."""
    api_key = os.environ.get("GMO_API_KEY", "")
    api_secret = os.environ.get("GMO_API_SECRET", "")
    return api_key, api_secret


def _create_sign(method: str, path: str, body: str, timestamp: str, secret: str) -> str:
    """Create HMAC-SHA256 signature for GMO API authentication."""
    text = timestamp + method.upper() + path + body
    sign = hmac.new(
        secret.encode("utf-8"),
        text.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return sign


def _make_headers(method: str, path: str, body: str = "") -> dict:
    """Build authenticated headers for GMO API request."""
    api_key, api_secret = _get_credentials()
    if not api_key or not api_secret:
        raise GmoApiError(0, [{"message_code": "AUTH", "message_string": "API credentials not configured"}])

    timestamp = str(int(time.time() * 1000))
    sign = _create_sign(method, path, body, timestamp, api_secret)

    return {
        "API-KEY": api_key,
        "API-TIMESTAMP": timestamp,
        "API-SIGN": sign,
    }


def _handle_response(resp: requests.Response) -> dict:
    """Parse GMO API response with two-stage validation."""
    resp.raise_for_status()
    data = resp.json()

    status = data.get("status", -1)
    if status != 0:
        messages = data.get("messages", [])
        raise GmoApiError(status, messages)

    return data


def get_account_margin() -> dict:
    """Fetch account margin info from GMO Coin API.

    Returns dict with keys: actualProfitLoss, availableAmount,
    margin, marginCallStatus, marginRatio, profitLoss, transferableAmount.
    """
    path = "/v1/account/margin"
    headers = _make_headers("GET", path)
    resp = requests.get(BASE_URL + path, headers=headers, timeout=10)
    data = _handle_response(resp)
    return data.get("data", {})


def get_latest_executions(
    symbol: str = "BTC_JPY", page: int = 1, count: int = 100
) -> dict:
    """Fetch the latest executions from GMO Coin private API.

    Returns the raw `data` object from the response, which contains:
      - pagination: {currentPage, count}
      - list: [ {executionId, orderId, symbol, side, settleType, size,
                 price, lossGain, fee, timestamp}, ... ]

    The list is ordered most-recent-first.
    """
    if count < 1 or count > 100:
        raise ValueError("count must be between 1 and 100")
    if page < 1:
        raise ValueError("page must be >= 1")

    path = "/v1/latestExecutions"
    query = f"?symbol={symbol}&page={page}&count={count}"
    headers = _make_headers("GET", path)
    resp = requests.get(BASE_URL + path + query, headers=headers, timeout=15)
    data = _handle_response(resp)
    return data.get("data", {}) or {}


def fetch_executions_for_date(
    date_jst: str,
    symbol: str = "BTC_JPY",
    max_pages: int = 50,
) -> dict:
    """Paginate GMO latestExecutions to collect every fill on a given JST date.

    Args:
        date_jst: 'YYYY-MM-DD' in Japan Standard Time (JST, UTC+9).
        symbol: trading symbol (default BTC_JPY).
        max_pages: safety cap to prevent runaway pagination.

    Returns:
        {
          "date": date_jst,
          "executions": [...],          # chronological (oldest first)
          "total": int,
          "pages_fetched": int,
          "complete": bool,             # False if we hit max_pages before
                                        # reaching executions older than date
        }

    Notes:
        - latestExecutions returns newest-first across pages. We walk pages
          until we encounter an execution strictly older than 00:00 JST
          on `date_jst`, then stop.
        - Timestamps from GMO are ISO 8601 in UTC. We compare against the
          UTC equivalent of JST midnight.
    """
    from datetime import datetime, timedelta, timezone

    jst = timezone(timedelta(hours=9))
    start_of_day_jst = datetime.strptime(date_jst, "%Y-%m-%d").replace(tzinfo=jst)
    end_of_day_jst = start_of_day_jst + timedelta(days=1)
    start_utc = start_of_day_jst.astimezone(timezone.utc)
    end_utc = end_of_day_jst.astimezone(timezone.utc)

    collected: list = []
    complete = False
    pages_fetched = 0

    for page in range(1, max_pages + 1):
        data = get_latest_executions(symbol=symbol, page=page, count=100)
        pages_fetched += 1
        rows = data.get("list") or []
        if not rows:
            complete = True
            break

        saw_older = False
        for row in rows:
            ts_raw = row.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts >= end_utc:
                continue  # newer than target date, skip
            if ts < start_utc:
                saw_older = True
                continue  # older than target date, skip
            collected.append(row)

        if saw_older:
            complete = True
            break

    collected.sort(key=lambda r: r.get("timestamp", ""))

    return {
        "date": date_jst,
        "executions": collected,
        "total": len(collected),
        "pages_fetched": pages_fetched,
        "complete": complete,
    }


def summarize_executions(executions: list) -> dict:
    """Compute aggregate stats from a list of GMO execution dicts.

    Returns:
        {
          "total_fills": int,
          "open_fills": int,
          "close_fills": int,
          "realized_pnl": float,   # sum of lossGain on CLOSE fills
          "total_fee": float,       # sum of fee across all fills
          "net_pnl": float,         # realized_pnl - total_fee
        }
    """
    open_fills = 0
    close_fills = 0
    realized_pnl = 0.0
    total_fee = 0.0

    for row in executions:
        settle = (row.get("settleType") or "").upper()
        if settle == "OPEN":
            open_fills += 1
        elif settle == "CLOSE":
            close_fills += 1
            try:
                realized_pnl += float(row.get("lossGain") or 0)
            except (TypeError, ValueError):
                pass
        try:
            total_fee += float(row.get("fee") or 0)
        except (TypeError, ValueError):
            pass

    return {
        "total_fills": len(executions),
        "open_fills": open_fills,
        "close_fills": close_fills,
        "realized_pnl": realized_pnl,
        "total_fee": total_fee,
        "net_pnl": realized_pnl - total_fee,
    }
