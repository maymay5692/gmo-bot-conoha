"""DVOLデータ取得モジュールのテスト。"""
import json
import os
from datetime import datetime, timezone
from unittest.mock import patch

from backtester.dvol_fetcher import parse_dvol_response, fetch_dvol


def test_parse_dvol_response():
    """APIレスポンスをパースしてdictのリストを返す。"""
    raw = {
        "result": {
            "data": [
                [1775001600000, 51.02, 51.03, 50.72, 50.77],
                [1775005200000, 50.77, 50.95, 50.60, 50.85],
            ],
            "continuation": None,
        }
    }
    records = parse_dvol_response(raw)
    assert len(records) == 2
    assert records[0]["timestamp"] == datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)
    assert records[0]["open"] == 51.02
    assert records[0]["close"] == 50.77
    assert records[1]["high"] == 50.95
    assert records[1]["low"] == 50.60


def test_parse_dvol_response_empty():
    """空レスポンス → 空リスト。"""
    raw = {"result": {"data": [], "continuation": None}}
    records = parse_dvol_response(raw)
    assert records == []


def test_fetch_dvol_uses_cache(tmp_path):
    """キャッシュが存在すればAPIを呼ばない。"""
    cache_dir = str(tmp_path / "dvol")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, "2026-04-01_2026-04-01.json")
    cached_data = [
        {"timestamp": "2026-04-01T00:00:00+00:00", "open": 51.0, "high": 51.5, "low": 50.5, "close": 51.2},
    ]
    with open(cache_file, "w") as f:
        json.dump(cached_data, f)

    with patch("backtester.dvol_fetcher._CACHE_DIR", cache_dir):
        records = fetch_dvol("2026-04-01", "2026-04-01")
    assert len(records) == 1
    assert records[0]["close"] == 51.2
