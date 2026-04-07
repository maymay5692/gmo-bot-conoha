"""data_loader モジュールのテスト。"""
from datetime import datetime, timezone

from backtester.data_loader import (
    TradeEvent,
    _calc_trip_fields,
    _parse_sl_pnl,
)


def _make_event(
    event: str,
    side: str,
    price: float,
    is_close,
    error: str = "",
    ts_offset_s: int = 0,
) -> TradeEvent:
    base = datetime(2026, 4, 2, 0, 0, 0, tzinfo=timezone.utc)
    return TradeEvent(
        timestamp=base.replace(second=ts_offset_s),
        event=event,
        order_id="test",
        side=side,
        price=price,
        size=0.001,
        mid_price=price,
        is_close=is_close,
        level=25,
        p_fill=0.1,
        best_ev=1.0,
        single_leg_ev=0.5,
        sigma_1s=0.5,
        spread_pct=0.00025,
        t_optimal_ms=3000,
        order_age_ms=500,
        error=error,
    )


def test_parse_sl_pnl_negative():
    result = _parse_sl_pnl("unrealized_pnl=-17.469")
    assert abs(result - (-17.469)) < 0.001


def test_parse_sl_pnl_positive():
    result = _parse_sl_pnl("unrealized_pnl=5.5")
    assert abs(result - 5.5) < 0.001


def test_parse_sl_pnl_with_extra_text():
    result = _parse_sl_pnl("[ApiError] something unrealized_pnl=-22.5 more")
    assert abs(result - (-22.5)) < 0.001


def test_parse_sl_pnl_empty():
    assert _parse_sl_pnl("") == 0.0


def test_parse_sl_pnl_no_field():
    assert _parse_sl_pnl("some other error") == 0.0


def test_parse_sl_pnl_malformed():
    assert _parse_sl_pnl("unrealized_pnl=NaN_text") == 0.0


def test_calc_trip_fields_normal_close_uses_price_diff():
    open_fill = _make_event("ORDER_FILLED", "BUY", 10000000, False, ts_offset_s=0)
    close_fill = _make_event("ORDER_FILLED", "SELL", 10005000, True, ts_offset_s=10)
    trip = _calc_trip_fields(open_fill, close_fill, sl_triggered=False)
    assert abs(trip.pnl_jpy - 5.0) < 0.001


def test_calc_trip_fields_sl_uses_unrealized_pnl():
    open_fill = _make_event("ORDER_FILLED", "BUY", 10000000, False, ts_offset_s=0)
    sl_close = _make_event(
        "STOP_LOSS_TRIGGERED", "SELL", 9999999, True,
        error="unrealized_pnl=-17.469", ts_offset_s=20,
    )
    trip = _calc_trip_fields(open_fill, sl_close, sl_triggered=True)
    assert abs(trip.pnl_jpy - (-17.469)) < 0.001


def test_calc_trip_fields_sl_no_unrealized_pnl_returns_zero():
    open_fill = _make_event("ORDER_FILLED", "BUY", 10000000, False, ts_offset_s=0)
    sl_close = _make_event(
        "STOP_LOSS_TRIGGERED", "SELL", 9999999, True,
        error="", ts_offset_s=20,
    )
    trip = _calc_trip_fields(open_fill, sl_close, sl_triggered=True)
    assert trip.pnl_jpy == 0.0
