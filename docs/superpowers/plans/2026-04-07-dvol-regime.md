# DVOL Z-Scoreレジームフィルタ 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deribit APIからBTC DVOLデータを取得し、Z-Scoreベースのレジーム分類でトレンド相場の損失回避効果をバックテスト検証する

**Architecture:** `dvol_fetcher.py` でDeribit公開APIからDVOL履歴を取得・キャッシュ。`dvol_regime.py` でZ-Score算出・レジーム分類・P&L集計・what-if。`run_analysis.py` に `--analysis dvol_regime` モードを追加。

**Tech Stack:** Python, requests, 既存backtesterモジュール（data_loader, market_replay, dsr）

---

### Task 1: dvol_fetcher.py — DVOLデータ取得・キャッシュ

**Files:**
- Create: `scripts/backtester/dvol_fetcher.py`
- Create: `scripts/backtester/tests/test_dvol_fetcher.py`

- [ ] **Step 1: failing test を書く**

```python
# scripts/backtester/tests/test_dvol_fetcher.py
"""DVOLデータ取得モジュールのテスト。"""
import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from backtester.dvol_fetcher import parse_dvol_response, fetch_dvol


def test_parse_dvol_response():
    """APIレスポンスをパースしてdictのリストを返す。"""
    raw = {
        "result": {
            "data": [
                [1743465600000, 51.02, 51.03, 50.72, 50.77],
                [1743469200000, 50.77, 50.95, 50.60, 50.85],
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
    cache_file = os.path.join(cache_dir, "2026-04-01.json")
    cached_data = [
        {"timestamp": "2026-04-01T00:00:00+00:00", "open": 51.0, "high": 51.5, "low": 50.5, "close": 51.2},
    ]
    with open(cache_file, "w") as f:
        json.dump(cached_data, f)

    with patch("backtester.dvol_fetcher._CACHE_DIR", cache_dir):
        records = fetch_dvol("2026-04-01", "2026-04-01")
    assert len(records) == 1
    assert records[0]["close"] == 51.2
```

- [ ] **Step 2: テスト実行して失敗を確認**

Run: `cd scripts && python -m pytest backtester/tests/test_dvol_fetcher.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: dvol_fetcher.py を実装**

```python
# scripts/backtester/dvol_fetcher.py
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
    """YYYY-MM-DD → milliseconds since epoch (UTC 00:00)。"""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _ms_to_datetime(ms: int) -> datetime:
    """Milliseconds since epoch → UTC datetime。"""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def parse_dvol_response(raw: dict) -> list[dict]:
    """Deribit APIレスポンスをパースしてレコードリストを返す。

    Args:
        raw: APIのJSONレスポンス

    Returns:
        [{"timestamp": datetime, "open": float, "high": float, "low": float, "close": float}, ...]
    """
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


def _load_cache(date_str: str) -> list[dict] | None:
    """キャッシュファイルがあれば読み込む。"""
    cache_file = os.path.join(_CACHE_DIR, f"{date_str}.json")
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


