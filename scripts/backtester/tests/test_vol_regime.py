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
