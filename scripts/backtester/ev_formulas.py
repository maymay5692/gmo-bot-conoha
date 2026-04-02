"""EV計算式群

現行のEV計算式と、Phase C検証用の候補式を集約。
decision_sim.py から呼び出される。
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# 現行式 (v0.13.3)
# single_leg_ev = P(fill) * (mid_price * level/100000 - volatility * alpha)
# ---------------------------------------------------------------------------

def current_formula(
    p_fill: float,
    mid_price: float,
    level: int,
    volatility: float,
    alpha: float = 0.7,
) -> float:
    """現行EV計算式。

    Args:
        p_fill:     注文ごとのP(fill) (0~1)
        mid_price:  現在のmid_price (JPY)
        level:      レベル番号 (22, 23, 24, 25)
        volatility: EWMA volatility (1秒あたりのJPY変動)
        alpha:      adverse factor (デフォルト0.7)

    Returns:
        single_leg_ev (JPY)
    """
    spread_jpy = mid_price * level * 1e-5
    adverse = volatility * alpha
    return p_fill * (spread_jpy - adverse)


# ---------------------------------------------------------------------------
# 候補式: sqrt(t_optimal)スケーリング版
# adverse = sigma_1s * sqrt(t_optimal_s) * alpha
# ---------------------------------------------------------------------------

def sqrt_t_formula(
    p_fill: float,
    mid_price: float,
    level: int,
    sigma_1s: float,
    t_optimal_ms: int,
    alpha: float = 0.7,
) -> float:
    """sqrt(t_optimal)スケーリング版EV計算式。

    adverse項を sqrt(t_optimal) でスケールし、
    保有時間が長いほど逆行リスクを大きく見積もる。

    注意: 廃止リストにある（t_opt ≠ hold_time なため）。
    比較用として残置。

    Args:
        sigma_1s:      1秒あたりのsigma (EWMA)
        t_optimal_ms:  t_optimal (ミリ秒)
    """
    spread_jpy = mid_price * level * 1e-5
    t_s = t_optimal_ms / 1000.0
    adverse = sigma_1s * math.sqrt(t_s) * alpha * mid_price
    return p_fill * (spread_jpy - adverse)


# ---------------------------------------------------------------------------
# 候補式: hold_time実測ベース版
# adverse = sigma_1s * sqrt(hold_time_s) * alpha * mid_price
# ---------------------------------------------------------------------------

def hold_time_formula(
    p_fill: float,
    mid_price: float,
    level: int,
    sigma_1s: float,
    hold_time_s: float,
    alpha: float = 0.7,
) -> float:
    """hold_time実測値を使ったEV計算式。

    バックテスト専用: 実際のhold_timeを逆行推定に使用。
    リアルタイムでは使用不可（hold_timeは事後情報）。

    Args:
        hold_time_s: 実際のopen→close保有時間（秒）
    """
    spread_jpy = mid_price * level * 1e-5
    adverse = sigma_1s * math.sqrt(max(hold_time_s, 1.0)) * alpha * mid_price
    return p_fill * (spread_jpy - adverse)


# ---------------------------------------------------------------------------
# 候補式: mean_reversion考慮版
# mean reversionが強い時間帯はadverseを割り引く
# ---------------------------------------------------------------------------

def mean_reversion_formula(
    p_fill: float,
    mid_price: float,
    level: int,
    volatility: float,
    alpha: float = 0.7,
    reversion_factor: float = 0.5,
    hold_time_s: float = 30.0,
    reversion_threshold_s: float = 600.0,
) -> float:
    """mean_reversion考慮版EV計算式。

    保有時間が長くなるほどmean reversionが期待できるとして
    adverse項を割り引く。

    Args:
        reversion_factor:       最大でどれだけadverseを割り引くか (0~1)
        hold_time_s:            現在の保有時間（秒）
        reversion_threshold_s:  この秒数でreversion_factorが最大に
    """
    spread_jpy = mid_price * level * 1e-5
    # 保有時間に応じたreversion割り引き (0~reversion_factor)
    discount = reversion_factor * min(1.0, hold_time_s / reversion_threshold_s)
    effective_alpha = alpha * (1.0 - discount)
    adverse = volatility * effective_alpha
    return p_fill * (spread_jpy - adverse)


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

def level_calc(level: int) -> float:
    """FloatingExp::calc() 相当。level → spread率変換。

    base=10, exp=-5, rate=level  →  10^(-5) * level
    例: level=22 → 0.00022
    """
    return 1e-5 * level


def recalc_single_leg_ev(
    p_fill: float,
    mid_price: float,
    level: int,
    volatility: float,
    alpha: float,
    sigma_1s: float = 0.0,
    t_optimal_ms: int = 0,
    use_sqrt_t: bool = False,
) -> float:
    """条件に応じて適切な計算式を選択。"""
    if use_sqrt_t and sigma_1s > 0 and t_optimal_ms > 0:
        return sqrt_t_formula(
            p_fill, mid_price, level, sigma_1s, t_optimal_ms, alpha,
        )
    return current_formula(p_fill, mid_price, level, volatility, alpha)


def find_best_level(
    p_fills: dict[int, float],
    mid_price: float,
    volatility: float,
    alpha: float,
    sigma_1s: float = 0.0,
    t_optimal_ms: int = 0,
    use_sqrt_t: bool = False,
) -> tuple[int, float]:
    """複数levelから最良EVのlevelを選択。

    Args:
        p_fills: {level: p_fill} のマップ

    Returns:
        (best_level, best_ev)
    """
    best_level = 0
    best_ev = float("-inf")
    for level, p_fill in p_fills.items():
        ev = recalc_single_leg_ev(
            p_fill, mid_price, level, volatility, alpha,
            sigma_1s, t_optimal_ms, use_sqrt_t,
        )
        if ev > best_ev:
            best_ev = ev
            best_level = level
    return best_level, best_ev


def calc_all_formulas(
    p_fill: float,
    mid_price: float,
    level: int,
    volatility: float,
    sigma_1s: float,
    t_optimal_ms: int,
    alpha: float = 0.7,
    hold_time_s: float = 30.0,
) -> dict[str, float]:
    """全EV計算式を一括計算して比較。"""
    return {
        "current": current_formula(p_fill, mid_price, level, volatility, alpha),
        "sqrt_t": sqrt_t_formula(p_fill, mid_price, level, sigma_1s, t_optimal_ms, alpha),
        "hold_time": hold_time_formula(p_fill, mid_price, level, sigma_1s, hold_time_s, alpha),
        "mean_reversion": mean_reversion_formula(
            p_fill, mid_price, level, volatility, alpha, hold_time_s=hold_time_s
        ),
    }