def _save_cache(date_str: str, records: list[dict]) -> None:
    """キャッシュに保存。"""
    os.makedirs(_CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(_CACHE_DIR, f"{date_str}.json")
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


def fetch_dvol(
    start_date: str,
    end_date: str,
    resolution: str = "3600",
) -> list[dict]:
    """Deribit APIからBTC DVOLデータを取得。キャッシュがあればそちらを使用。

    Args:
        start_date: 開始日 (YYYY-MM-DD)
        end_date: 終了日 (YYYY-MM-DD)
        resolution: 解像度（秒）。"3600"=1時間

    Returns:
        [{"timestamp": datetime, "open": float, "high": float, "low": float, "close": float}, ...]
    """
    # 日単位でキャッシュを確認
    cached = _load_cache(f"{start_date}_{end_date}")
    if cached is not None:
        return cached

    start_ms = _date_to_ms(start_date)
    end_ms = _date_to_ms(end_date) + 86400000  # end_date の翌日00:00まで

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
        _save_cache(f"{start_date}_{end_date}", records)

    return records
```

- [ ] **Step 4: テスト実行してパスを確認**

Run: `cd scripts && python -m pytest backtester/tests/test_dvol_fetcher.py -v`
Expected: 3 passed

- [ ] **Step 5: コミット**

```bash
git add scripts/backtester/dvol_fetcher.py scripts/backtester/tests/test_dvol_fetcher.py
git commit -m "feat: add DVOL data fetcher with Deribit API and cache"
```

---

### Task 2: dvol_regime.py — Z-Score算出・レジーム分類

**Files:**
- Create: `scripts/backtester/dvol_regime.py`
- Create: `scripts/backtester/tests/test_dvol_regime.py`

- [ ] **Step 1: failing test を書く**

```python
# scripts/backtester/tests/test_dvol_regime.py
"""DVOLレジーム分析モジュールのテスト。"""
from datetime import datetime, timedelta, timezone

from backtester.dvol_regime import calc_dvol_zscore, classify_dvol_regime


def _make_dvol_data(n_hours: int, base_dvol: float = 50.0, spike_at: int = -1, spike_value: float = 80.0) -> list[dict]:
    """テスト用DVOLデータ生成。"""
    base = datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)
    records = []
    for i in range(n_hours):
        dvol = spike_value if i == spike_at else base_dvol + (i % 5) * 0.5
        records.append({
            "timestamp": base + timedelta(hours=i),
            "open": dvol,
            "high": dvol + 0.5,
            "low": dvol - 0.5,
            "close": dvol,
        })
    return records


def test_calc_dvol_zscore_basic():
    """Z-Scoreが計算される。"""
    data = _make_dvol_data(48)
    result = calc_dvol_zscore(data, lookback_hours=24)
    assert len(result) > 0
    assert "z_score" in result[0]
    assert "dvol" in result[0]
    assert "timestamp" in result[0]


def test_calc_dvol_zscore_spike_detected():
    """スパイクが高Z-Scoreとして検出される。"""
    data = _make_dvol_data(48, base_dvol=50.0, spike_at=47, spike_value=80.0)
    result = calc_dvol_zscore(data, lookback_hours=24)
    last = result[-1]
    assert last["z_score"] > 2.0, f"Spike should have Z>2, got {last['z_score']}"


def test_classify_dvol_regime_labels():
    """Z-Scoreからnormal/highに分類される。"""
    data = _make_dvol_data(48, base_dvol=50.0, spike_at=47, spike_value=80.0)
    zscore_data = calc_dvol_zscore(data, lookback_hours=24)
    result = classify_dvol_regime(zscore_data)
    labels = result["labels"]
    assert len(labels) > 0

    # スパイク時刻はhigh
    spike_ts = data[47]["timestamp"]
    assert labels.get(spike_ts) == "high", f"Spike should be 'high', got {labels.get(spike_ts)}"

    # 通常時刻はnormal
    normal_count = sum(1 for v in labels.values() if v == "normal")
    assert normal_count > 0


def test_classify_dvol_regime_stats():
    """statsにmeanとstdが含まれる。"""
    data = _make_dvol_data(48)
    zscore_data = calc_dvol_zscore(data, lookback_hours=24)
    result = classify_dvol_regime(zscore_data)
    assert "mean" in result["stats"]
    assert "std" in result["stats"]
```

- [ ] **Step 2: テスト実行して失敗を確認**

Run: `cd scripts && python -m pytest backtester/tests/test_dvol_regime.py -v`
Expected: FAIL

- [ ] **Step 3: dvol_regime.py を実装**

```python
# scripts/backtester/dvol_regime.py
"""DVOL Z-Scoreレジーム分析モジュール。

Deribit DVOLのZ-Scoreで市場ストレスレベルを判定し、
レジーム別P&L集計とフィルタwhat-ifを提供する。
"""
from __future__ import annotations

import bisect
import math
from datetime import datetime

from .data_loader import Trip
from .market_replay import MarketState, get_market_state_at


