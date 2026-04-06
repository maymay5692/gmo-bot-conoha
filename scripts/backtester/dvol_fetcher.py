"""Deribit DVOL (BTC Implied Volatility Index) データ取得モジュール。

Deribit公開APIからBTC DVOLの履歴データを取得しローカルキャッシュする。
認証不要。データはOHLC形式（1時間解像度）。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import requests

_API_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_cache", "dvol")


def _date_to_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _ms_to_datetime(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def parse_dvol_response(raw: dict) -> list[dict]:
    data = raw.get("result", {}).get("data", [])
    return [
        {
            "timestamp": _ms_to_datetime(row[0]),
            "open": row[1],
            "high": row[2],
            "low": row[3],
            "close": row[4],
        }
        for row in data
    ]


def _load_cache(cache_key: str) -> list[dict] | None:
    cache_file = os.path.join(_CACHE_DIR, f"{cache_key}.json")
    if not os.path.exists(cache_file):
        return None
    with open(cache_file) as f:
        raw = json.load(f)
    return [
        {
            "timestamp": datetime.fromisoformat(r["timestamp"]),
            "open": r["open"],
            "high": r["high"],
            "low": r["low"],
            "close": r["close"],
        }
        for r in raw
    ]


def _save_cache(cache_key: str, records: list[dict]) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(_CACHE_DIR, f"{cache_key}.json")
    serializable = [
        {
            "timestamp": r["timestamp"].isoformat(),
            "open": r["open"],
            "high": r["high"],
            "low": r["low"],
            "close": r["close"],
        }
        for r in records
    ]
    with open(cache_file, "w") as f:
        json.dump(serializable, f)


def fetch_dvol(start_date: str, end_date: str, resolution: str = "3600") -> list[dict]:
    cache_key = f"{start_date}_{end_date}"
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    start_ms = _date_to_ms(start_date)
    end_ms = _date_to_ms(end_date) + 86400000

    params = {
        "currency": "BTC",
        "start_timestamp": start_ms,
        "end_timestamp": end_ms,
        "resolution": resolution,
    }

    response = requests.get(_API_URL, params=params, timeout=30)
    response.raise_for_status()
    raw = response.json()
    records = parse_dvol_response(raw)

    if records:
        _save_cache(cache_key, records)

    return records
