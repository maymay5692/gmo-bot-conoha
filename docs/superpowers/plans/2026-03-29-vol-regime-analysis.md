# ボラティリティレジーム分析 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** バックテスターにボラティリティレジーム分析を追加し、高ボラ時の取引除外によるP&L改善をwhat-if評価できるようにする

**Architecture:** `scripts/backtester/vol_regime.py` にレジーム分類とP&L集計ロジックを実装し、`run_analysis.py` から `--analysis vol_regime` で呼び出す。既存の `market_replay.get_market_state_at` でtripの時刻のvolatilityを取得し、パーセンタイルで3レジームに分類する。DSRで統計的有意性も判定。

**Tech Stack:** Python, 既存 backtester モジュール（market_replay, data_loader, dsr）

---

### Task 1: vol_regime.py — レジーム分類関数

**Files:**
- Create: `scripts/backtester/vol_regime.py`
- Modify: `scripts/backtester/tests/test_dsr.py` → Create: `scripts/backtester/tests/test_vol_regime.py`

- [ ] **Step 1: failing test を書く — classify_vol_regime**

```python
# scripts/backtester/tests/test_vol_regime.py
"""ボラティリティレジーム分析モジュールのテスト。"""
from datetime import datetime, timezone

from backtester.market_replay import MarketState
from backtester.vol_regime import classify_vol_regime


def _make_market_state(ts_hour: int, volatility: float) -> MarketState:
    """テスト用MarketState生成。"""
    return MarketState(
        timestamp=datetime(2026, 2, 27, ts_hour, 0, 0, tzinfo=timezone.utc),
        mid_price=13000000.0,
        spread=500.0,
        sigma_1s=0.5,
        volatility=volatility,
        t_optimal_ms=3000,
        long_size=0.0,
        short_size=0.0,
        best_ask=13000250.0,
        best_bid=12999750.0,
        buy_spread_pct=0.00022,
        sell_spread_pct=0.00022,
    )


def test_classify_returns_boundaries_and_labels():
    """classify_vol_regimeがboundariesとlabelsを返す。"""
    timeline = [
        _make_market_state(0, 100.0),
        _make_market_state(1, 200.0),
        _make_market_state(2, 300.0),
        _make_market_state(3, 400.0),
        _make_market_state(4, 500.0),
        _make_market_state(5, 600.0),
        _make_market_state(6, 700.0),
        _make_market_state(7, 800.0),
    ]
    result = classify_vol_regime(timeline)
    assert "boundaries" in result
    assert "labels" in result
    assert "p25" in result["boundaries"]
    assert "p75" in result["boundaries"]
    assert len(result["labels"]) == 8


def test_classify_labels_correct():
    """パーセンタイルで正しくlow/mid/highに分類される。"""
    timeline = [
        _make_market_state(0, 100.0),  # low
        _make_market_state(1, 200.0),  # low
        _make_market_state(2, 400.0),  # mid
        _make_market_state(3, 500.0),  # mid
        _make_market_state(4, 600.0),  # mid
        _make_market_state(5, 700.0),  # mid
        _make_market_state(6, 900.0),  # high
        _make_market_state(7, 1000.0), # high
    ]
    result = classify_vol_regime(timeline)
    labels = result["labels"]

    # P25 = 250, P75 = 850 (近似)
    # 100, 200 < P25 → low
    # 900, 1000 >= P75 → high
    # 残り → mid
    ts0 = timeline[0].timestamp
    ts7 = timeline[7].timestamp
    assert labels[ts0] == "low"
    assert labels[ts7] == "high"


def test_classify_empty_timeline():
    """空タイムライン → 空結果。"""
    result = classify_vol_regime([])
    assert result["boundaries"]["p25"] == 0.0
    assert result["boundaries"]["p75"] == 0.0
    assert len(result["labels"]) == 0
```

- [ ] **Step 2: テスト実行して失敗を確認**

