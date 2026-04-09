# close_fill_sim 実装プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** min_hold x close_spread_factor のパラメータスイープを Lookahead bias なしで実行する close fill シミュレータ

**Architecture:** 期待値モード（決定論的）で各 3s ティックの fill 確率を Brownian micro-fill モデルで計算し、p_survive を減衰させながら加重 P&L を算出。既存 data_loader / market_replay / dsr をそのまま利用。

**Tech Stack:** Python 3, scipy.stats.norm, dataclasses, bisect, 既存 backtester モジュール

**Spec:** `docs/superpowers/specs/2026-04-10-close-fill-sim-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `scripts/backtester/close_fill_sim.py` | SimResult, calc_close_price, calc_fill_prob, simulate loop, sweep, grid display |
| Create | `scripts/backtester/test_close_fill_sim.py` | 全テスト |
| Modify | `scripts/backtester/run_analysis.py:20-53,627-691` | close_fill import + analysis mode + CLI args |

---

### Task 1: SimResult + calc_close_price

**Files:**
- Create: `scripts/backtester/test_close_fill_sim.py`
- Create: `scripts/backtester/close_fill_sim.py`

- [ ] **Step 1: Write failing tests for calc_close_price**

```python
# scripts/backtester/test_close_fill_sim.py
"""close_fill_sim のテスト。"""
from __future__ import annotations

import math
import pytest
from datetime import datetime, timezone, timedelta

from backtester.close_fill_sim import SimResult, calc_close_price


