# min_hold シミュレーション分析 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** バックテスターにmin_hold（最低保持時間）シミュレーション分析モードを追加し、close禁止期間の最適値をDSRで統計検証する

**Architecture:** `scripts/backtester/min_hold_sim.py` にシミュレーションロジックを実装し、`run_analysis.py` から `--analysis min_hold` で呼び出す。既存 `cnew3_whatif.py` の検証済みロジックを再利用・整理。各min_hold値のシミュレーション後P&Lリストを保持し、DSRでベストパターンの統計的有意性を判定。

**Tech Stack:** Python, 既存 backtester モジュール（market_replay, data_loader, dsr）

---

### Task 1: min_hold_sim.py — simulate_min_hold

**Files:**
- Create: `scripts/backtester/min_hold_sim.py`
- Create: `scripts/backtester/tests/test_min_hold_sim.py`

- [ ] **Step 1: failing test を書く**

```python
# scripts/backtester/tests/test_min_hold_sim.py
"""min_holdシミュレーションのテスト。"""
from datetime import datetime, timedelta, timezone

from backtester.data_loader import TradeEvent, Trip
from backtester.market_replay import MarketState
from backtester.min_hold_sim import simulate_min_hold


def _make_market_state(ts_sec: int, mid_price: float, volatility: float = 500.0) -> MarketState:
    """テスト用MarketState生成。ts_secは基準時刻からの秒数。"""
    base = datetime(2026, 2, 27, 0, 0, 0, tzinfo=timezone.utc)
    return MarketState(
        timestamp=base + timedelta(seconds=ts_sec),
        mid_price=mid_price,
        spread=500.0,
        sigma_1s=0.5,
        volatility=volatility,
        t_optimal_ms=3000,
        long_size=0.0,
        short_size=0.0,
        best_ask=mid_price + 250,
        best_bid=mid_price - 250,
        buy_spread_pct=0.00022,
        sell_spread_pct=0.00022,
    )


def _make_trade_event(
    ts_sec: int,
    price: float = 13000000.0,
    mid_price: float = 13000000.0,
    side: str = "BUY",
    is_close: bool = False,
) -> TradeEvent:
    """テスト用TradeEvent生成。"""
    base = datetime(2026, 2, 27, 0, 0, 0, tzinfo=timezone.utc)
    return TradeEvent(
        timestamp=base + timedelta(seconds=ts_sec),
        event="ORDER_FILLED",
        order_id="test",
        side=side,
        price=price,
        size=0.001,
        mid_price=mid_price,
        is_close=is_close,
        level=25,
        p_fill=0.1,
        best_ev=1.0,
        single_leg_ev=0.5,
        sigma_1s=0.5,
        spread_pct=0.00025,
        t_optimal_ms=3000,
        order_age_ms=500,
        error="",
    )


def _make_trip(open_sec: int, close_sec: int, pnl: float, spread: float = 3.0) -> Trip:
    """テスト用Trip生成。"""
    open_fill = _make_trade_event(open_sec, mid_price=13000000.0)
    close_fill = _make_trade_event(
        close_sec,
        price=13000000.0 + pnl / 0.001,
        mid_price=13000000.0 + pnl / 0.001 - spread / 0.001,
        is_close=True,
    )
    return Trip(
        open_fill=open_fill,
        close_fill=close_fill,
        sl_triggered=False,
        hold_time_s=float(close_sec - open_sec),
        pnl_jpy=pnl,
        mid_adverse_jpy=-2.0,
        spread_captured_jpy=spread,
    )


def test_simulate_min_hold_no_effect():
    """全tripがmin_hold以上 → シミュレーション影響なし。"""
    timeline = [_make_market_state(s, 13000000.0) for s in range(0, 601, 3)]
    trips = [
        _make_trip(0, 200, pnl=-5.0),
        _make_trip(300, 500, pnl=3.0),
    ]
    result = simulate_min_hold(trips, timeline, min_hold_s=60.0)
    assert result["affected_trips"] == 0
    assert abs(result["original_pnl_sum"] - (-2.0)) < 0.01
    assert abs(result["simulated_pnl_sum"] - (-2.0)) < 0.01
    assert len(result["simulated_pnl_list"]) == 2


def test_simulate_min_hold_affects_short_trip():
    """hold_time < min_holdのtripが再評価される。"""
    # mid_priceが時間とともに戻る（mean reversion）シナリオ
    # t=0: open BUY @ mid=13000000
    # t=10: mid=12999000 (逆行) → 現行close, pnl=-1.0
    # t=120: mid=13000500 (戻り)
    timeline = [
        _make_market_state(0, 13000000.0),
        _make_market_state(3, 12999500.0),
        _make_market_state(10, 12999000.0),
        _make_market_state(60, 12999800.0),
        _make_market_state(120, 13000500.0),
        _make_market_state(180, 13000200.0),
    ]
    trips = [
        _make_trip(0, 10, pnl=-1.0, spread=3.0),  # hold=10s, 短すぎる
    ]
    result = simulate_min_hold(trips, timeline, min_hold_s=120.0)
    assert result["affected_trips"] == 1
    # t=120でmid=13000500, direction=BUY=+1
    # new_pnl = (13000500 - 13000000) * 0.001 * 1 + 3.0 = 0.5 + 3.0 = 3.5
    assert result["simulated_pnl_sum"] > result["original_pnl_sum"]
    assert len(result["simulated_pnl_list"]) == 1


def test_simulate_min_hold_empty_trips():
    """空tripリスト → ゼロ結果。"""
    timeline = [_make_market_state(0, 13000000.0)]
    result = simulate_min_hold([], timeline, min_hold_s=60.0)
    assert result["total_trips"] == 0
    assert result["simulated_pnl_list"] == []
```