Run: `cd scripts && python -m pytest backtester/tests/test_vol_regime.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: classify_vol_regime を実装**

```python
# scripts/backtester/vol_regime.py
"""ボラティリティレジーム分析モジュール。

EWMA volatilityのパーセンタイルで低・中・高の3レジームに分類し、
レジーム別P&L集計とフィルタwhat-ifシミュレーションを提供する。
"""
from __future__ import annotations

from datetime import datetime

from .market_replay import MarketState, get_market_state_at


def _percentile(sorted_values: list[float], pct: float) -> float:
    """ソート済みリストのパーセンタイル値を返す（線形補間）。"""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    k = (n - 1) * pct / 100.0
    f = int(k)
    c = f + 1
    if c >= n:
        return sorted_values[-1]
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])


def classify_vol_regime(
    timeline: list[MarketState],
    percentiles: tuple[float, float] = (25, 75),
) -> dict:
    """volatility分布のパーセンタイルで各時刻にレジームラベルを付与。

    Args:
        timeline: build_market_timeline()の結果
        percentiles: (低/中の境界, 中/高の境界) パーセンタイル

    Returns:
        {
            "boundaries": {"p25": float, "p75": float},
            "labels": {datetime: "low" | "mid" | "high"},
        }
    """
    if not timeline:
        return {
            "boundaries": {"p25": 0.0, "p75": 0.0},
            "labels": {},
        }

    vols = sorted(s.volatility for s in timeline)
    p_low = _percentile(vols, percentiles[0])
    p_high = _percentile(vols, percentiles[1])

    labels: dict[datetime, str] = {}
    for s in timeline:
        if s.volatility < p_low:
            labels[s.timestamp] = "low"
        elif s.volatility >= p_high:
            labels[s.timestamp] = "high"
        else:
            labels[s.timestamp] = "mid"

    return {
        "boundaries": {"p25": p_low, "p75": p_high},
        "labels": labels,
    }
```

- [ ] **Step 4: テスト実行してパスを確認**

Run: `cd scripts && python -m pytest backtester/tests/test_vol_regime.py -v`
Expected: 3 passed

- [ ] **Step 5: コミット**

```bash
git add scripts/backtester/vol_regime.py scripts/backtester/tests/test_vol_regime.py
git commit -m "feat: add vol regime classification module"
```

---

### Task 2: レジーム別P&L集計

**Files:**
- Modify: `scripts/backtester/vol_regime.py`
- Modify: `scripts/backtester/tests/test_vol_regime.py`

- [ ] **Step 1: failing test を書く — analyze_by_vol_regime**

以下を `test_vol_regime.py` に追加:

```python
from backtester.data_loader import TradeEvent, Trip
from backtester.vol_regime import analyze_by_vol_regime


def _make_trade_event(
    ts_hour: int,
    ts_minute: int = 0,
    price: float = 13000000.0,
    side: str = "BUY",
    is_close: bool = False,
    level: int = 25,
) -> TradeEvent:
    """テスト用TradeEvent生成。"""
    return TradeEvent(
        timestamp=datetime(2026, 2, 27, ts_hour, ts_minute, 0, tzinfo=timezone.utc),
        event="ORDER_FILLED",
        order_id="test",
        side=side,
        price=price,
        size=0.001,
        mid_price=price,
        is_close=is_close,
        level=level,
        p_fill=0.1,
        best_ev=1.0,
        single_leg_ev=0.5,
        sigma_1s=0.5,
        spread_pct=0.00025,
        t_optimal_ms=3000,
        order_age_ms=500,
        error="",
    )


def _make_trip(
    open_hour: int,
    close_hour: int,
    pnl: float,
    adverse: float = -2.0,
    spread: float = 3.0,
) -> Trip:
    """テスト用Trip生成。"""
    open_fill = _make_trade_event(open_hour, price=13000000.0)
    close_fill = _make_trade_event(close_hour, price=13000000.0 + pnl / 0.001, is_close=True)
    return Trip(
        open_fill=open_fill,
        close_fill=close_fill,
        sl_triggered=False,
        hold_time_s=(close_hour - open_hour) * 3600.0,
        pnl_jpy=pnl,
        mid_adverse_jpy=adverse,
        spread_captured_jpy=spread,
    )