class TestCalcClosePrice:
    """close価格計算のテスト。"""

    def test_close_long_l25(self):
        """Long close (SELL limit): L25, mid=14_000_000, factor=0.4"""
        # spread_pct=25e-5, level_spread=14_000_000 * 25e-5 = 3500
        # adjusted = 3500 - 50 = 3450
        # close_price = mid + 3450 * 0.4 = 14_000_000 + 1380 = 14_001_380
        price = calc_close_price(
            mid=14_000_000.0,
            spread_pct=25e-5,
            factor=0.4,
            direction=1,  # long
            position_penalty=50.0,
        )
        assert price == 14_001_380.0

    def test_close_short_l25(self):
        """Short close (BUY limit): L25, mid=14_000_000, factor=0.4"""
        # close_price = mid - 3450 * 0.4 = 14_000_000 - 1380 = 13_998_620
        price = calc_close_price(
            mid=14_000_000.0,
            spread_pct=25e-5,
            factor=0.4,
            direction=-1,  # short
            position_penalty=50.0,
        )
        assert price == 13_998_620.0

    def test_close_clamps_to_mid_plus_1(self):
        """factor=0, adjusted_spread=0 -> clamp to mid+1 (long) / mid-1 (short)"""
        price_long = calc_close_price(
            mid=14_000_000.0,
            spread_pct=25e-5,
            factor=0.0,
            direction=1,
            position_penalty=50.0,
        )
        assert price_long == 14_000_001.0

        price_short = calc_close_price(
            mid=14_000_000.0,
            spread_pct=25e-5,
            factor=0.0,
            direction=-1,
            position_penalty=50.0,
        )
        assert price_short == 13_999_999.0

    def test_close_l22(self):
        """L22 で factor=0.3"""
        # spread_pct=22e-5, level_spread=14M * 22e-5 = 3080
        # adjusted = 3080 - 50 = 3030
        # close_price = 14M + 3030 * 0.3 = 14_000_909
        price = calc_close_price(
            mid=14_000_000.0,
            spread_pct=22e-5,
            factor=0.3,
            direction=1,
            position_penalty=50.0,
        )
        assert price == 14_000_909.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/okadasusumutakashi/Desktop/gmo-bot-conoha && python -m pytest scripts/backtester/test_close_fill_sim.py::TestCalcClosePrice -v`
Expected: FAIL (ImportError — module doesn't exist yet)

- [ ] **Step 3: Implement SimResult + calc_close_price**

```python
# scripts/backtester/close_fill_sim.py
"""Close Fill シミュレータ。

close注文のfill確率を確率的にモデル化し、(min_hold, close_spread_factor) の
パラメータスイープを Lookahead bias なしで実行する。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimResult:
    """1 trip x 1 パラメータ組のシミュレーション結果。"""
    trip_index: int
    min_hold_s: int
    factor: float
    simulated_pnl: float
    dominant_outcome: str       # "fill" | "sl" | "timeout"
    p_fill: float
    p_sl: float
    p_timeout: float
    simulated_hold_s: float
    close_delay_s: float
    weighted_fill_price: float


def calc_close_price(
    mid: float,
    spread_pct: float,
    factor: float,
    direction: int,
    position_penalty: float = 50.0,
) -> float:
    """Rust の close 価格計算を再現。

    Args:
        mid: 現在の mid_price
        spread_pct: open_fill.spread_pct (e.g. 25e-5 for L25)
        factor: close_spread_factor (0.0 ~ 1.0)
        direction: +1 (long, close=SELL) / -1 (short, close=BUY)
        position_penalty: Rust ハードコード値 (50.0 for 0.001 BTC)

    Returns:
        close limit price (float)
    """
    level_spread_jpy = spread_pct * mid
    adjusted_spread = level_spread_jpy - position_penalty

    if direction == 1:  # long -> SELL limit
        return max(mid + adjusted_spread * factor, mid + 1.0)
    else:               # short -> BUY limit
        return min(mid - adjusted_spread * factor, mid - 1.0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/okadasusumutakashi/Desktop/gmo-bot-conoha && python -m pytest scripts/backtester/test_close_fill_sim.py::TestCalcClosePrice -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/backtester/close_fill_sim.py scripts/backtester/test_close_fill_sim.py
git commit -m "feat: SimResult dataclass + calc_close_price for close_fill_sim"
```

---

### Task 2: calc_fill_prob

**Files:**
- Modify: `scripts/backtester/test_close_fill_sim.py`
- Modify: `scripts/backtester/close_fill_sim.py`

- [ ] **Step 1: Write failing tests for calc_fill_prob**

Add to `test_close_fill_sim.py`:

```python
from backtester.close_fill_sim import calc_fill_prob


class TestCalcFillProb:
    """fill確率モデルのテスト。"""

    def test_bid_already_at_close_price_long(self):
        """Long close: bid >= close_price -> p_fill = 1.0"""
        p = calc_fill_prob(
            close_price=14_001_380.0,
            best_bid=14_001_400.0,  # bid above close price
            best_ask=14_003_500.0,
            sigma_1s=0.0001,
            mid=14_000_000.0,
            direction=1,
        )
        assert p == 1.0

    def test_ask_already_at_close_price_short(self):
        """Short close: ask <= close_price -> p_fill = 1.0"""
        p = calc_fill_prob(
            close_price=13_998_620.0,
            best_bid=13_996_500.0,
            best_ask=13_998_600.0,  # ask below close price
            sigma_1s=0.0001,
            mid=14_000_000.0,
            direction=-1,
        )
        assert p == 1.0

    def test_zero_sigma_no_fill(self):
        """sigma=0, bid < close_price -> p_fill = 0.0"""
        p = calc_fill_prob(
            close_price=14_001_380.0,
            best_bid=13_996_500.0,
            best_ask=14_003_500.0,
            sigma_1s=0.0,
            mid=14_000_000.0,
            direction=1,
        )
        assert p == 0.0

    def test_high_vol_high_prob(self):
        """高ボラティリティ + 小さい distance -> 高い fill 確率"""
        p = calc_fill_prob(
            close_price=14_001_380.0,
            best_bid=14_001_370.0,  # distance = 10 JPY
            best_ask=14_003_500.0,
            sigma_1s=0.001,         # high vol
            mid=14_000_000.0,
            direction=1,
        )
        # sigma_jpy = 0.001 * 14M = 14000, distance = 10
        # p = 2 * Phi(-10 / (14000 * sqrt(3))) ≈ 2 * Phi(-0.000412) ≈ 0.9997
        assert p > 0.99

    def test_low_vol_large_distance(self):
        """低ボラティリティ + 大きい distance -> 低い fill 確率"""
        p = calc_fill_prob(
            close_price=14_001_380.0,
            best_bid=13_996_500.0,  # distance = 4880 JPY
            best_ask=14_003_500.0,
            sigma_1s=0.00001,       # very low vol
            mid=14_000_000.0,
            direction=1,
        )
        # sigma_jpy = 0.00001 * 14M = 140, distance = 4880
        # p = 2 * Phi(-4880 / (140 * sqrt(3))) ≈ 2 * Phi(-20.1) ≈ 0.0
        assert p < 0.01

    def test_returns_between_0_and_1(self):
        """fill確率は常に [0, 1] 範囲"""
        p = calc_fill_prob(
            close_price=14_001_380.0,
            best_bid=14_000_000.0,
            best_ask=14_003_500.0,
            sigma_1s=0.0005,
            mid=14_000_000.0,
            direction=1,
        )
        assert 0.0 <= p <= 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest scripts/backtester/test_close_fill_sim.py::TestCalcFillProb -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement calc_fill_prob**

Add to `close_fill_sim.py`:

```python
from math import sqrt

from scipy.stats import norm as _norm

_DT = 3.0  # ティック間隔（秒）


def calc_fill_prob(
    close_price: float,
    best_bid: float,
    best_ask: float,
    sigma_1s: float,
    mid: float,
    direction: int,
    dt: float = _DT,
) -> float:
    """3s ティック内の close fill 確率を Brownian micro-fill モデルで計算。

    Args:
        close_price: close limit price
        best_bid / best_ask: 現在の板情報
        sigma_1s: 1秒あたりの fractional volatility
        mid: 現在の mid_price
        direction: +1 (long, SELL limit) / -1 (short, BUY limit)
        dt: ティック間隔（秒）

    Returns:
        P(fill in dt) in [0.0, 1.0]
    """
    if direction == 1:  # long -> SELL limit, fill if bid >= close_price
        if best_bid >= close_price:
            return 1.0
        distance = close_price - best_bid
    else:               # short -> BUY limit, fill if ask <= close_price
        if best_ask <= close_price:
            return 1.0
        distance = best_ask - close_price

    if distance <= 0:
        return 1.0

    sigma_jpy = sigma_1s * mid
    if sigma_jpy <= 0:
        return 0.0

    return float(2.0 * _norm.cdf(-distance / (sigma_jpy * sqrt(dt))))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest scripts/backtester/test_close_fill_sim.py::TestCalcFillProb -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/backtester/close_fill_sim.py scripts/backtester/test_close_fill_sim.py
git commit -m "feat: calc_fill_prob — Brownian micro-fill model"
```

---

### Task 3: simulate_single_trip (core engine)

**Files:**
- Modify: `scripts/backtester/test_close_fill_sim.py`
- Modify: `scripts/backtester/close_fill_sim.py`

- [ ] **Step 1: Write test helpers + failing tests**

Add to `test_close_fill_sim.py`:

```python
from backtester.data_loader import TradeEvent, Trip
from backtester.market_replay import MarketState
from backtester.close_fill_sim import simulate_single_trip


def _make_market_state(
    ts: datetime,
    mid: float = 14_000_000.0,
    spread: float = 7000.0,
    sigma_1s: float = 0.0005,
) -> MarketState:
    """テスト用 MarketState を生成。"""
    half = spread / 2
    return MarketState(
        timestamp=ts,
        mid_price=mid,
        spread=spread,
        sigma_1s=sigma_1s,
        volatility=sigma_1s * mid,
        t_optimal_ms=5000,
        long_size=0.0,
        short_size=0.0,
        best_ask=mid + half,
        best_bid=mid - half,
        buy_spread_pct=25e-5,
        sell_spread_pct=25e-5,
    )


def _make_timeline(
    start: datetime,
    count: int = 200,
    interval_s: float = 3.0,
    mid: float = 14_000_000.0,
    spread: float = 7000.0,
    sigma_1s: float = 0.0005,
    mid_drift_per_tick: float = 0.0,
) -> list[MarketState]:
    """等間隔の MarketState タイムラインを生成。"""
    timeline = []
    for i in range(count):
        ts = start + timedelta(seconds=i * interval_s)
        current_mid = mid + mid_drift_per_tick * i
        timeline.append(_make_market_state(
            ts=ts, mid=current_mid, spread=spread, sigma_1s=sigma_1s,
        ))
    return timeline


def _make_open_fill(
    ts: datetime,
    side: str = "BUY",
    price: float = 13_996_500.0,
    mid_price: float = 14_000_000.0,
    spread_pct: float = 25e-5,
) -> TradeEvent:
    """テスト用 open fill TradeEvent。"""
    return TradeEvent(
        timestamp=ts, event="ORDER_FILLED", order_id="test-001",
        side=side, price=price, size=0.001, mid_price=mid_price,
        is_close=False, level=25, p_fill=0.1, best_ev=0.5,
        single_leg_ev=0.25, sigma_1s=0.0005, spread_pct=spread_pct,
        t_optimal_ms=5000, order_age_ms=3000, error="",
    )


def _make_trip(
    open_fill: TradeEvent,
    close_fill: TradeEvent | None = None,
    sl_triggered: bool = False,
) -> Trip:
    """テスト用 Trip。"""
    if close_fill is None:
        return Trip(
            open_fill=open_fill, close_fill=None, sl_triggered=False,
            hold_time_s=0.0, pnl_jpy=0.0, mid_adverse_jpy=0.0,
            spread_captured_jpy=0.0,
        )
    hold = (close_fill.timestamp - open_fill.timestamp).total_seconds()
    direction = 1.0 if open_fill.side == "BUY" else -1.0
    pnl = (close_fill.price - open_fill.price) * 0.001 * direction
    return Trip(
        open_fill=open_fill, close_fill=close_fill,
        sl_triggered=sl_triggered, hold_time_s=hold,
        pnl_jpy=pnl, mid_adverse_jpy=0.0, spread_captured_jpy=0.0,
    )


class TestSimulateSingleTrip:
    """コアエンジンのテスト。"""

    def test_immediate_fill(self):
        """bid が close price 以上 -> 即 fill, p_fill ≈ 1.0"""
        t0 = datetime(2026, 4, 8, 0, 0, 0, tzinfo=timezone.utc)
        open_fill = _make_open_fill(ts=t0, side="BUY", price=13_996_500.0)
        trip = _make_trip(open_fill)

        # bid = mid + 0 (close_price ≈ mid + 1380)
        # bid を close_price 以上に設定 -> spread を狭くする
        timeline = _make_timeline(
            start=t0, count=200, mid=14_000_000.0,
            spread=200.0,  # bid = 14M - 100 = 13_999_900 > close_price
            sigma_1s=0.001,
        )

        result = simulate_single_trip(
            trip=trip, trip_index=0, timeline=timeline,
            min_hold_s=60, close_spread_factor=0.4,
            stop_loss_jpy=15.0, position_penalty=50.0,
        )
        assert result.dominant_outcome == "fill"
        assert result.p_fill > 0.95
        assert result.simulated_pnl > 0  # close above open

    def test_sl_during_hold_phase(self):
        """Hold 期間中に SL 発動 (mid が急落)"""
        t0 = datetime(2026, 4, 8, 0, 0, 0, tzinfo=timezone.utc)
        open_fill = _make_open_fill(
            ts=t0, side="BUY", price=14_000_000.0, mid_price=14_000_000.0,
        )
        trip = _make_trip(open_fill)

        # mid が毎 tick -500 ずつ下落 -> 30 tick (90s) で -15000
        # unrealized = (mid - open_price) * 0.001
        # -15 JPY に達するのは mid = 14M - 15000 = 13_985_000 (30 tick)
        timeline = _make_timeline(
            start=t0, count=200, mid=14_000_000.0,
            mid_drift_per_tick=-500.0, sigma_1s=0.0001,
        )

        result = simulate_single_trip(
            trip=trip, trip_index=0, timeline=timeline,
            min_hold_s=180, close_spread_factor=0.4,
            stop_loss_jpy=15.0, position_penalty=50.0,
        )
        assert result.dominant_outcome == "sl"
        assert result.p_sl > 0.99
        assert result.simulated_pnl < 0
        assert result.simulated_hold_s < 180  # SL before min_hold

    def test_timeout(self):
        """データ末端まで fill も SL もなし -> timeout"""
        t0 = datetime(2026, 4, 8, 0, 0, 0, tzinfo=timezone.utc)
        open_fill = _make_open_fill(ts=t0, side="BUY", price=14_000_000.0)
        trip = _make_trip(open_fill)

        # 短いタイムライン (30 ticks = 90s) + min_hold=60s
        # fill もしない程度に bid を遠くする
        timeline = _make_timeline(
            start=t0, count=30, mid=14_000_000.0,
            spread=7000.0, sigma_1s=0.00001,  # very low vol
        )

        result = simulate_single_trip(
            trip=trip, trip_index=0, timeline=timeline,
            min_hold_s=60, close_spread_factor=0.4,
            stop_loss_jpy=15.0, position_penalty=50.0,
        )
        assert result.dominant_outcome == "timeout"
        assert result.p_timeout > 0.5

    def test_p_components_sum_to_1(self):
        """p_fill + p_sl + p_timeout ≈ 1.0"""
        t0 = datetime(2026, 4, 8, 0, 0, 0, tzinfo=timezone.utc)
        open_fill = _make_open_fill(ts=t0, side="BUY", price=14_000_000.0)
        trip = _make_trip(open_fill)
        timeline = _make_timeline(start=t0, count=100, sigma_1s=0.0005)

        result = simulate_single_trip(
            trip=trip, trip_index=0, timeline=timeline,
            min_hold_s=60, close_spread_factor=0.4,
            stop_loss_jpy=15.0, position_penalty=50.0,
        )
        total = result.p_fill + result.p_sl + result.p_timeout
        assert abs(total - 1.0) < 0.001

    def test_short_direction(self):
        """Short position の simulation"""
        t0 = datetime(2026, 4, 8, 0, 0, 0, tzinfo=timezone.utc)
        open_fill = _make_open_fill(
            ts=t0, side="SELL", price=14_003_500.0, mid_price=14_000_000.0,
        )
        trip = _make_trip(open_fill)

        # ask を close_price 以下に → 即 fill
        timeline = _make_timeline(
            start=t0, count=200, mid=14_000_000.0,
            spread=200.0, sigma_1s=0.001,
        )

        result = simulate_single_trip(
            trip=trip, trip_index=0, timeline=timeline,
            min_hold_s=60, close_spread_factor=0.4,
            stop_loss_jpy=15.0, position_penalty=50.0,
        )
        assert result.dominant_outcome == "fill"
        assert result.p_fill > 0.95
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest scripts/backtester/test_close_fill_sim.py::TestSimulateSingleTrip -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement simulate_single_trip**

Add to `close_fill_sim.py`:

```python
import bisect
from datetime import timedelta

from .data_loader import Trip
from .market_replay import MarketState


def simulate_single_trip(
    trip: Trip,
    trip_index: int,
    timeline: list[MarketState],
    min_hold_s: int,
    close_spread_factor: float,
    stop_loss_jpy: float = 15.0,
    position_penalty: float = 50.0,
) -> SimResult:
    """1 trip のclose fillを期待値モードでシミュレーション。"""
    open_fill = trip.open_fill
    open_price = open_fill.price
    spread_pct = open_fill.spread_pct
    size = 0.001
    direction = 1 if open_fill.side == "BUY" else -1

    open_ts = open_fill.timestamp
    min_hold_end = open_ts + timedelta(seconds=min_hold_s)

    # タイムライン上の開始インデックスを探す
    timestamps = [s.timestamp for s in timeline]
    start_idx = bisect.bisect_right(timestamps, open_ts)
    if start_idx >= len(timeline):
        return _timeout_result(
            trip_index, min_hold_s, close_spread_factor,
            0.0, 0.0, 0.0, 1.0,
        )

    p_survive = 1.0
    expected_pnl = 0.0
    p_fill_total = 0.0
    p_sl_total = 0.0
    weighted_fill_price_sum = 0.0
    last_mid = timeline[start_idx].mid_price
    last_hold_s = 0.0

    for i in range(start_idx, len(timeline)):
        tick = timeline[i]
        last_mid = tick.mid_price
        elapsed = (tick.timestamp - open_ts).total_seconds()
        last_hold_s = elapsed

        # SL チェック（Phase 1 & 2 共通）
        unrealized = (tick.mid_price - open_price) * size * direction
        if unrealized < -stop_loss_jpy:
            p_sl_total += p_survive
            expected_pnl += p_survive * unrealized
            p_survive = 0.0
            break

        # Phase 1: hold 期間中は close しない
        if tick.timestamp < min_hold_end:
            continue

        # Phase 2: fill 確率計算
        close_price = calc_close_price(
            mid=tick.mid_price, spread_pct=spread_pct,
            factor=close_spread_factor, direction=direction,
            position_penalty=position_penalty,
        )
        p_fill = calc_fill_prob(
            close_price=close_price,
            best_bid=tick.best_bid, best_ask=tick.best_ask,
            sigma_1s=tick.sigma_1s, mid=tick.mid_price,
            direction=direction,
        )

        fill_pnl = (close_price - open_price) * size * direction
        p_fill_at_tick = p_survive * p_fill

        expected_pnl += p_fill_at_tick * fill_pnl
        p_fill_total += p_fill_at_tick
        weighted_fill_price_sum += p_fill_at_tick * close_price

        p_survive *= (1.0 - p_fill)
        if p_survive < 1e-9:
            break

    # タイムアウト: 残存確率分を最終 mid で評価
    p_timeout = p_survive
    if p_timeout > 0:
        terminal_pnl = (last_mid - open_price) * size * direction
        expected_pnl += p_timeout * terminal_pnl

    # dominant outcome
    outcomes = {"fill": p_fill_total, "sl": p_sl_total, "timeout": p_timeout}
    dominant = max(outcomes, key=outcomes.get)

    close_delay = max(last_hold_s - min_hold_s, 0.0)
    avg_fill_price = (
        weighted_fill_price_sum / p_fill_total if p_fill_total > 0 else 0.0
    )

    return SimResult(
        trip_index=trip_index,
        min_hold_s=min_hold_s,
        factor=close_spread_factor,
        simulated_pnl=expected_pnl,
        dominant_outcome=dominant,
        p_fill=p_fill_total,
        p_sl=p_sl_total,
        p_timeout=p_timeout,
        simulated_hold_s=last_hold_s,
        close_delay_s=close_delay,
        weighted_fill_price=avg_fill_price,
    )


def _timeout_result(
    trip_index: int, min_hold_s: int, factor: float,
    pnl: float, hold_s: float, delay_s: float, p_timeout: float,
) -> SimResult:
    return SimResult(
        trip_index=trip_index, min_hold_s=min_hold_s, factor=factor,
        simulated_pnl=pnl, dominant_outcome="timeout",
        p_fill=0.0, p_sl=0.0, p_timeout=p_timeout,
        simulated_hold_s=hold_s, close_delay_s=delay_s,
        weighted_fill_price=0.0,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest scripts/backtester/test_close_fill_sim.py::TestSimulateSingleTrip -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/backtester/close_fill_sim.py scripts/backtester/test_close_fill_sim.py
git commit -m "feat: simulate_single_trip — core close fill engine"
```

---

### Task 4: simulate_close_fill + run_close_fill_sweep

**Files:**
- Modify: `scripts/backtester/test_close_fill_sim.py`
- Modify: `scripts/backtester/close_fill_sim.py`

- [ ] **Step 1: Write failing tests**

Add to `test_close_fill_sim.py`:

```python
from backtester.close_fill_sim import simulate_close_fill, run_close_fill_sweep


class TestSimulateCloseFill:
    """multi-trip シミュレーションのテスト。"""

    def test_multiple_trips(self):
        """複数 trip を処理し、結果数が trip 数と一致"""
        t0 = datetime(2026, 4, 8, 0, 0, 0, tzinfo=timezone.utc)
        timeline = _make_timeline(start=t0, count=300, sigma_1s=0.0005)

        trips = []
        for i in range(5):
            ts = t0 + timedelta(seconds=i * 200)
            of = _make_open_fill(ts=ts, price=14_000_000.0 + i * 100)
            trips.append(_make_trip(of))

        results = simulate_close_fill(
            trips=trips, timeline=timeline,
            min_hold_s=60, close_spread_factor=0.4,
        )
        assert len(results) == 5
        assert all(isinstance(r, SimResult) for r in results)

    def test_empty_trips(self):
        """空の trip リスト -> 空の結果"""
        t0 = datetime(2026, 4, 8, 0, 0, 0, tzinfo=timezone.utc)
        timeline = _make_timeline(start=t0, count=10)
        results = simulate_close_fill(
            trips=[], timeline=timeline,
            min_hold_s=60, close_spread_factor=0.4,
        )
        assert results == []


class TestRunCloseFillSweep:
    """パラメータスイープのテスト。"""

    def test_sweep_returns_all_combos(self):
        """全 (min_hold, factor) 組の結果が返る"""
        t0 = datetime(2026, 4, 8, 0, 0, 0, tzinfo=timezone.utc)
        timeline = _make_timeline(start=t0, count=300, sigma_1s=0.0005)
        of = _make_open_fill(ts=t0, price=14_000_000.0)
        trips = [_make_trip(of)]

        holds = [60, 120]
        factors = [0.3, 0.4]
        sweep = run_close_fill_sweep(
            trips=trips, timeline=timeline,
            min_holds=holds, factors=factors,
        )
        assert len(sweep) == 4  # 2 x 2
        assert (60, 0.3) in sweep
        assert (120, 0.4) in sweep
        assert all(len(v) == 1 for v in sweep.values())

    def test_default_params(self):
        """デフォルトパラメータで 42 組"""
        t0 = datetime(2026, 4, 8, 0, 0, 0, tzinfo=timezone.utc)
        timeline = _make_timeline(start=t0, count=300, sigma_1s=0.0005)
        of = _make_open_fill(ts=t0, price=14_000_000.0)
        trips = [_make_trip(of)]

        sweep = run_close_fill_sweep(trips=trips, timeline=timeline)
        assert len(sweep) == 42  # 6 x 7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest scripts/backtester/test_close_fill_sim.py::TestSimulateCloseFill scripts/backtester/test_close_fill_sim.py::TestRunCloseFillSweep -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement simulate_close_fill + run_close_fill_sweep**

Add to `close_fill_sim.py`:

```python
_DEFAULT_MIN_HOLDS = [60, 90, 120, 180, 240, 300]
_DEFAULT_FACTORS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]


def simulate_close_fill(
    trips: list[Trip],
    timeline: list[MarketState],
    min_hold_s: int,
    close_spread_factor: float,
    stop_loss_jpy: float = 15.0,
    position_penalty: float = 50.0,
) -> list[SimResult]:
    """単一パラメータ組での全 trip シミュレーション。"""
    return [
        simulate_single_trip(
            trip=trip, trip_index=i, timeline=timeline,
            min_hold_s=min_hold_s, close_spread_factor=close_spread_factor,
            stop_loss_jpy=stop_loss_jpy, position_penalty=position_penalty,
        )
        for i, trip in enumerate(trips)
    ]


def run_close_fill_sweep(
    trips: list[Trip],
    timeline: list[MarketState],
    min_holds: list[int] | None = None,
    factors: list[float] | None = None,
    stop_loss_jpy: float = 15.0,
) -> dict[tuple[int, float], list[SimResult]]:
    """全パラメータ組のスイープ実行。"""
    if min_holds is None:
        min_holds = _DEFAULT_MIN_HOLDS
    if factors is None:
        factors = _DEFAULT_FACTORS

    results: dict[tuple[int, float], list[SimResult]] = {}
    for hold in min_holds:
        for factor in factors:
            results[(hold, factor)] = simulate_close_fill(
                trips=trips, timeline=timeline,
                min_hold_s=hold, close_spread_factor=factor,
                stop_loss_jpy=stop_loss_jpy,
            )
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest scripts/backtester/test_close_fill_sim.py::TestSimulateCloseFill scripts/backtester/test_close_fill_sim.py::TestRunCloseFillSweep -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/backtester/close_fill_sim.py scripts/backtester/test_close_fill_sim.py
git commit -m "feat: simulate_close_fill + run_close_fill_sweep"
```

---

### Task 5: aggregate_results + print_sweep_grid

**Files:**
- Modify: `scripts/backtester/test_close_fill_sim.py`
- Modify: `scripts/backtester/close_fill_sim.py`

- [ ] **Step 1: Write failing tests**

Add to `test_close_fill_sim.py`:

```python
from backtester.close_fill_sim import aggregate_results


class TestAggregateResults:
    """集計メトリクスのテスト。"""

    def test_basic_aggregation(self):
        """SimResult リストから集計メトリクスを算出"""
        results = [
            SimResult(
                trip_index=0, min_hold_s=60, factor=0.4,
                simulated_pnl=5.0, dominant_outcome="fill",
                p_fill=0.9, p_sl=0.0, p_timeout=0.1,
                simulated_hold_s=120.0, close_delay_s=60.0,
                weighted_fill_price=14_001_380.0,
            ),
            SimResult(
                trip_index=1, min_hold_s=60, factor=0.4,
                simulated_pnl=-3.0, dominant_outcome="sl",
                p_fill=0.1, p_sl=0.8, p_timeout=0.1,
                simulated_hold_s=45.0, close_delay_s=0.0,
                weighted_fill_price=0.0,
            ),
        ]
        agg = aggregate_results(results)
        assert agg["total_trips"] == 2
        assert agg["total_pnl"] == pytest.approx(2.0)
        assert agg["pnl_per_trip"] == pytest.approx(1.0)
        assert agg["fill_count"] == 1
        assert agg["sl_count"] == 1
        assert agg["timeout_count"] == 0
        assert 0.0 <= agg["win_rate"] <= 1.0

    def test_empty(self):
        """空リスト"""
        agg = aggregate_results([])
        assert agg["total_trips"] == 0
        assert agg["pnl_per_trip"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest scripts/backtester/test_close_fill_sim.py::TestAggregateResults -v`
Expected: FAIL

- [ ] **Step 3: Implement aggregate_results + print_sweep_grid**

Add to `close_fill_sim.py`:

```python
from .dsr import calc_sharpe_ratio, evaluate_dsr, format_dsr_line


def aggregate_results(results: list[SimResult]) -> dict:
    """SimResult リストを集計メトリクスに変換。"""
    if not results:
        return {
            "total_trips": 0, "total_pnl": 0.0, "pnl_per_trip": 0.0,
            "fill_count": 0, "sl_count": 0, "timeout_count": 0,
            "win_rate": 0.0, "avg_hold_s": 0.0, "avg_close_delay_s": 0.0,
            "sharpe": 0.0, "pnl_list": [],
        }

    total = len(results)
    pnl_list = [r.simulated_pnl for r in results]
    total_pnl = sum(pnl_list)
    fill_count = sum(1 for r in results if r.dominant_outcome == "fill")
    sl_count = sum(1 for r in results if r.dominant_outcome == "sl")
    timeout_count = sum(1 for r in results if r.dominant_outcome == "timeout")
    win_count = sum(1 for r in results if r.simulated_pnl > 0)

    return {
        "total_trips": total,
        "total_pnl": total_pnl,
        "pnl_per_trip": total_pnl / total,
        "fill_count": fill_count,
        "sl_count": sl_count,
        "timeout_count": timeout_count,
        "win_rate": win_count / total,
        "avg_hold_s": sum(r.simulated_hold_s for r in results) / total,
        "avg_close_delay_s": sum(r.close_delay_s for r in results) / total,
        "sl_rate": sl_count / total,
        "sharpe": calc_sharpe_ratio(pnl_list),
        "pnl_list": pnl_list,
    }


def print_sweep_grid(
    sweep_results: dict[tuple[int, float], list[SimResult]],
    metric: str = "pnl_per_trip",
) -> None:
    """グリッド形式でスイープ結果を表示。"""
    if not sweep_results:
        print("  No results")
        return

    holds = sorted({k[0] for k in sweep_results})
    factors = sorted({k[1] for k in sweep_results})

    # DSR 用に全組の best SR を特定
    n_combos = len(sweep_results)
    all_aggs = {k: aggregate_results(v) for k, v in sweep_results.items()}

    best_sr = float("-inf")
    best_pnl_list: list[float] = []
    for agg in all_aggs.values():
        if agg["sharpe"] > best_sr and len(agg["pnl_list"]) >= 2:
            best_sr = agg["sharpe"]
            best_pnl_list = agg["pnl_list"]

    dsr_result = None
    significant_keys: set[tuple[int, float]] = set()
    if best_pnl_list:
        dsr_result = evaluate_dsr(best_pnl_list, N=n_combos)
        if dsr_result["significant"]:
            for k, agg in all_aggs.items():
                if len(agg["pnl_list"]) >= 2:
                    cell_dsr = evaluate_dsr(agg["pnl_list"], N=n_combos)
                    if cell_dsr["significant"]:
                        significant_keys.add(k)

    # ヘッダー
    header = f"{'':>12s}" + "".join(f"  f={f:.1f}" for f in factors)
    print(header)
    print("-" * len(header))

    for hold in holds:
        row = f"  hold={hold:3d}s "
        for factor in factors:
            key = (hold, factor)
            agg = all_aggs.get(key)
            if agg is None or agg["total_trips"] == 0:
                row += "     N/A"
                continue
            val = agg[metric]
            mark = " *" if key == (180, 0.4) else ""
            sig = " \u2713" if key in significant_keys else ""
            row += f"  {val:+6.2f}{mark}{sig}"
        print(row)

    # DSR サマリー
    if dsr_result:
        print()
        print(f"  {format_dsr_line(dsr=dsr_result['dsr'], N=dsr_result['N'], T=dsr_result['T'], sr_best=dsr_result['sr_best'], significant=dsr_result['significant'])}")
    print(f"\n  * = 現行値 (min_hold=180, factor=0.4)")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest scripts/backtester/test_close_fill_sim.py::TestAggregateResults -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/backtester/close_fill_sim.py scripts/backtester/test_close_fill_sim.py
git commit -m "feat: aggregate_results + print_sweep_grid with DSR"
```

---

### Task 6: run_analysis.py に close_fill モード追加

**Files:**
- Modify: `scripts/backtester/run_analysis.py:20-53` (imports)
- Modify: `scripts/backtester/run_analysis.py:627-691` (main, analysis choices, dispatch)

- [ ] **Step 1: Add import**

`run_analysis.py` の import セクション (line 52 付近) に追加:

```python
from backtester.close_fill_sim import (  # noqa: E402
    print_sweep_grid,
    run_close_fill_sweep,
)
```

- [ ] **Step 2: Add analysis_close_fill function**

`analysis_min_hold` の直後 (line 492 付近) に追加:

```python
def analysis_close_fill(trades, metrics, trips, timeline, min_holds_str: str | None, factors_str: str | None):
    """close fill 確率シミュレーション + パラメータスイープ。"""
    print("\n=== close_fill シミュレーション ===")
    matched = [t for t in trips if t.close_fill is not None]
    if not matched:
        print("  トリップデータなし")
        return

    min_holds = (
        [int(x) for x in min_holds_str.split(",")]
        if min_holds_str else None
    )
    factors = (
        [float(x) for x in factors_str.split(",")]
        if factors_str else None
    )

    sweep = run_close_fill_sweep(
        trips=matched, timeline=timeline,
        min_holds=min_holds, factors=factors,
    )

    print("\n--- P&L/trip グリッド ---")
    print_sweep_grid(sweep, metric="pnl_per_trip")

    print("\n--- Win率 グリッド ---")
    print_sweep_grid(sweep, metric="win_rate")

    print("\n--- SL率 グリッド ---")
    print_sweep_grid(sweep, metric="sl_rate")
```

- [ ] **Step 3: Add CLI arguments and dispatch**

argparse の `choices` に `"close_fill"` を追加 (line 633):

```python
    parser.add_argument(
        "--analysis",
        choices=["all", "hold_time", "time_filter", "ev_sim", "close_dynamics",
                 "market_hours", "vol_regime", "min_hold", "dvol_regime", "close_fill"],
        default="all",
        help="実行する分析",
    )
    parser.add_argument("--min-holds", type=str, default=None, help="close_fill: min_hold値 (カンマ区切り)")
    parser.add_argument("--factors", type=str, default=None, help="close_fill: factor値 (カンマ区切り)")
```

main() の末尾、dvol_regime ディスパッチの後に追加:

```python
    if args.analysis in ("all", "close_fill"):
        analysis_close_fill(trades, metrics, trips, timeline, args.min_holds, args.factors)
```

- [ ] **Step 4: Verify module loads without errors**

Run: `python -c "from backtester.close_fill_sim import run_close_fill_sweep, print_sweep_grid; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest scripts/backtester/test_close_fill_sim.py -v`
Expected: All tests pass (17 total)

- [ ] **Step 6: Commit**

```bash
git add scripts/backtester/run_analysis.py
git commit -m "feat: add close_fill analysis mode to run_analysis.py"
```

---

### Task 7: 実データ統合テスト

**Files:** None (実行のみ)

- [ ] **Step 1: 実データで close_fill 分析を実行**

Run: `cd /Users/okadasusumutakashi/Desktop/gmo-bot-conoha && python scripts/backtester/run_analysis.py --date 2026-04-08 --analysis close_fill`

Expected: P&L/trip グリッド + Win率グリッド + DSR が表示される。エラーなし。

- [ ] **Step 2: キャリブレーション検証**

グリッド内の (min_hold=180, factor=0.4) の P&L/trip を確認。
GMO 真値 (4/8 v0.14.2 = -120 JPY / ~30 trips ≈ -4.0/trip) と比較し、
+/-30% 以内に入っているか確認。

乖離が大きい場合 -> モデルパラメータを調整（別タスク）。

- [ ] **Step 3: 結果を記録してコミット**

結果のスクリーンショットまたはサマリーをハンドオフに記載する（別タスク）。
