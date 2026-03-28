"""DSR計算モジュールのテスト。"""
from backtester.dsr import deflated_sharpe_ratio, expected_max_sr


def test_expected_max_sr_single_trial():
    """N=1のとき、期待最大SR ≈ 0（1回しか試していない）。"""
    result = expected_max_sr(N=1, T=100, skew=0.0, kurt=0.0)
    assert abs(result) < 0.1


def test_expected_max_sr_increases_with_n():
    """Nが増えるとexpected_max_srも増加する。"""
    sr_10 = expected_max_sr(N=10, T=100, skew=0.0, kurt=0.0)
    sr_100 = expected_max_sr(N=100, T=100, skew=0.0, kurt=0.0)
    assert sr_100 > sr_10 > 0


def test_expected_max_sr_known_value():
    """N=1000, T=1000, 正規分布のとき SR ≈ 0.1 前後（per-trip SR）。"""
    result = expected_max_sr(N=1000, T=1000, skew=0.0, kurt=0.0)
    assert 0.05 < result < 0.20


def test_dsr_high_sr_is_significant():
    """真に高いSRはDSR ≥ 0.95。"""
    result = deflated_sharpe_ratio(
        sr_observed=2.0, N=8, T=200, skew=0.0, kurt=0.0
    )
    assert result >= 0.95


def test_dsr_low_sr_is_not_significant():
    """偶然レベルのSRはDSR < 0.95。"""
    result = deflated_sharpe_ratio(
        sr_observed=0.3, N=100, T=50, skew=0.0, kurt=0.0
    )
    assert result < 0.95


def test_dsr_returns_between_0_and_1():
    """DSRは0〜1の範囲。"""
    result = deflated_sharpe_ratio(
        sr_observed=1.0, N=10, T=100, skew=0.0, kurt=0.0
    )
    assert 0.0 <= result <= 1.0


def test_dsr_more_trials_harder_to_pass():
    """Nが増えるとDSRは下がる（有意になりにくい）。"""
    dsr_10 = deflated_sharpe_ratio(
        sr_observed=1.0, N=10, T=100, skew=0.0, kurt=0.0
    )
    dsr_100 = deflated_sharpe_ratio(
        sr_observed=1.0, N=100, T=100, skew=0.0, kurt=0.0
    )
    assert dsr_10 > dsr_100


def test_extreme_skew_does_not_crash():
    """極端なskewでもクラッシュしない。"""
    result = deflated_sharpe_ratio(sr_observed=1.0, N=10, T=100, skew=5.0, kurt=0.0)
    assert 0.0 <= result <= 1.0
