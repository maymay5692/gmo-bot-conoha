"""クローズ約定シミュレーターモジュール。

Rust botのclose注文価格計算とブラウン運動マイクロフィルモデルを
Python で再現し、what-if分析の基盤を提供する。

主要コンポーネント:
  SimResult              - シミュレーション結果を保持する不変データクラス
  calc_close_price       - Rust bot と同一のclose価格計算
  calc_fill_prob         - ブラウン運動近似による3秒以内の約定確率
  simulate_single_trip   - 1トリップの期待値モードclose fillシミュレーション
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import timedelta
from math import sqrt

from scipy.stats import norm as _norm

from .data_loader import Trip
from .market_replay import MarketState


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


# ---------------------------------------------------------------------------
# _timeout_result
# ---------------------------------------------------------------------------

def _timeout_result(
    trip_index: int,
    min_hold_s: int,
    factor: float,
    pnl: float,
    hold_s: float,
    delay_s: float,
    p_timeout: float,
) -> SimResult:
    """タイムライン空または到達確率ゼロのとき timeout SimResult を返す。"""
    return SimResult(
        trip_index=trip_index,
        min_hold_s=min_hold_s,
        factor=factor,
        simulated_pnl=pnl,
        dominant_outcome="timeout",
        p_fill=0.0,
        p_sl=0.0,
        p_timeout=p_timeout,
        simulated_hold_s=hold_s,
        close_delay_s=delay_s,
        weighted_fill_price=0.0,
    )


# ---------------------------------------------------------------------------
# simulate_single_trip
# ---------------------------------------------------------------------------

def simulate_single_trip(
    trip: Trip,
    trip_index: int,
    timeline: list[MarketState],
    min_hold_s: int,
    close_spread_factor: float,
    stop_loss_jpy: float = 15.0,
    position_penalty: float = 50.0,
) -> SimResult:
    """1トリップの close fill を期待値モード（確定的）でシミュレーションする。

    タイムライン内の各tickで SL判定 → close注文価格/約定確率を計算し、
    生存確率 p_survive を消費しながら期待PnLを累積する。

    Args:
        trip:                実際のトリップ（open_fill のメタデータを使用）
        trip_index:          出力 SimResult に埋め込むインデックス
        timeline:            市場状態タイムライン（時刻昇順）
        min_hold_s:          オープン後このsecond数はclose注文を出さない
        close_spread_factor: calc_close_price に渡す factor
        stop_loss_jpy:       SLしきい値 (JPY、デフォルト15.0)
        position_penalty:    calc_close_price に渡すポジションペナルティ

    Returns:
        SimResult (frozen dataclass)
    """
    open_fill = trip.open_fill
    open_ts = open_fill.timestamp
    open_price = open_fill.price
    spread_pct = open_fill.spread_pct
    direction = 1 if open_fill.side == "BUY" else -1
    size = 0.001

    min_hold_end = open_ts + timedelta(seconds=min_hold_s)

    # タイムラインが空なら即 timeout
    if not timeline:
        return _timeout_result(
            trip_index=trip_index, min_hold_s=min_hold_s, factor=close_spread_factor,
            pnl=0.0, hold_s=0.0, delay_s=0.0, p_timeout=1.0,
        )

    # open_ts より後の最初のインデックスを bisect で特定
    timestamps = [ms.timestamp for ms in timeline]
    start_idx = bisect.bisect_right(timestamps, open_ts)

    p_survive = 1.0
    p_fill_total = 0.0
    p_sl_total = 0.0
    expected_pnl = 0.0
    weighted_fill_price_sum = 0.0

    # SLが発動したtickのタイムスタンプ（simulated_hold_s算出用）
    sl_tick_ts = None
    # close phaseで最初にfillできたtickのタイムスタンプ（close_delay_s算出用）
    first_fill_ts = None

    last_mid = open_price  # タイムアウト時のfallback

    for i in range(start_idx, len(timeline)):
        tick = timeline[i]
        last_mid = tick.mid_price

        # --- SL check ---
        unrealized = (tick.mid_price - open_price) * size * direction
        if unrealized < -stop_loss_jpy:
            # SL発動: 生存確率を全てSLに割り当て
            p_sl_total += p_survive
            expected_pnl += p_survive * unrealized
            if sl_tick_ts is None:
                sl_tick_ts = tick.timestamp
            p_survive = 0.0
            break

        # --- ホールドフェーズ: min_hold_end 前はclose注文しない ---
        if tick.timestamp < min_hold_end:
            continue

        # --- クローズフェーズ ---
        close_price = calc_close_price(
            mid=tick.mid_price,
            spread_pct=spread_pct,
            factor=close_spread_factor,
            direction=direction,
            position_penalty=position_penalty,
        )
        p_fill = calc_fill_prob(
            close_price=close_price,
            best_bid=tick.best_bid,
            best_ask=tick.best_ask,
            sigma_1s=tick.sigma_1s,
            mid=tick.mid_price,
            direction=direction,
        )

        fill_pnl = (close_price - open_price) * size * direction

        expected_pnl += p_survive * p_fill * fill_pnl
        p_fill_total += p_survive * p_fill
        weighted_fill_price_sum += p_survive * p_fill * close_price

        if first_fill_ts is None and p_fill > 0:
            first_fill_ts = tick.timestamp

        p_survive *= (1.0 - p_fill)

        if p_survive < 1e-9:
            p_survive = 0.0
            break

    # --- タイムアウト残余確率 ---
    p_timeout = p_survive
    if p_timeout > 0.0:
        terminal_pnl = (last_mid - open_price) * size * direction
        expected_pnl += p_timeout * terminal_pnl

    # --- dominant_outcome 判定 ---
    outcomes = {"fill": p_fill_total, "sl": p_sl_total, "timeout": p_timeout}
    dominant_outcome = max(outcomes, key=lambda k: outcomes[k])

    # --- hold時間・delay計算 ---
    if dominant_outcome == "sl" and sl_tick_ts is not None:
        simulated_hold_s = (sl_tick_ts - open_ts).total_seconds()
    elif dominant_outcome == "fill" and first_fill_ts is not None:
        simulated_hold_s = (first_fill_ts - open_ts).total_seconds()
    elif timeline:
        simulated_hold_s = (timeline[-1].timestamp - open_ts).total_seconds()
    else:
        simulated_hold_s = 0.0

    close_delay_s = max(0.0, simulated_hold_s - min_hold_s)

    weighted_fill_price = (
        weighted_fill_price_sum / p_fill_total if p_fill_total > 0.0 else 0.0
    )

    return SimResult(
        trip_index=trip_index,
        min_hold_s=min_hold_s,
        factor=close_spread_factor,
        simulated_pnl=expected_pnl,
        dominant_outcome=dominant_outcome,
        p_fill=p_fill_total,
        p_sl=p_sl_total,
        p_timeout=p_timeout,
        simulated_hold_s=simulated_hold_s,
        close_delay_s=close_delay_s,
        weighted_fill_price=weighted_fill_price,
    )