def test_analyze_by_vol_regime_basic():
    """レジーム別にP&Lが正しく集計される。"""
    timeline = [
        _make_market_state(0, 100.0),   # low
        _make_market_state(1, 200.0),   # low
        _make_market_state(2, 500.0),   # mid
        _make_market_state(3, 600.0),   # mid
        _make_market_state(4, 500.0),   # mid
        _make_market_state(5, 600.0),   # mid
        _make_market_state(6, 900.0),   # high
        _make_market_state(7, 1000.0),  # high
    ]
    regime_result = classify_vol_regime(timeline)

    trips = [
        _make_trip(0, 1, pnl=5.0),    # low regime
        _make_trip(1, 2, pnl=3.0),    # low regime
        _make_trip(3, 4, pnl=-2.0),   # mid regime
        _make_trip(6, 7, pnl=-8.0),   # high regime
    ]

    rows = analyze_by_vol_regime(trips, regime_result, timeline)

    # 3レジームの結果が返る
    regime_names = [r["regime"] for r in rows]
    assert "low" in regime_names
    assert "mid" in regime_names
    assert "high" in regime_names

    # low: 2件, pnl_sum=8.0
    low_row = next(r for r in rows if r["regime"] == "low")
    assert low_row["count"] == 2
    assert abs(low_row["pnl_sum"] - 8.0) < 0.01

    # high: 1件, pnl_sum=-8.0
    high_row = next(r for r in rows if r["regime"] == "high")
    assert high_row["count"] == 1
    assert abs(high_row["pnl_sum"] - (-8.0)) < 0.01


def test_analyze_by_vol_regime_empty_trips():
    """トリップ0件 → 空結果。"""
    timeline = [_make_market_state(0, 500.0)]
    regime_result = classify_vol_regime(timeline)
    rows = analyze_by_vol_regime([], regime_result, timeline)
    assert len(rows) == 0
```

- [ ] **Step 2: テスト実行して失敗を確認**

Run: `cd scripts && python -m pytest backtester/tests/test_vol_regime.py -v -k "analyze"`
Expected: FAIL with "ImportError"

- [ ] **Step 3: analyze_by_vol_regime を実装**

以下を `vol_regime.py` に追加:

```python
from .data_loader import Trip


def _get_trip_regime(
    trip: Trip,
    regime_result: dict,
    timeline: list[MarketState],
) -> tuple[str, float]:
    """tripのopen時刻でのレジームとvolatilityを返す。"""
    state = get_market_state_at(timeline, trip.open_fill.timestamp)
    if state is None:
        return "mid", 0.0

    label = regime_result["labels"].get(state.timestamp, "mid")
    return label, state.volatility


