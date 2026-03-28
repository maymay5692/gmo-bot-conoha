"""DSR計算モジュールのテスト。"""
from backtester.dsr import (
    calc_pnl_stats,
    calc_sharpe_ratio,
    deflated_sharpe_ratio,
    expected_max_sr,
)


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


def test_calc_sharpe_ratio_positive():
    """正のP&Lリストから正のSRを返す。"""
    pnl_list = [1.0, 2.0, 1.5, 3.0, 0.5, 2.0, 1.0, 1.5]
    sr = calc_sharpe_ratio(pnl_list)
    assert sr > 0


def test_calc_sharpe_ratio_zero_variance():
    """全て同じ値 → SR = 0.0（ゼロ除算しない）。"""
    pnl_list = [1.0, 1.0, 1.0, 1.0]
    sr = calc_sharpe_ratio(pnl_list)
    assert sr == 0.0


def test_calc_sharpe_ratio_empty():
    """空リスト → SR = 0.0。"""
    sr = calc_sharpe_ratio([])
    assert sr == 0.0


def test_calc_sharpe_ratio_single_element():
    """1要素 → SR = 0.0。"""
    sr = calc_sharpe_ratio([5.0])
    assert sr == 0.0


def test_calc_sharpe_ratio_known_value():
    """既知の入力で期待するSR値を返す。"""
    pnl_list = [1.0, 2.0, 3.0]
    # mean=2.0, sample_std=1.0, SR=2.0
    sr = calc_sharpe_ratio(pnl_list)
    assert abs(sr - 2.0) < 1e-10


def test_calc_sharpe_ratio_negative():
    """負のP&Lリストから負のSRを返す。"""
    pnl_list = [-1.0, -2.0, -1.5, -3.0]
    sr = calc_sharpe_ratio(pnl_list)
    assert sr < 0


def test_calc_pnl_stats_empty():
    """空リスト → フォールバック辞書。"""
    result = calc_pnl_stats([])
    assert result == {"sr": 0.0, "T": 0, "skew": 0.0, "kurt": 0.0}


def test_calc_pnl_stats_single():
    """1要素 → T=1, sr=0.0。"""
    result = calc_pnl_stats([5.0])
    assert result["T"] == 1
    assert result["sr"] == 0.0


def test_calc_pnl_stats_returns_all_keys():
    """正常リストで全キーが存在する。"""
    pnl_list = [1.0, -0.5, 2.0, -1.0, 0.5, 1.5, -0.3, 0.8]
    result = calc_pnl_stats(pnl_list)
    assert set(result.keys()) == {"sr", "T", "skew", "kurt"}
    assert result["T"] == 8
    assert isinstance(result["sr"], float)
    assert isinstance(result["skew"], float)
    assert isinstance(result["kurt"], float)