def calc_dvol_zscore(
    dvol_data: list[dict],
    lookback_hours: int = 720,
) -> list[dict]:
    """DVOL close値からZ-Scoreを算出。

    Args:
        dvol_data: fetch_dvol()の結果
        lookback_hours: 移動平均・標準偏差のウィンドウ（時間）

    Returns:
        [{"timestamp": datetime, "dvol": float, "z_score": float}, ...]
    """
    if not dvol_data:
        return []

    closes = [d["close"] for d in dvol_data]
    timestamps = [d["timestamp"] for d in dvol_data]
    result = []

    for i in range(len(closes)):
        # lookback window
        start_idx = max(0, i - lookback_hours + 1)
        window = closes[start_idx:i + 1]

        if len(window) < 2:
            result.append({
                "timestamp": timestamps[i],
                "dvol": closes[i],
                "z_score": 0.0,
            })
            continue

        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / (len(window) - 1)
        std = math.sqrt(variance) if variance > 0 else 0.0

        z_score = (closes[i] - mean) / std if std > 0 else 0.0

        result.append({
            "timestamp": timestamps[i],
            "dvol": closes[i],
            "z_score": z_score,
        })

    return result


def classify_dvol_regime(
    zscore_data: list[dict],
    z_threshold: float = 2.0,
) -> dict:
    """Z-Scoreでレジーム分類。

    Args:
        zscore_data: calc_dvol_zscore()の結果
        z_threshold: high/lowの閾値

    Returns:
        {
            "labels": {datetime: "normal" | "high" | "low"},
            "stats": {"mean": float, "std": float},
        }
    """
    if not zscore_data:
        return {"labels": {}, "stats": {"mean": 0.0, "std": 0.0}}

    labels: dict[datetime, str] = {}
    dvol_values = [d["dvol"] for d in zscore_data]

    for d in zscore_data:
        if d["z_score"] >= z_threshold:
            labels[d["timestamp"]] = "high"
        elif d["z_score"] <= -z_threshold:
            labels[d["timestamp"]] = "low"
        else:
            labels[d["timestamp"]] = "normal"

    mean = sum(dvol_values) / len(dvol_values)
    variance = sum((x - mean) ** 2 for x in dvol_values) / (len(dvol_values) - 1) if len(dvol_values) > 1 else 0.0
    std = math.sqrt(variance) if variance > 0 else 0.0

    return {
        "labels": labels,
        "stats": {"mean": mean, "std": std},
    }


def _get_dvol_regime_at(
    timestamp: datetime,
    zscore_data: list[dict],
    regime_labels: dict[datetime, str],
) -> str:
    """指定時刻のDVOLレジームを返す。bisectで最近傍を検索。"""
    if not zscore_data:
        return "normal"

    ts_list = [d["timestamp"] for d in zscore_data]
    idx = bisect.bisect_right(ts_list, timestamp) - 1
    if idx < 0:
        return "normal"

    matched_ts = ts_list[idx]
    return regime_labels.get(matched_ts, "normal")


def analyze_by_dvol_regime(
    trips: list[Trip],
    dvol_regime_result: dict,
    zscore_data: list[dict],
) -> list[dict]:
    """DVOLレジーム別のP&L集計。

    Args:
        trips: build_trips()の結果
        dvol_regime_result: classify_dvol_regime()の結果
        zscore_data: calc_dvol_zscore()の結果

    Returns:
        レジーム別の集計リスト
    """
    matched = [t for t in trips if t.close_fill is not None]
    if not matched:
        return []

    labels = dvol_regime_result["labels"]
    groups: dict[str, list[Trip]] = {"normal": [], "high": [], "low": []}

    for t in matched:
        regime = _get_dvol_regime_at(t.open_fill.timestamp, zscore_data, labels)
        if regime in groups:
            groups[regime].append(t)

    rows = []
    for regime in ["normal", "high", "low"]:
        items = groups[regime]
        if not items:
            rows.append({
                "regime": regime, "count": 0, "pnl_sum": 0.0,
                "pnl_mean": 0.0, "win_rate": 0.0,
            })
            continue

        pnl_list = [t.pnl_jpy for t in items]
        wins = sum(1 for p in pnl_list if p > 0)
        rows.append({
            "regime": regime,
            "count": len(items),
            "pnl_sum": sum(pnl_list),
            "pnl_mean": sum(pnl_list) / len(pnl_list),
            "win_rate": wins / len(items),
        })

    return rows


