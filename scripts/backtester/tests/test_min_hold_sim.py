"""min_holdシミュレーションのテスト。"""
from datetime import datetime, timedelta, timezone

from backtester.data_loader import TradeEvent, Trip
from backtester.market_replay import MarketState
from backtester.min_hold_sim import simulate_min_hold


def _make_market_state(ts_sec: int, mid_price: float, volatility: float = 500.0) -> MarketState:
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


def _make_trade_event(ts_sec: int, price: float = 13000000.0, mid_price: float = 13000000.0, side: str = "BUY", is_close: bool = False) -> TradeEvent:
    base = datetime(2026, 2, 27, 0, 0, 0, tzinfo=timezone.utc)
    return TradeEvent(
        timestamp=base + timedelta(seconds=ts_sec),
        event="ORDER_FILLED", order_id="test", side=side, price=price, size=0.001,
        mid_price=mid_price, is_close=is_close, level=25, p_fill=0.1, best_ev=1.0,
        single_leg_ev=0.5, sigma_1s=0.5, spread_pct=0.00025, t_optimal_ms=3000,
        order_age_ms=500, error="",
    )


def _make_trip(open_sec: int, close_sec: int, pnl: float, spread: float = 3.0) -> Trip:
    open_fill = _make_trade_event(open_sec, mid_price=13000000.0)
    close_fill = _make_trade_event(close_sec, price=13000000.0 + pnl / 0.001, mid_price=13000000.0 + pnl / 0.001 - spread / 0.001, is_close=True)
    return Trip(
        open_fill=open_fill, close_fill=close_fill, sl_triggered=False,
        hold_time_s=float(close_sec - open_sec), pnl_jpy=pnl,
        mid_adverse_jpy=-2.0, spread_captured_jpy=spread,
    )


def test_simulate_min_hold_no_effect():
    """全tripがmin_hold以上 → 影響なし。"""
    timeline = [_make_market_state(s, 13000000.0) for s in range(0, 601, 3)]
    trips = [_make_trip(0, 200, pnl=-5.0), _make_trip(300, 500, pnl=3.0)]
    result = simulate_min_hold(trips, timeline, min_hold_s=60.0)
    assert result["affected_trips"] == 0
    assert abs(result["original_pnl_sum"] - (-2.0)) < 0.01
    assert abs(result["simulated_pnl_sum"] - (-2.0)) < 0.01
    assert len(result["simulated_pnl_list"]) == 2


def test_simulate_min_hold_affects_short_trip():
    """hold_time < min_holdのtripが再評価される。"""
    timeline = [
        _make_market_state(0, 13000000.0),
        _make_market_state(3, 12999500.0),
        _make_market_state(10, 12999000.0),
        _make_market_state(60, 12999800.0),
        _make_market_state(120, 13000500.0),
        _make_market_state(180, 13000200.0),
    ]
    trips = [_make_trip(0, 10, pnl=-1.0, spread=3.0)]
    result = simulate_min_hold(trips, timeline, min_hold_s=120.0)
    assert result["affected_trips"] == 1
    assert result["simulated_pnl_sum"] > result["original_pnl_sum"]
    assert len(result["simulated_pnl_list"]) == 1


def test_simulate_min_hold_empty_trips():
    """空tripリスト → ゼロ結果。"""
    timeline = [_make_market_state(0, 13000000.0)]
    result = simulate_min_hold([], timeline, min_hold_s=60.0)
    assert result["total_trips"] == 0
    assert result["simulated_pnl_list"] == []