- [ ] **Step 2: テスト実行して失敗を確認**

Run: `cd scripts && python -m pytest backtester/tests/test_min_hold_sim.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: simulate_min_hold を実装**

```python
# scripts/backtester/min_hold_sim.py
"""min_hold（最低保持時間）シミュレーションモジュール。

open後一定時間closeを禁止した場合のP&L変化をwhat-ifシミュレーションする。
cnew3_whatif.pyの検証済みロジックを正式分析モードとして再構成。
"""
from __future__ import annotations

from datetime import timedelta

from .data_loader import Trip
from .market_replay import MarketState, get_mid_price_series

# metricsの3s間隔 + 余裕
_TIMELINE_BUFFER_S = 10


def simulate_min_hold(
    trips: list[Trip],
    timeline: list[MarketState],
    min_hold_s: float,
) -> dict:
    """hold_time < min_hold_s のtripをmin_hold_s時点のmid_priceで再評価。

    Args:
        trips: build_trips()の結果
        timeline: build_market_timeline()の結果
        min_hold_s: 最低保持時間（秒）

    Returns:
        {
            "min_hold_s": float,
            "total_trips": int,
            "affected_trips": int,
            "original_pnl_sum": float,
            "simulated_pnl_sum": float,
            "delta_pnl": float,
            "pnl_per_trip_orig": float,
            "pnl_per_trip_sim": float,
            "simulated_pnl_list": list[float],
        }
    """
    matched = [t for t in trips if t.close_fill is not None]

    if not matched:
        return {
            "min_hold_s": min_hold_s,
            "total_trips": 0,
            "affected_trips": 0,
            "original_pnl_sum": 0.0,
            "simulated_pnl_sum": 0.0,
            "delta_pnl": 0.0,
            "pnl_per_trip_orig": 0.0,
            "pnl_per_trip_sim": 0.0,
            "simulated_pnl_list": [],
        }

    original_pnl = 0.0
    simulated_pnl = 0.0
    affected = 0
    sim_pnl_list: list[float] = []

    for trip in matched:
        original_pnl += trip.pnl_jpy

        if trip.hold_time_s >= min_hold_s:
            simulated_pnl += trip.pnl_jpy
            sim_pnl_list.append(trip.pnl_jpy)
            continue

        # min_hold_s時点のmid_priceを取得
        open_ts = trip.open_fill.timestamp
        target_ts = open_ts + timedelta(seconds=min_hold_s)
        search_end = target_ts + timedelta(seconds=_TIMELINE_BUFFER_S)
        series = get_mid_price_series(timeline, open_ts, search_end)

        target_mid = None
        for ts, mid in series:
            elapsed = (ts - open_ts).total_seconds()
            if elapsed >= min_hold_s - 1.0:
                target_mid = mid
                break

        if target_mid is None:
            simulated_pnl += trip.pnl_jpy
            sim_pnl_list.append(trip.pnl_jpy)
            continue

        affected += 1
        direction = 1.0 if trip.open_fill.side == "BUY" else -1.0
        size = trip.open_fill.size
        mid_change = target_mid - trip.open_fill.mid_price
        mid_pnl = mid_change * size * direction
        new_pnl = mid_pnl + trip.spread_captured_jpy
        simulated_pnl += new_pnl
        sim_pnl_list.append(new_pnl)

    total = len(matched)
    return {
        "min_hold_s": min_hold_s,
        "total_trips": total,
        "affected_trips": affected,
        "original_pnl_sum": original_pnl,
        "simulated_pnl_sum": simulated_pnl,
        "delta_pnl": simulated_pnl - original_pnl,
        "pnl_per_trip_orig": original_pnl / total,
        "pnl_per_trip_sim": simulated_pnl / total,
        "simulated_pnl_list": sim_pnl_list,
    }