def calc_dvol_filter_impact(
    trips: list[Trip],
    dvol_regime_result: dict,
    zscore_data: list[dict],
    exclude_regimes: list[str],
) -> dict:
    """特定DVOLレジームを除外した場合のP&L影響。"""
    matched = [t for t in trips if t.close_fill is not None]
    labels = dvol_regime_result["labels"]
    exclude_set = set(exclude_regimes)

    included: list[Trip] = []
    excluded: list[Trip] = []

    for t in matched:
        regime = _get_dvol_regime_at(t.open_fill.timestamp, zscore_data, labels)
        if regime in exclude_set:
            excluded.append(t)
        else:
            included.append(t)

    def _stats(ts: list[Trip]) -> dict:
        if not ts:
            return {"pnl_sum": 0.0, "pnl_mean": 0.0, "count": 0}
        pnl_list = [t.pnl_jpy for t in ts]
        return {
            "pnl_sum": sum(pnl_list),
            "pnl_mean": sum(pnl_list) / len(pnl_list),
            "count": len(ts),
        }

    return {
        "exclude_spec": "+".join(exclude_regimes),
        "included": _stats(included),
        "excluded": _stats(excluded),
        "total": {
            "pnl_sum": sum(t.pnl_jpy for t in matched),
            "count": len(matched),
        },
    }
```

- [ ] **Step 4: テスト実行してパスを確認**

Run: `cd scripts && python -m pytest backtester/tests/test_dvol_regime.py -v`
Expected: 4 passed

- [ ] **Step 5: コミット**

```bash
git add scripts/backtester/dvol_regime.py scripts/backtester/tests/test_dvol_regime.py
git commit -m "feat: add DVOL Z-Score regime classification and analysis"
```

---

### Task 3: run_analysis.py にdvol_regime分析モードを統合

**Files:**
- Modify: `scripts/backtester/run_analysis.py`

- [ ] **Step 1: import追加**

既存importブロックの末尾に追加:

```python
from backtester.dvol_fetcher import fetch_dvol  # noqa: E402
from backtester.dvol_regime import (  # noqa: E402
    analyze_by_dvol_regime,
    calc_dvol_filter_impact,
    calc_dvol_zscore,
    classify_dvol_regime,
)
```

- [ ] **Step 2: analysis_dvol_regime 関数を追加**

`analysis_min_hold` の後に追加:

```python
def analysis_dvol_regime(trades, metrics, trips, timeline, date: str):
    """DVOL Z-Scoreレジーム分析。"""
    print("\n=== DVOL Z-Scoreレジーム分析 ===")

    # DVOL取得（前30日 + 当日）
    from datetime import datetime, timedelta
    target = datetime.strptime(date, "%Y-%m-%d")
    start = (target - timedelta(days=30)).strftime("%Y-%m-%d")

    try:
        dvol_data = fetch_dvol(start, date)
    except Exception as e:
        print(f"  DVOL取得失敗: {e}")
        return

    if not dvol_data:
        print("  DVOLデータなし")
        return

    zscore_data = calc_dvol_zscore(dvol_data, lookback_hours=720)
    regime_result = classify_dvol_regime(zscore_data)

    stats = regime_result["stats"]
    print(f"  DVOL: mean={stats['mean']:.1f}  std={stats['std']:.1f}")

    # 当日のZ-Score範囲
    day_zscores = [
        d for d in zscore_data
        if d["timestamp"].strftime("%Y-%m-%d") == date
    ]
    if day_zscores:
        z_min = min(d["z_score"] for d in day_zscores)
        z_max = max(d["z_score"] for d in day_zscores)
        z_last = day_zscores[-1]["z_score"]
        print(f"  当日Z-Score: min={z_min:.2f}  max={z_max:.2f}  last={z_last:.2f}")

    # レジーム別P&L
    rows = analyze_by_dvol_regime(trips, regime_result, zscore_data)
    if not rows:
        print("  トリップデータなし")
        return

    print()
    headers = ["レジーム", "件数", "P&L合計", "P&L/trip", "win率"]
    widths = [10, 6, 10, 9, 8]
    table_rows = []
    for r in rows:
        if r["count"] == 0:
            continue
        table_rows.append([
            r["regime"],
            str(r["count"]),
            f"{r['pnl_sum']:+.2f}",
            f"{r['pnl_mean']:+.3f}",
            f"{r['win_rate']:.1%}",
        ])
    _print_table(headers, table_rows, widths)

    # フィルタwhat-if
    print("\n=== フィルタwhat-if ===")
    filter_patterns = [["high"], ["high", "low"]]
    total_count = sum(r["count"] for r in rows)
    total_pnl = sum(r["pnl_sum"] for r in rows)
    overall_mean = total_pnl / total_count if total_count > 0 else 0.0

    wh_headers = ["除外パターン", "件数", "P&L合計", "P&L/trip", "改善"]
    wh_widths = [18, 6, 10, 9, 12]
    wh_rows = []
    for excl in filter_patterns:
        result = calc_dvol_filter_impact(trips, regime_result, zscore_data, exclude_regimes=excl)
        inc = result["included"]
        if inc["count"] > 0:
            improvement = inc["pnl_mean"] - overall_mean
            wh_rows.append([
                "+".join(excl) + "除外",
                str(inc["count"]),
                f"{inc['pnl_sum']:+.2f}",
                f"{inc['pnl_mean']:+.3f}",
                f"{improvement:+.3f}/trip",
            ])
    _print_table(wh_headers, wh_rows, wh_widths)

    # DSR
    matched = [t for t in trips if t.close_fill is not None]
    if matched:
        labels = regime_result["labels"]
        best_sr = float("-inf")
        best_pnl_list: list[float] = []
        from backtester.dvol_regime import _get_dvol_regime_at
        for excl in filter_patterns:
            excl_set = set(excl)
            inc_trips = [
                t for t in matched
                if _get_dvol_regime_at(t.open_fill.timestamp, zscore_data, labels) not in excl_set
            ]
            if len(inc_trips) >= 2:
                pnl_list = [t.pnl_jpy for t in inc_trips]
                sr = calc_sharpe_ratio(pnl_list)
                if sr > best_sr:
                    best_sr = sr
                    best_pnl_list = pnl_list
        if best_pnl_list:
            dsr_result = evaluate_dsr(best_pnl_list, N=len(filter_patterns))
            dsr_line = format_dsr_line(
                dsr=dsr_result["dsr"],
                N=dsr_result["N"],
                T=dsr_result["T"],
                sr_best=dsr_result["sr_best"],
                significant=dsr_result["significant"],
            )
            print(f"\n  {dsr_line}")
