"""ボラティリティレジーム分析モジュールのテスト。"""
from datetime import datetime, timezone

from backtester.data_loader import TradeEvent, Trip
from backtester.market_replay import MarketState
from backtester.vol_regime import analyze_by_vol_regime, classify_vol_regime


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
    assert "low" in result["boundaries"]
    assert "high" in result["boundaries"]
    assert len(result["labels"]) == 8


def test_classify_labels_correct():
    """パーセンタイルで正しくlow/mid/highに分類される。"""
    timeline = [
        _make_market_state(0, 100.0),
        _make_market_state(1, 200.0),
        _make_market_state(2, 400.0),
        _make_market_state(3, 500.0),
        _make_market_state(4, 600.0),
        _make_market_state(5, 700.0),
        _make_market_state(6, 900.0),
        _make_market_state(7, 1000.0),
    ]
    result = classify_vol_regime(timeline)
    labels = result["labels"]
    ts0 = timeline[0].timestamp
    ts7 = timeline[7].timestamp
    assert labels[ts0] == "low"
    assert labels[ts7] == "high"


def test_classify_empty_timeline():
    """空タイムライン → 空結果。"""
    result = classify_vol_regime([])
    assert result["boundaries"]["low"] == 0.0
    assert result["boundaries"]["high"] == 0.0
    assert len(result["labels"]) == 0


def test_classify_uniform_volatility():
    """全volatility同一 → 全てmid。"""
    timeline = [_make_market_state(h, 500.0) for h in range(8)]
    result = classify_vol_regime(timeline)
    for label in result["labels"].values():
        assert label == "mid"


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
        _make_trip(1, 2, pnl=3.0),
        _make_trip(3, 4, pnl=-2.0),
        _make_trip(6, 7, pnl=-8.0),
    ]

    rows = analyze_by_vol_regime(trips, regime_result, timeline)

    regime_names = [r["regime"] for r in rows]
    assert "low" in regime_names
    assert "mid" in regime_names
    assert "high" in regime_names

    low_row = next(r for r in rows if r["regime"] == "low")
    assert low_row["count"] == 2
    assert abs(low_row["pnl_sum"] - 8.0) < 0.01

    high_row = next(r for r in rows if r["regime"] == "high")
    assert high_row["count"] == 1
    assert abs(high_row["pnl_sum"] - (-8.0)) < 0.01


def test_analyze_by_vol_regime_empty_trips():
    """トリップ0件 → 空結果。"""
    timeline = [_make_market_state(0, 500.0)]
    regime_result = classify_vol_regime(timeline)
    rows = analyze_by_vol_regime([], regime_result, timeline)
    assert len(rows) == 0
