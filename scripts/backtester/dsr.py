"""Deflated Sharpe Ratio (DSR) 計算モジュール。

Bailey & López de Prado (2014) に基づき、多重比較バイアスを補正した
Sharpe Ratio の統計的有意性を判定する。
"""
from __future__ import annotations

import math

from scipy.stats import norm

_EULER_MASCHERONI = 0.5772156649015329


def _sr_std(T: int, skew: float, kurt: float) -> float:
	"""SR推定量の標準偏差（non-normal補正付き）。"""
	if T <= 0:
		return 1.0
	radicand = (1.0 + 0.25 * kurt - skew * skew) / T
	if radicand <= 0:
		return 0.0
	return math.sqrt(radicand)


def expected_max_sr(
    N: int,
    T: int,
    skew: float = 0.0,
    kurt: float = 0.0,
) -> float:
    """N回の独立試行で偶然出る最大 Sharpe Ratio の期待値。

    N個の戦略を比較した場合に多重比較バイアスにより
    偶然生じる最大SRの期待値を返す。

    Args:
        N:    試行回数（比較パラメータ数）
        T:    観測数（trip数など）
        skew: P&L分布の歪度
        kurt: P&L分布の超過尖度

    Returns:
        E[max(SR)] — N回試行時に偶然期待される最大SR
    """
    if N <= 0:
        return 0.0
    if N == 1:
        return 0.0

    sr_std = _sr_std(T, skew, kurt)

    z_n = norm.ppf(1.0 - 1.0 / N)
    e_max_z = z_n + _EULER_MASCHERONI / z_n if z_n > 0 else 0.0

    return sr_std * e_max_z


def deflated_sharpe_ratio(
    sr_observed: float,
    N: int,
    T: int,
    skew: float = 0.0,
    kurt: float = 0.0,
) -> float:
    """Deflated Sharpe Ratio を計算。

    観測された最良SRが多重比較バイアスを超えて統計的に有意かどうかを
    確率値（0〜1）として返す。0.95以上なら有意水準5%で合格。

    Args:
        sr_observed: 観測されたベストの Sharpe Ratio（per-trip SR）
        N:           試行回数（比較パラメータ数）
        T:           サンプル数（trip数）
        skew:        P&L分布の歪度
        kurt:        P&L分布の超過尖度

    Returns:
        DSR値 (0〜1)。0.95以上なら統計的に有意。
    """
    if T <= 1 or N <= 0:
        return 0.0

    sr_benchmark = expected_max_sr(N, T, skew, kurt)

    sr_std = _sr_std(T, skew, kurt)

    if sr_std <= 0:
        return 0.0

    test_stat = (sr_observed - sr_benchmark) / sr_std

    return float(norm.cdf(test_stat))
