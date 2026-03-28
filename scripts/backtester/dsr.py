"""Deflated Sharpe Ratio (DSR) 計算モジュール。

Bailey & López de Prado (2014) に基づき、多重比較バイアスを補正した
Sharpe Ratio の統計的有意性を判定する。
"""
from __future__ import annotations

import math

from scipy.stats import kurtosis as sp_kurtosis, norm, skew as sp_skew

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


def calc_sharpe_ratio(pnl_list: list[float]) -> float:
    """trip P&L リストから Sharpe Ratio を算出。

    年率化はせず、per-trip SR を返す。

    Args:
        pnl_list: tripごとのP&L (JPY) のリスト

    Returns:
        SR = mean / std。std=0 のとき 0.0。
    """
    if len(pnl_list) < 2:
        return 0.0

    mean = sum(pnl_list) / len(pnl_list)
    variance = sum((x - mean) ** 2 for x in pnl_list) / (len(pnl_list) - 1)
    std = math.sqrt(variance)

    if std == 0:
        return 0.0

    return mean / std


_DSR_THRESHOLD = 0.95


def evaluate_dsr(
    pnl_list: list[float],
    N: int,
    threshold: float = _DSR_THRESHOLD,
) -> dict[str, float | int | bool | str]:
    """P&Lリストと試行回数NからDSR評価を一括実行。

    Args:
        pnl_list: tripごとのP&L (JPY) のリスト
        N:        試行回数（比較パラメータ数）
        threshold: 有意判定閾値（デフォルト0.95）

    Returns:
        {
            "dsr": float,
            "sr_best": float,
            "N": int,
            "T": int,
            "skew": float,
            "kurt": float,
            "significant": bool,
            "message": str,
        }
    """
    stats = calc_pnl_stats(pnl_list)
    dsr = deflated_sharpe_ratio(
        sr_observed=stats["sr"],
        N=N,
        T=int(stats["T"]),
        skew=stats["skew"],
        kurt=stats["kurt"],
    )
    significant = dsr >= threshold

    if significant:
        message = f"統計的に有意な改善 (DSR={dsr:.2f} >= {threshold})"
    else:
        message = f"閾値{threshold}未満: この改善は偶然の可能性あり (DSR={dsr:.2f})"

    return {
        "dsr": dsr,
        "sr_best": stats["sr"],
        "N": N,
        "T": stats["T"],
        "skew": stats["skew"],
        "kurt": stats["kurt"],
        "significant": significant,
        "message": message,
    }


def format_dsr_line(
    dsr: float,
    N: int,
    T: int,
    sr_best: float,
    significant: bool,
    threshold: float = 0.95,
) -> str:
    """DSR結果を1行のフォーマット文字列で返す。"""
    mark = "\u2713" if significant else "\u26a0"
    if significant:
        detail = "統計的に有意な改善"
    else:
        detail = f"閾値{threshold}未満: この改善は偶然の可能性あり"
    return f"DSR: {dsr:.2f} (N={N}, T={T}, SR_best={sr_best:.2f}) \u2014 {mark} {detail}"


def calc_pnl_stats(pnl_list: list[float]) -> dict[str, float | int]:
    """P&Lリストから DSR に必要な統計量を一括算出。

    Args:
        pnl_list: tripごとのP&L (JPY) のリスト

    Returns:
        {"sr": float, "T": int, "skew": float, "kurt": float}
    """
    if len(pnl_list) < 2:
        return {"sr": 0.0, "T": len(pnl_list), "skew": 0.0, "kurt": 0.0}

    return {
        "sr": calc_sharpe_ratio(pnl_list),
        "T": len(pnl_list),
        "skew": float(sp_skew(pnl_list)),
        "kurt": float(sp_kurtosis(pnl_list, fisher=True)),
    }
