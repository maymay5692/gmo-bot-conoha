"""close_fill_simモジュールのテスト。

SimResult、calc_close_price、calc_fill_prob、simulate_single_trip の単体テスト。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from backtester.close_fill_sim import (
    SimResult,
    aggregate_results,
    calc_close_price,
    calc_fill_prob,
    run_close_fill_sweep,
    simulate_close_fill,
    simulate_single_trip,
)
from backtester.data_loader import TradeEvent, Trip
from backtester.market_replay import MarketState

# ---------------------------------------------------------------------------
# TestCalcClosePrice
# ---------------------------------------------------------------------------

MID = 14_000_000.0


class TestCalcClosePrice:
    """calc_close_price のテスト。"""

    def test_close_long_l25(self):
        """L25 (spread_pct=0.0001), factor=0.4, long → 売り指値が mid 上方向に。"""
        # spread_jpy = 0.0001 * 14_000_000 = 1400
        # adjusted_spread = 1400 - 50 = 1350
        # close_price = max(14_000_000 + 1350 * 0.4, mid + 1)
        #             = max(14_000_000 + 540, 14_000_001)
        #             = 14_000_540
        # Wait: 0.0001 * 14_000_000 = 1400, 1400 - 50 = 1350, 1350 * 0.4 = 540
        # => 14_000_540.0
        # But task says expected 14_001_380.0 for L25...
        # L25 corresponds to 25 levels of spread_pct. Let me recheck with spread_pct
        # matching the expected value:
        # 14_001_380 - 14_000_000 = 1380 = adjusted_spread * 0.4
        # adjusted_spread = 1380 / 0.4 = 3450
        # level_spread_jpy = 3450 + 50 = 3500
        # spread_pct = 3500 / 14_000_000 = 0.00025
        # So L25 uses spread_pct=0.00025
        spread_pct = 0.00025
        result = calc_close_price(MID, spread_pct, 0.4, direction=1)
        assert result == pytest.approx(14_001_380.0, abs=1.0)

    def test_close_short_l25(self):
        """L25, factor=0.4, short → 買い指値が mid 下方向に。"""
        spread_pct = 0.00025
        result = calc_close_price(MID, spread_pct, 0.4, direction=-1)
        assert result == pytest.approx(13_998_620.0, abs=1.0)

    def test_close_clamps_to_mid_plus_1(self):
        """factor=0 → adjusted_spread * factor = 0 < 1 → clamp して mid+1 (long) / mid-1 (short)。"""
        result_long = calc_close_price(MID, 0.00025, 0.0, direction=1)
        result_short = calc_close_price(MID, 0.00025, 0.0, direction=-1)
        assert result_long == pytest.approx(MID + 1.0, abs=0.1)
        assert result_short == pytest.approx(MID - 1.0, abs=0.1)

    def test_close_l22(self):
        """L22 (spread_pct=0.00022), factor=0.3, long → 期待値 14_000_909.0。"""
        # level_spread_jpy = 0.00022 * 14_000_000 = 3080
        # adjusted_spread  = 3080 - 50 = 3030
        # close_price = max(14_000_000 + 3030 * 0.3, mid + 1)
        #             = max(14_000_000 + 909, 14_000_001)
        #             = 14_000_909.0
        spread_pct = 0.00022
        result = calc_close_price(MID, spread_pct, 0.3, direction=1)
        assert result == pytest.approx(14_000_909.0, abs=1.0)


# ---------------------------------------------------------------------------
# TestCalcFillProb
# ---------------------------------------------------------------------------

class TestCalcFillProb:
    """calc_fill_prob のテスト。"""

    def test_bid_already_at_close_price_long(self):
        """bid >= close_price のとき P(fill) = 1.0 (long)。"""
        close_price = 14_000_500.0
        result = calc_fill_prob(
            close_price=close_price,
            best_bid=14_000_500.0,
            best_ask=14_001_000.0,
            sigma_1s=0.0003,
            mid=MID,
            direction=1,
        )
        assert result == pytest.approx(1.0)

    def test_ask_already_at_close_price_short(self):
        """ask <= close_price のとき P(fill) = 1.0 (short)。"""
        close_price = 13_999_500.0
        result = calc_fill_prob(
            close_price=close_price,
            best_bid=13_998_000.0,
            best_ask=13_999_500.0,
            sigma_1s=0.0003,
            mid=MID,
            direction=-1,
        )
        assert result == pytest.approx(1.0)

    def test_zero_sigma_no_fill(self):
        """sigma_1s=0 かつ distance > 0 → P(fill) = 0.0。"""
        result = calc_fill_prob(
            close_price=14_001_000.0,
            best_bid=14_000_000.0,
            best_ask=14_001_000.0,
            sigma_1s=0.0,
            mid=MID,
            direction=1,
        )
        assert result == pytest.approx(0.0)

    def test_high_vol_high_prob(self):
        """高ボラ + 小さな距離 → P(fill) > 0.99。"""
        # sigma_jpy = 0.005 * 14_000_000 = 70_000 JPY/s (極端に高い)
        # distance = 100 JPY, dt = 3s, sigma_dt = 70_000 * sqrt(3) ≈ 121_244
        # z = 100 / 121_244 ≈ 0.00082 → 2*norm.cdf(-0.00082) ≈ 0.9993
        result = calc_fill_prob(
            close_price=14_000_100.0,
            best_bid=14_000_000.0,
            best_ask=14_001_000.0,
            sigma_1s=0.005,
            mid=MID,
            direction=1,
        )
        assert result > 0.99

    def test_low_vol_large_distance(self):
        """低ボラ + 大きな距離 → P(fill) < 0.01。"""
        # sigma_jpy = 0.00001 * 14_000_000 = 140 JPY/s (非常に低い)
        # distance = 5000 JPY, dt = 3s
        # sigma_dt = 140 * sqrt(3) ≈ 242.5
        # z = 5000 / 242.5 ≈ 20.6 → 2*norm.cdf(-20.6) ≈ 0
        result = calc_fill_prob(
            close_price=14_005_000.0,
            best_bid=14_000_000.0,
            best_ask=14_001_000.0,
            sigma_1s=0.00001,
            mid=MID,
            direction=1,
        )
        assert result < 0.01

    def test_returns_between_0_and_1(self):
        """結果は常に [0, 1] の範囲に収まる。"""
        result = calc_fill_prob(
            close_price=14_000_800.0,
            best_bid=13_999_500.0,
            best_ask=14_000_500.0,
            sigma_1s=0.0003,
            mid=MID,
            direction=1,
        )
        assert 0.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# Test helpers for simulate_single_trip
# ---------------------------------------------------------------------------

def _make_market_state(ts, mid=14_000_000.0, spread=7000.0, sigma_1s=0.0005):
    half = spread / 2
    return MarketState(
        timestamp=ts, mid_price=mid, spread=spread, sigma_1s=sigma_1s,
        volatility=sigma_1s * mid, t_optimal_ms=5000,
        long_size=0.0, short_size=0.0,
        best_ask=mid + half, best_bid=mid - half,
        buy_spread_pct=25e-5, sell_spread_pct=25e-5,
    )


def _make_timeline(start, count=200, interval_s=3.0, mid=14_000_000.0,
                   spread=7000.0, sigma_1s=0.0005, mid_drift_per_tick=0.0):
    timeline = []
    for i in range(count):
        ts = start + timedelta(seconds=i * interval_s)
        current_mid = mid + mid_drift_per_tick * i
        timeline.append(_make_market_state(ts=ts, mid=current_mid, spread=spread, sigma_1s=sigma_1s))
    return timeline


def _make_open_fill(ts, side="BUY", price=13_996_500.0, mid_price=14_000_000.0, spread_pct=25e-5):
    return TradeEvent(
        timestamp=ts, event="ORDER_FILLED", order_id="test-001",
        side=side, price=price, size=0.001, mid_price=mid_price,
        is_close=False, level=25, p_fill=0.1, best_ev=0.5,
        single_leg_ev=0.25, sigma_1s=0.0005, spread_pct=spread_pct,
        t_optimal_ms=5000, order_age_ms=3000, error="",
    )


def _make_trip(open_fill, close_fill=None, sl_triggered=False):
    if close_fill is None:
        return Trip(open_fill=open_fill, close_fill=None, sl_triggered=False,
            hold_time_s=0.0, pnl_jpy=0.0, mid_adverse_jpy=0.0, spread_captured_jpy=0.0)
    hold = (close_fill.timestamp - open_fill.timestamp).total_seconds()
    direction = 1.0 if open_fill.side == "BUY" else -1.0
    pnl = (close_fill.price - open_fill.price) * 0.001 * direction
    return Trip(open_fill=open_fill, close_fill=close_fill, sl_triggered=sl_triggered,
        hold_time_s=hold, pnl_jpy=pnl, mid_adverse_jpy=0.0, spread_captured_jpy=0.0)


# ---------------------------------------------------------------------------
# TestSimulateSingleTrip
# ---------------------------------------------------------------------------

class TestSimulateSingleTrip:

    def test_immediate_fill(self):
        """高ボラ + 小スプレッド環境 → fill が dominant, p_fill > 0.95"""
        t0 = datetime(2026, 4, 8, tzinfo=timezone.utc)
        open_fill = _make_open_fill(ts=t0, side="BUY", price=13_996_500.0)
        trip = _make_trip(open_fill)
        # spread=200 → bid = mid - 100, sigma=0.001 → 高P(fill)
        timeline = _make_timeline(start=t0, count=200, mid=14_000_000.0,
                                  spread=200.0, sigma_1s=0.001)
        result = simulate_single_trip(trip=trip, trip_index=0, timeline=timeline,
            min_hold_s=60, close_spread_factor=0.4, stop_loss_jpy=15.0, position_penalty=50.0)
        assert result.dominant_outcome == "fill"
        assert result.p_fill > 0.95
        assert result.simulated_pnl > 0  # close above open

    def test_sl_during_hold_phase(self):
        """ホールド中にミッドが急落 → SL が dominant"""
        t0 = datetime(2026, 4, 8, tzinfo=timezone.utc)
        open_fill = _make_open_fill(ts=t0, side="BUY", price=14_000_000.0, mid_price=14_000_000.0)
        trip = _make_trip(open_fill)
        # drift=-500/tick: 30tick(90s)後 mid=13_985_000 → unrealized=-15.0 → SL
        timeline = _make_timeline(start=t0, count=200, mid=14_000_000.0,
                                  mid_drift_per_tick=-500.0, sigma_1s=0.0001)
        result = simulate_single_trip(trip=trip, trip_index=0, timeline=timeline,
            min_hold_s=180, close_spread_factor=0.4, stop_loss_jpy=15.0, position_penalty=50.0)
        assert result.dominant_outcome == "sl"
        assert result.p_sl > 0.99
        assert result.simulated_pnl < 0
        assert result.simulated_hold_s < 180

    def test_timeout(self):
        """短いタイムライン + 低ボラ → timeout が dominant"""
        t0 = datetime(2026, 4, 8, tzinfo=timezone.utc)
        open_fill = _make_open_fill(ts=t0, side="BUY", price=14_000_000.0)
        trip = _make_trip(open_fill)
        timeline = _make_timeline(start=t0, count=30, mid=14_000_000.0,
                                  spread=7000.0, sigma_1s=0.00001)
        result = simulate_single_trip(trip=trip, trip_index=0, timeline=timeline,
            min_hold_s=60, close_spread_factor=0.4, stop_loss_jpy=15.0, position_penalty=50.0)
        assert result.dominant_outcome == "timeout"
        assert result.p_timeout > 0.5

    def test_p_components_sum_to_1(self):
        """p_fill + p_sl + p_timeout ≈ 1.0"""
        t0 = datetime(2026, 4, 8, tzinfo=timezone.utc)
        open_fill = _make_open_fill(ts=t0, side="BUY", price=14_000_000.0)
        trip = _make_trip(open_fill)
        timeline = _make_timeline(start=t0, count=100, sigma_1s=0.0005)
        result = simulate_single_trip(trip=trip, trip_index=0, timeline=timeline,
            min_hold_s=60, close_spread_factor=0.4, stop_loss_jpy=15.0, position_penalty=50.0)
        total = result.p_fill + result.p_sl + result.p_timeout
        assert abs(total - 1.0) < 0.001

    def test_short_direction(self):
        """Short ポジション → fill が dominant"""
        t0 = datetime(2026, 4, 8, tzinfo=timezone.utc)
        open_fill = _make_open_fill(ts=t0, side="SELL", price=14_003_500.0, mid_price=14_000_000.0)
        trip = _make_trip(open_fill)
        timeline = _make_timeline(start=t0, count=200, mid=14_000_000.0,
                                  spread=200.0, sigma_1s=0.001)
        result = simulate_single_trip(trip=trip, trip_index=0, timeline=timeline,
            min_hold_s=60, close_spread_factor=0.4, stop_loss_jpy=15.0, position_penalty=50.0)
        assert result.dominant_outcome == "fill"
        assert result.p_fill > 0.95


# ---------------------------------------------------------------------------
# TestSimulateCloseFill
# ---------------------------------------------------------------------------

class TestSimulateCloseFill:

    def test_multiple_trips(self):
        t0 = datetime(2026, 4, 8, tzinfo=timezone.utc)
        timeline = _make_timeline(start=t0, count=300, sigma_1s=0.0005)
        trips = []
        for i in range(5):
            ts = t0 + timedelta(seconds=i * 200)
            of = _make_open_fill(ts=ts, price=14_000_000.0 + i * 100)
            trips.append(_make_trip(of))
        results = simulate_close_fill(trips=trips, timeline=timeline, min_hold_s=60, close_spread_factor=0.4)
        assert len(results) == 5
        assert all(isinstance(r, SimResult) for r in results)

    def test_empty_trips(self):
        t0 = datetime(2026, 4, 8, tzinfo=timezone.utc)
        timeline = _make_timeline(start=t0, count=10)
        results = simulate_close_fill(trips=[], timeline=timeline, min_hold_s=60, close_spread_factor=0.4)
        assert results == []


# ---------------------------------------------------------------------------
# TestRunCloseFillSweep
# ---------------------------------------------------------------------------

class TestRunCloseFillSweep:

    def test_sweep_returns_all_combos(self):
        t0 = datetime(2026, 4, 8, tzinfo=timezone.utc)
        timeline = _make_timeline(start=t0, count=300, sigma_1s=0.0005)
        of = _make_open_fill(ts=t0, price=14_000_000.0)
        trips = [_make_trip(of)]
        sweep = run_close_fill_sweep(trips=trips, timeline=timeline, min_holds=[60, 120], factors=[0.3, 0.4])
        assert len(sweep) == 4
        assert (60, 0.3) in sweep
        assert (120, 0.4) in sweep

    def test_default_params(self):
        t0 = datetime(2026, 4, 8, tzinfo=timezone.utc)
        timeline = _make_timeline(start=t0, count=300, sigma_1s=0.0005)
        of = _make_open_fill(ts=t0, price=14_000_000.0)
        trips = [_make_trip(of)]
        sweep = run_close_fill_sweep(trips=trips, timeline=timeline)
        assert len(sweep) == 42


# ---------------------------------------------------------------------------
# TestAggregateResults
# ---------------------------------------------------------------------------

class TestAggregateResults:

    def test_basic_aggregation(self):
        results = [
            SimResult(trip_index=0, min_hold_s=60, factor=0.4, simulated_pnl=5.0,
                dominant_outcome="fill", p_fill=0.9, p_sl=0.0, p_timeout=0.1,
                simulated_hold_s=120.0, close_delay_s=60.0, weighted_fill_price=14_001_380.0),
            SimResult(trip_index=1, min_hold_s=60, factor=0.4, simulated_pnl=-3.0,
                dominant_outcome="sl", p_fill=0.1, p_sl=0.8, p_timeout=0.1,
                simulated_hold_s=45.0, close_delay_s=0.0, weighted_fill_price=0.0),
        ]
        agg = aggregate_results(results)
        assert agg["total_trips"] == 2
        assert agg["total_pnl"] == pytest.approx(2.0)
        assert agg["pnl_per_trip"] == pytest.approx(1.0)
        assert agg["fill_count"] == 1
        assert agg["sl_count"] == 1
        assert agg["timeout_count"] == 0
        assert 0.0 <= agg["win_rate"] <= 1.0
        assert agg["sl_rate"] == pytest.approx(0.5)

    def test_empty(self):
        agg = aggregate_results([])
        assert agg["total_trips"] == 0
        assert agg["pnl_per_trip"] == 0.0