def analyze_by_vol_regime(
    trips: list[Trip],
    regime_result: dict,
    timeline: list[MarketState],
) -> list[dict]:
    """レジーム別のP&L集計。

    Args:
        trips: build_trips()の結果
        regime_result: classify_vol_regime()の結果
        timeline: build_market_timeline()の結果

    Returns:
        レジーム別の集計リスト（low, mid, high順）
    """
    matched = [t for t in trips if t.close_fill is not None]
    if not matched:
        return []

    groups: dict[str, list[tuple[Trip, float]]] = {
        "low": [], "mid": [], "high": [],
    }

    for t in matched:
        regime, vol = _get_trip_regime(t, regime_result, timeline)
        if regime in groups:
            groups[regime].append((t, vol))

    rows = []
    for regime in ["low", "mid", "high"]:
        items = groups[regime]
        if not items:
            rows.append({
                "regime": regime,
                "count": 0,
                "pnl_sum": 0.0,
                "pnl_mean": 0.0,
                "adverse_mean": 0.0,
                "win_rate": 0.0,
                "hold_mean_s": 0.0,
                "vol_mean": 0.0,
            })
            continue

        trip_list = [item[0] for item in items]
        vol_list = [item[1] for item in items]
        pnl_list = [t.pnl_jpy for t in trip_list]
        adverse_list = [t.mid_adverse_jpy for t in trip_list]
        hold_list = [t.hold_time_s for t in trip_list]
        wins = sum(1 for p in pnl_list if p > 0)

        rows.append({
            "regime": regime,
            "count": len(trip_list),
            "pnl_sum": sum(pnl_list),
            "pnl_mean": sum(pnl_list) / len(pnl_list),
            "adverse_mean": sum(adverse_list) / len(adverse_list),
            "win_rate": wins / len(trip_list),
            "hold_mean_s": sum(hold_list) / len(hold_list),
            "vol_mean": sum(vol_list) / len(vol_list),
        })

    return rows
```

- [ ] **Step 4: テスト実行してパスを確認**

Run: `cd scripts && python -m pytest backtester/tests/test_vol_regime.py -v`
Expected: 5 passed

- [ ] **Step 5: コミット**

```bash
git add scripts/backtester/vol_regime.py scripts/backtester/tests/test_vol_regime.py
git commit -m "feat: add analyze_by_vol_regime for regime-based P&L analysis"
```

---

### Task 3: フィルタwhat-if

**Files:**
- Modify: `scripts/backtester/vol_regime.py`
- Modify: `scripts/backtester/tests/test_vol_regime.py`

- [ ] **Step 1: failing test を書く — calc_vol_filter_impact**

以下を `test_vol_regime.py` に追加:

```python
from backtester.vol_regime import calc_vol_filter_impact


def test_calc_vol_filter_impact_exclude_high():
    """high除外でincluded/excluded/totalが正しい。"""
    timeline = [
        _make_market_state(0, 100.0),
        _make_market_state(1, 200.0),
        _make_market_state(2, 500.0),
        _make_market_state(3, 600.0),
        _make_market_state(4, 500.0),
        _make_market_state(5, 600.0),
        _make_market_state(6, 900.0),
        _make_market_state(7, 1000.0),
    ]
    regime_result = classify_vol_regime(timeline)

    trips = [
        _make_trip(0, 1, pnl=5.0),
        _make_trip(3, 4, pnl=-2.0),
        _make_trip(6, 7, pnl=-8.0),
    ]

    result = calc_vol_filter_impact(trips, regime_result, timeline, exclude_regimes=["high"])

    # high除外: 2件 (low + mid)
    assert result["included"]["count"] == 2
    assert abs(result["included"]["pnl_sum"] - 3.0) < 0.01

    # excluded: 1件 (high)
    assert result["excluded"]["count"] == 1
    assert abs(result["excluded"]["pnl_sum"] - (-8.0)) < 0.01


def test_calc_vol_filter_impact_exclude_multiple():
    """high+mid除外。"""
    timeline = [
        _make_market_state(0, 100.0),
        _make_market_state(1, 200.0),
        _make_market_state(2, 500.0),
        _make_market_state(3, 600.0),
        _make_market_state(4, 500.0),
        _make_market_state(5, 600.0),
        _make_market_state(6, 900.0),
        _make_market_state(7, 1000.0),
    ]
    regime_result = classify_vol_regime(timeline)

    trips = [
        _make_trip(0, 1, pnl=5.0),
        _make_trip(3, 4, pnl=-2.0),
        _make_trip(6, 7, pnl=-8.0),
    ]

    result = calc_vol_filter_impact(trips, regime_result, timeline, exclude_regimes=["high", "mid"])
    assert result["included"]["count"] == 1
    assert abs(result["included"]["pnl_sum"] - 5.0) < 0.01