```

- [ ] **Step 3: main() を更新**

argparse choicesに `"dvol_regime"` を追加。

analysis実行部分の末尾に追加:

```python
    if args.analysis in ("all", "dvol_regime"):
        analysis_dvol_regime(trades, metrics, trips, timeline, date=args.date)
```

注意: `analysis_dvol_regime` は `date` 引数が必要（DVOL取得に使用）。他のanalysis関数と異なるシグネチャ。

- [ ] **Step 4: 動作確認**

Run: `cd scripts && python backtester/run_analysis.py --date 2026-04-02 --analysis dvol_regime`
Expected: DVOLレジーム分析結果が表示される

- [ ] **Step 5: コミット**

```bash
git add scripts/backtester/run_analysis.py
git commit -m "feat: integrate DVOL regime analysis into run_analysis CLI"
```

---

### Task 4: __init__.py 更新と全テスト

**Files:**
- Modify: `scripts/backtester/__init__.py`

- [ ] **Step 1: __init__.py にモジュール説明を追加**

`min_hold_sim` の行の後に追加:

```
  dvol_fetcher   - Deribit DVOL データ取得・キャッシュ
  dvol_regime    - DVOL Z-Scoreレジーム分析
```

- [ ] **Step 2: 全テスト実行**

Run: `cd scripts && python -m pytest backtester/tests/ -v`
Expected: all passed

- [ ] **Step 3: コミット**

```bash
git add scripts/backtester/__init__.py
git commit -m "docs: add dvol modules to backtester __init__ docstring"
```
