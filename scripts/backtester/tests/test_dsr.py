"""DSR計算モジュールのテスト。"""
from backtester.dsr import (
    calc_pnl_stats,
    calc_sharpe_ratio,
    deflated_sharpe_ratio,
    evaluate_dsr,
    expected_max_sr,
    format_dsr_line,
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


def test_evaluate_dsr_returns_all_fields():
    """evaluate_dsrが必要な全フィールドを返す。"""
    pnl_list = [1.0, -0.5, 2.0, -1.0, 0.5, 1.5, -0.3, 0.8]
    result = evaluate_dsr(pnl_list, N=8)
    expected_keys = {"dsr", "sr_best", "N", "T", "skew", "kurt", "significant", "message"}
    assert set(result.keys()) == expected_keys


def test_evaluate_dsr_message_significant():
    """有意なとき、メッセージに '有意' が含まれる。"""
    pnl_list = [10.0] * 50 + [9.5] * 50
    result = evaluate_dsr(pnl_list, N=2)
    assert result["significant"] is True
    assert "有意" in result["message"]


def test_evaluate_dsr_message_not_significant():
    """有意でないとき、メッセージに '偶然' が含まれる。"""
    pnl_list = [0.1, -0.1, 0.05, -0.05, 0.02, -0.02]
    result = evaluate_dsr(pnl_list, N=100)
    assert result["significant"] is False
    assert "偶然" in result["message"]


def test_format_dsr_line():
    """format_dsr_lineが1行の文字列を返す。"""
    line = format_dsr_line(dsr=0.87, N=8, T=127, sr_best=0.42, significant=False)
    assert "DSR" in line
    assert "0.87" in line
    assert "N=8" in line


def test_format_dsr_line_significant():
    """significant=Trueのとき、有意な改善を表示する。"""
    line = format_dsr_line(dsr=0.98, N=4, T=200, sr_best=1.5, significant=True)
    assert "DSR" in line
    assert "0.98" in line
    assert "有意" in line