```

- [ ] **Step 2: テスト実行して失敗を確認**

Run: `cd scripts && python -m pytest backtester/tests/test_vol_regime.py -v -k "filter"`
Expected: FAIL with "ImportError"

- [ ] **Step 3: calc_vol_filter_impact を実装**

以下を `vol_regime.py` に追加:

```python
def calc_vol_filter_impact(
    trips: list[Trip],
    regime_result: dict,
    timeline: list[MarketState],
    exclude_regimes: list[str],
) -> dict:
    """特定レジームを除外した場合のP&L影響をシミュレート。

    Args:
        trips: build_trips()の結果
        regime_result: classify_vol_regime()の結果
        timeline: build_market_timeline()の結果
        exclude_regimes: 除外するレジーム名のリスト

    Returns:
        {
            "exclude_spec": str,
            "included": {"pnl_sum": float, "pnl_mean": float, "count": int},
            "excluded": {"pnl_sum": float, "pnl_mean": float, "count": int},
            "total": {"pnl_sum": float, "count": int},
        }
    """
    matched = [t for t in trips if t.close_fill is not None]
    exclude_set = set(exclude_regimes)

    included: list[Trip] = []
    excluded: list[Trip] = []

    for t in matched:
        regime, _ = _get_trip_regime(t, regime_result, timeline)
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

Run: `cd scripts && python -m pytest backtester/tests/test_vol_regime.py -v`
Expected: 7 passed

- [ ] **Step 5: コミット**

```bash
git add scripts/backtester/vol_regime.py scripts/backtester/tests/test_vol_regime.py
git commit -m "feat: add calc_vol_filter_impact for regime-based what-if"
```

---

### Task 4: run_analysis.py にvol_regime分析モードを統合

**Files:**
- Modify: `scripts/backtester/run_analysis.py`

- [ ] **Step 1: run_analysis.py にimportを追加**

既存importブロック（`from backtester.dsr import ...` の後）に追加:

```python
from backtester.vol_regime import (  # noqa: E402
    analyze_by_vol_regime,
    calc_vol_filter_impact,
    classify_vol_regime,
)
```

- [ ] **Step 2: analysis_vol_regime 関数を追加**

`analysis_close_dynamics` 関数の前に追加:

```python
def analysis_vol_regime(trades, metrics, trips, timeline):
    """ボラティリティレジーム別P&L分析。"""
    print("\n=== ボラティリティレジーム分析 ===")
    regime_result = classify_vol_regime(timeline)
    p25 = regime_result["boundaries"]["p25"]
    p75 = regime_result["boundaries"]["p75"]
    print(f"  Volatility分布: P25={p25:.1f}  P75={p75:.1f}")

    rows = analyze_by_vol_regime(trips, regime_result, timeline)
    if not rows:
        print("  トリップデータなし")
        return

    print()
    headers = ["レジーム", "件数", "P&L合計", "P&L/trip", "adverse", "win率", "hold(s)", "avg_vol"]
    widths = [10, 6, 10, 9, 9, 8, 8, 9]
    table_rows = []
    for r in rows:
        if r["count"] == 0:
            continue
        table_rows.append([
            r["regime"],
            str(r["count"]),
            f"{r['pnl_sum']:+.2f}",
            f"{r['pnl_mean']:+.3f}",
            f"{r['adverse_mean']:.3f}",
            f"{r['win_rate']:.1%}",
            f"{r['hold_mean_s']:.1f}",
            f"{r['vol_mean']:.1f}",
        ])
    _print_table(headers, table_rows, widths)

    # --- フィルタwhat-if ---
    print("\n=== フィルタwhat-if ===")
    filter_patterns = [
        ["high"],
        ["high", "mid"],
        ["low"],
    ]
    total_count = sum(r["count"] for r in rows)
    total_pnl = sum(r["pnl_sum"] for r in rows)
    overall_mean = total_pnl / total_count if total_count > 0 else 0.0

    wh_headers = ["除外パターン", "件数", "P&L合計", "P&L/trip", "改善"]
    wh_widths = [18, 6, 10, 9, 12]
    wh_rows = []
    for excl in filter_patterns:
        result = calc_vol_filter_impact(trips, regime_result, timeline, exclude_regimes=excl)
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

    # --- DSR 判定 ---
    matched = [t for t in trips if t.close_fill is not None]
    if matched:
        best_sr = float("-inf")
        best_pnl_list: list[float] = []
        for excl in filter_patterns:
            result = calc_vol_filter_impact(trips, regime_result, timeline, exclude_regimes=excl)
            inc = result["included"]
            if inc["count"] >= 2:
                inc_trips = [
                    t for t in matched
                    if _get_trip_regime_label(t, regime_result, timeline) not in set(excl)
                ]
                pnl_list = [t.pnl_jpy for t in inc_trips]
                sr = calc_sharpe_ratio(pnl_list)
                if sr > best_sr:
                    best_sr = sr
                    best_pnl_list = pnl_list
        if best_pnl_list:
            dsr_result = evaluate_dsr(best_pnl_list, N=len(filter_patterns))
            print(f"\n  {format_dsr_line(dsr=dsr_result['dsr'], N=dsr_result['N'], T=dsr_result['T'], sr_best=dsr_result['sr_best'], significant=dsr_result['significant'])}")
```