```

- [ ] **Step 4: テスト実行してパスを確認**

Run: `cd scripts && python -m pytest backtester/tests/test_min_hold_sim.py -v`
Expected: 3 passed

- [ ] **Step 5: コミット**

```bash
git add scripts/backtester/min_hold_sim.py scripts/backtester/tests/test_min_hold_sim.py
git commit -m "feat: add min_hold simulation module"
```

---

### Task 2: simulate_min_hold_sweep

**Files:**
- Modify: `scripts/backtester/min_hold_sim.py`
- Modify: `scripts/backtester/tests/test_min_hold_sim.py`

- [ ] **Step 1: failing test を書く**

以下を `test_min_hold_sim.py` に追加:

```python
from backtester.min_hold_sim import simulate_min_hold_sweep


def test_sweep_returns_multiple_results():
    """sweepが各min_hold値の結果を返す。"""
    timeline = [_make_market_state(s, 13000000.0) for s in range(0, 601, 3)]
    trips = [
        _make_trip(0, 10, pnl=-1.0),
        _make_trip(100, 200, pnl=-3.0),
        _make_trip(300, 500, pnl=5.0),
    ]
    results = simulate_min_hold_sweep(trips, timeline, hold_values=[30, 60, 120])
    assert len(results) == 3
    assert results[0]["min_hold_s"] == 30
    assert results[1]["min_hold_s"] == 60
    assert results[2]["min_hold_s"] == 120


def test_sweep_default_values():
    """デフォルトhold_valuesが[30, 60, 120, 180, 300]。"""
    timeline = [_make_market_state(s, 13000000.0) for s in range(0, 601, 3)]
    trips = [_make_trip(0, 10, pnl=-1.0)]
    results = simulate_min_hold_sweep(trips, timeline)
    assert len(results) == 5
    assert [r["min_hold_s"] for r in results] == [30, 60, 120, 180, 300]
```

- [ ] **Step 2: テスト実行して失敗を確認**

Run: `cd scripts && python -m pytest backtester/tests/test_min_hold_sim.py -v -k "sweep"`
Expected: FAIL

- [ ] **Step 3: simulate_min_hold_sweep を実装**

以下を `min_hold_sim.py` に追加:

```python
_DEFAULT_HOLD_VALUES = [30, 60, 120, 180, 300]


def simulate_min_hold_sweep(
    trips: list[Trip],
    timeline: list[MarketState],
    hold_values: list[int] | None = None,
) -> list[dict]:
    """複数のmin_hold値で一括シミュレーション。

    Args:
        trips: build_trips()の結果
        timeline: build_market_timeline()の結果
        hold_values: min_hold値のリスト（秒）。Noneならデフォルト使用

    Returns:
        各min_hold値のsimulate_min_hold結果のリスト
    """
    if hold_values is None:
        hold_values = _DEFAULT_HOLD_VALUES

    return [
        simulate_min_hold(trips, timeline, float(h))
        for h in hold_values
    ]
