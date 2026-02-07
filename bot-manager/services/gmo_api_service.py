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