注意: DSRブロックで使う `_get_trip_regime_label` はヘルパー関数。`vol_regime.py` の `_get_trip_regime` を公開する必要がある。

`vol_regime.py` に以下を追加:

```python
def get_trip_regime_label(
    trip: Trip,
    regime_result: dict,
    timeline: list[MarketState],
) -> str:
    """tripのopen時刻でのレジームラベルを返す。"""
    regime, _ = _get_trip_regime(trip, regime_result, timeline)
    return regime
```

`run_analysis.py` のimportにも追加:

```python
from backtester.vol_regime import (  # noqa: E402
    analyze_by_vol_regime,
    calc_vol_filter_impact,
    classify_vol_regime,
    get_trip_regime_label,
)
```

DSRブロック内の `_get_trip_regime_label` を `get_trip_regime_label` に変更。

- [ ] **Step 3: main()にvol_regime分析を追加**

`main()` の `--analysis` choices に `"vol_regime"` を追加:

```python
    parser.add_argument(
        "--analysis",
        choices=["all", "hold_time", "time_filter", "ev_sim", "close_dynamics", "market_hours", "vol_regime"],
        default="all",
        help="実行する分析",
    )
```

analysis実行部分（`analysis_market_hours` の後）に追加:

```python
    if args.analysis in ("all", "vol_regime"):
        analysis_vol_regime(trades, metrics, trips, timeline)
```

- [ ] **Step 4: 動作確認**

Run: `cd scripts && python backtester/run_analysis.py --date 2026-02-27 --analysis vol_regime`
Expected: レジーム別テーブル、フィルタwhat-if、DSR判定が表示される

- [ ] **Step 5: コミット**

```bash
git add scripts/backtester/vol_regime.py scripts/backtester/run_analysis.py
git commit -m "feat: integrate vol_regime analysis into run_analysis CLI"
```

---

### Task 5: __init__.py 更新と全テスト

**Files:**
- Modify: `scripts/backtester/__init__.py`

- [ ] **Step 1: __init__.py にモジュール説明を追加**

`dsr` の行の後に追加:

```
  vol_regime     - ボラティリティレジーム分析 (パーセンタイル分類・what-if)
```

- [ ] **Step 2: 全テスト実行**

Run: `cd scripts && python -m pytest backtester/tests/ -v`
Expected: all passed（DSR 22 + vol_regime 7 = 29）

- [ ] **Step 3: コミット**

```bash
git add scripts/backtester/__init__.py
git commit -m "docs: add vol_regime module to backtester __init__ docstring"
```
