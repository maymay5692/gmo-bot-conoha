"""クローズ約定シミュレーターモジュール。

Rust botのclose注文価格計算とブラウン運動マイクロフィルモデルを
Python で再現し、what-if分析の基盤を提供する。

主要コンポーネント:
  SimResult         - シミュレーション結果を保持する不変データクラス
  calc_close_price  - Rust bot と同一のclose価格計算
  calc_fill_prob    - ブラウン運動近似による3秒以内の約定確率
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from scipy.stats import norm as _norm


# ---------------------------------------------------------------------------
# SimResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SimResult:
    """1トリップのclose fill シミュレーション結果。

    frozen=True で不変保証。
    """
    trip_index: int
    min_hold_s: int
    factor: float
    simulated_pnl: float
    dominant_outcome: str       # "fill" | "sl" | "timeout"
    p_fill: float
    p_sl: float
    p_timeout: float
    simulated_hold_s: float
    close_delay_s: float
    weighted_fill_price: float


# ---------------------------------------------------------------------------
# calc_close_price
# ---------------------------------------------------------------------------

def calc_close_price(
    mid: float,
    spread_pct: float,
    factor: float,
    direction: int,
    position_penalty: float = 50.0,
) -> float:
    """Rust bot のclose価格計算を再現する。

    spread_pct × mid でレベルスプレッド(JPY)を算出し、
    position_penalty を差し引いた adjusted_spread に factor を乗じた額を
    mid から外側にオフセットした指値を返す。

    方向性下限として mid ± 1.0 にクランプする。

    Args:
        mid:              現在のmid価格 (JPY)
        spread_pct:       板レベルのスプレッド率
        factor:           close_spread_factor (例: 0.4)
        direction:        1 = long (SELL limit), -1 = short (BUY limit)
        position_penalty: ポジション保有コスト補正 (JPY, デフォルト50.0)

    Returns:
        close指値価格 (JPY)
    """
    level_spread_jpy = spread_pct * mid
    adjusted_spread = level_spread_jpy - position_penalty

    if direction == 1:  # long → SELL limit
        return max(mid + adjusted_spread * factor, mid + 1.0)
    else:               # short → BUY limit
        return min(mid - adjusted_spread * factor, mid - 1.0)


# ---------------------------------------------------------------------------
# calc_fill_prob
# ---------------------------------------------------------------------------

def calc_fill_prob(
    close_price: float,
    best_bid: float,
    best_ask: float,
    sigma_1s: float,
    mid: float,
    direction: int,
    dt: float = 3.0,
) -> float:
    """ブラウン運動近似による dt 秒以内の約定確率を返す。

    価格が指値に到達する確率をガウス分布の両裾で近似する。
    既に最良気配が指値以内なら即時約定 (1.0) を返す。
    sigma_1s=0 かつ distance > 0 の場合は 0.0 を返す。

    Args:
        close_price: close指値価格 (JPY)
        best_bid:    現在のbest bid (JPY)
        best_ask:    現在のbest ask (JPY)
        sigma_1s:    1秒あたりの価格変動率 (sigma / mid)
        mid:         現在のmid価格 (JPY)
        direction:   1 = long (SELL limit) / -1 = short (BUY limit)
        dt:          評価時間窓 (秒, デフォルト3.0)

    Returns:
        約定確率 [0.0, 1.0]
    """
    if direction == 1:  # SELL limit → bid が close_price 以上で約定
        if best_bid >= close_price:
            return 1.0
        distance = close_price - best_bid
    else:               # BUY limit → ask が close_price 以下で約定
        if best_ask <= close_price:
            return 1.0
        distance = best_ask - close_price

    if distance <= 0:
        return 1.0

    sigma_jpy = sigma_1s * mid
    if sigma_jpy <= 0:
        return 0.0

    return float(2.0 * _norm.cdf(-distance / (sigma_jpy * sqrt(dt))))
