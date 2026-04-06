"""DVOLレジーム分析モジュールのテスト。"""
from datetime import datetime, timedelta, timezone

from backtester.dvol_regime import calc_dvol_zscore, classify_dvol_regime


def _make_dvol_data(
    n_hours: int,
    base_dvol: float = 50.0,
    spike_at: int = -1,
    spike_value: float = 80.0,
) -> list[dict]:
    """テスト用DVOLデータ生成。"""
    base = datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)
    records = []
    for i in range(n_hours):
        dvol = spike_value if i == spike_at else base_dvol + (i % 5) * 0.5
        records.append(
            {
                "timestamp": base + timedelta(hours=i),
                "open": dvol,
                "high": dvol + 0.5,
                "low": dvol - 0.5,
                "close": dvol,
            }
        )
    return records


def test_calc_dvol_zscore_basic():
    data = _make_dvol_data(48)
    result = calc_dvol_zscore(data, lookback_hours=24)
    assert len(result) > 0
    assert "z_score" in result[0]
    assert "dvol" in result[0]
    assert "timestamp" in result[0]


def test_calc_dvol_zscore_spike_detected():
    data = _make_dvol_data(48, base_dvol=50.0, spike_at=47, spike_value=80.0)
    result = calc_dvol_zscore(data, lookback_hours=24)
    last = result[-1]
    assert last["z_score"] > 2.0


def test_classify_dvol_regime_labels():
    data = _make_dvol_data(48, base_dvol=50.0, spike_at=47, spike_value=80.0)
    zscore_data = calc_dvol_zscore(data, lookback_hours=24)
    result = classify_dvol_regime(zscore_data)
    labels = result["labels"]
    assert len(labels) > 0
    spike_ts = data[47]["timestamp"]
    assert labels.get(spike_ts) == "high"
    normal_count = sum(1 for v in labels.values() if v == "normal")
    assert normal_count > 0


def test_classify_dvol_regime_stats():
    data = _make_dvol_data(48)
    zscore_data = calc_dvol_zscore(data, lookback_hours=24)
    result = classify_dvol_regime(zscore_data)
    assert "mean" in result["stats"]
    assert "std" in result["stats"]