```

- [ ] **Step 4: テスト実行してパスを確認**

Run: `cd scripts && python -m pytest backtester/tests/test_min_hold_sim.py -v`
Expected: 5 passed

- [ ] **Step 5: コミット**

```bash
git add scripts/backtester/min_hold_sim.py scripts/backtester/tests/test_min_hold_sim.py
git commit -m "feat: add simulate_min_hold_sweep for batch analysis"
```

---

### Task 3: run_analysis.py にmin_hold分析モードを統合

**Files:**
- Modify: `scripts/backtester/run_analysis.py`

- [ ] **Step 1: import追加**

既存importブロック（`from backtester.vol_regime import ...` の後）に追加:

```python
from backtester.min_hold_sim import simulate_min_hold_sweep  # noqa: E402
```

- [ ] **Step 2: analysis_min_hold 関数を追加**

`analysis_vol_regime` 関数の後に追加:

```python
def analysis_min_hold(trades, metrics, trips, timeline):
    """min_hold（最低保持時間）シミュレーション分析。"""
    print("\n=== min_hold シミュレーション ===")

    results = simulate_min_hold_sweep(trips, timeline)

    if not results or results[0]["total_trips"] == 0:
        print("  トリップデータなし")
        return

    headers = ["min_hold", "件数", "影響trip", "orig_pnl/t", "sim_pnl/t", "delta"]
    widths = [10, 6, 10, 12, 12, 10]
    table_rows = []
    for r in results:
        table_rows.append([
            f"{r['min_hold_s']:.0f}s",
            str(r["total_trips"]),
            str(r["affected_trips"]),
            f"{r['pnl_per_trip_orig']:+.3f}",
            f"{r['pnl_per_trip_sim']:+.3f}",
            f"{r['delta_pnl'] / r['total_trips']:+.3f}",
        ])
    _print_table(headers, table_rows, widths)

    # --- DSR 判定 ---
    best_sr = float("-inf")
    best_pnl_list: list[float] = []
    for r in results:
        pnl_list = r["simulated_pnl_list"]
        if len(pnl_list) >= 2:
            sr = calc_sharpe_ratio(pnl_list)
            if sr > best_sr:
                best_sr = sr
                best_pnl_list = pnl_list
    if best_pnl_list:
        dsr_result = evaluate_dsr(best_pnl_list, N=len(results))
        dsr_line = format_dsr_line(
            dsr=dsr_result["dsr"],
            N=dsr_result["N"],
            T=dsr_result["T"],
            sr_best=dsr_result["sr_best"],
            significant=dsr_result["significant"],
        )
        print(f"\n  {dsr_line}")
```

- [ ] **Step 3: main()更新**

argparse choicesに `"min_hold"` を追加:

```python
choices=["all", "hold_time", "time_filter", "ev_sim", "close_dynamics", "market_hours", "vol_regime", "min_hold"],
```

analysis実行部分の末尾に追加:

```python
    if args.analysis in ("all", "min_hold"):
        analysis_min_hold(trades, metrics, trips, timeline)
```

- [ ] **Step 4: 動作確認**

Run: `cd scripts && python backtester/run_analysis.py --date 2026-02-27 --analysis min_hold`
Expected: min_holdテーブルとDSR判定が表示される

- [ ] **Step 5: コミット**

```bash
git add scripts/backtester/run_analysis.py
git commit -m "feat: integrate min_hold analysis into run_analysis CLI"
```

---

### Task 4: __init__.py 更新と全テスト

**Files:**
- Modify: `scripts/backtester/__init__.py`

- [ ] **Step 1: __init__.py にモジュール説明を追加**

`vol_regime` の行の後に追加:

```
  min_hold_sim   - min_hold（最低保持時間）シミュレーション
```

- [ ] **Step 2: 全テスト実行**

Run: `cd scripts && python -m pytest backtester/tests/ -v`
Expected: all passed（DSR 22 + vol_regime 8 + min_hold 5 = 35）

- [ ] **Step 3: コミット**

```bash
git add scripts/backtester/__init__.py
git commit -m "docs: add min_hold_sim module to backtester __init__ docstring"
```
