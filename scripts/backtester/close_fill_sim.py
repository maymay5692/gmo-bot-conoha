"""クローズ約定シミュレーターモジュール。

Rust botのclose注文価格計算と反事実close fillモデルを
Python で再現し、what-if分析の基盤を提供する。

主要コンポーネント:
  SimResult                    - シミュレーション結果を保持する不変データクラス
  calc_close_price             - Rust bot と同一のclose価格計算
  calc_fill_prob               - 決定的fill判定（bid/ask vs close_price）
  simulate_counterfactual_trip - 反事実モデルによる1トリップclose fillシミュレーション
  simulate_single_trip         - 期待値モード（後方互換、非推奨）
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import timedelta

from .data_loader import Trip
from .dsr import calc_sharpe_ratio, evaluate_dsr, format_dsr_line
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
    """決定的fill判定: 現在の気配が指値に到達しているか。

    Brownianモデル（旧）は実効fill rateを~130倍過大推定していたため、
    決定的判定（bid >= close_price なら1.0、そうでなければ0.0）に変更。

    Args:
        close_price: close指値価格 (JPY)
        best_bid:    現在のbest bid (JPY)
        best_ask:    現在のbest ask (JPY)
        sigma_1s:    未使用（後方互換のため残存）
        mid:         未使用（後方互換のため残存）
        direction:   1 = long (SELL limit) / -1 = short (BUY limit)
        dt:          未使用（後方互換のため残存）

    Returns:
        1.0 (fillable) or 0.0 (not fillable)
    """
    if direction == 1:  # SELL limit → bid が close_price 以上で約定
        return 1.0 if best_bid >= close_price else 0.0
    else:               # BUY limit → ask が close_price 以下で約定
        return 1.0 if best_ask <= close_price else 0.0


# ---------------------------------------------------------------------------
# _is_fillable
# ---------------------------------------------------------------------------

def _is_fillable(close_price: float, tick: MarketState, direction: int) -> bool:
    """決定的fill判定: この tick で close 注文が約定するか。"""
    if direction == 1:  # SELL limit → bid が close_price 以上
        return tick.best_bid >= close_price
    else:               # BUY limit → ask が close_price 以下
        return tick.best_ask <= close_price


# ---------------------------------------------------------------------------
# simulate_counterfactual_trip
# ---------------------------------------------------------------------------

def simulate_counterfactual_trip(
    trip: Trip,
    trip_index: int,
    timeline: list[MarketState],
    min_hold_s: int,
    close_spread_factor: float,
    stop_loss_jpy: float = 15.0,
    position_penalty: float = 50.0,
    max_sim_duration_s: float = 7200.0,
    baseline_min_hold_s: int = 180,
) -> SimResult:
    """反事実モデルによる1トリップのclose fillシミュレーション。

    実際のトリップ結果（fill/SL）をアンカーとして使用し、
    パラメータ変更時の P&L を決定的に計算する。

    Baseline (同一パラメータ): P&L は実績と完全一致。
    What-if (factor変更): close 価格変更による P&L 差分を計算。
    What-if (min_hold変更): timeline を full scan（SL 検出に既知のノイズあり）。

    Args:
        trip:                実際のトリップ
        trip_index:          出力に埋め込むインデックス
        timeline:            市場状態タイムライン（時刻昇順）
        min_hold_s:          close注文開始までの待機秒数
        close_spread_factor: calc_close_price に渡す factor
        stop_loss_jpy:       SLしきい値 (JPY)
        position_penalty:    calc_close_price に渡すポジションペナルティ
        max_sim_duration_s:  1トリップの最大シミュレーション時間 (秒)
        baseline_min_hold_s: 実 bot が使用した min_hold（アンカー判定用）

    Returns:
        SimResult (frozen dataclass)
    """
    open_fill = trip.open_fill
    open_ts = open_fill.timestamp
    open_price = open_fill.price
    spread_pct = open_fill.spread_pct
    direction = 1 if open_fill.side == "BUY" else -1
    size = 0.001

    if not timeline:
        return _timeout_result(
            trip_index=trip_index, min_hold_s=min_hold_s,
            factor=close_spread_factor, pnl=0.0,
            hold_s=0.0, delay_s=0.0, p_timeout=1.0,
        )

    # --- min_hold が baseline と同じならアンカーモード ---
    if min_hold_s == baseline_min_hold_s:
        return _counterfactual_anchored(
            trip=trip, trip_index=trip_index, timeline=timeline,
            min_hold_s=min_hold_s, close_spread_factor=close_spread_factor,
            stop_loss_jpy=stop_loss_jpy, position_penalty=position_penalty,
            max_sim_duration_s=max_sim_duration_s,
        )

    # --- min_hold が異なる場合は full scan ---
    return _counterfactual_full_scan(
        trip=trip, trip_index=trip_index, timeline=timeline,
        min_hold_s=min_hold_s, close_spread_factor=close_spread_factor,
        stop_loss_jpy=stop_loss_jpy, position_penalty=position_penalty,
        max_sim_duration_s=max_sim_duration_s,
    )


def _counterfactual_anchored(
    trip: Trip,
    trip_index: int,
    timeline: list[MarketState],
    min_hold_s: int,
    close_spread_factor: float,
    stop_loss_jpy: float,
    position_penalty: float,
    max_sim_duration_s: float,
) -> SimResult:
    """実トリップ結果をアンカーとした反事実計算（min_hold が同一の場合）。

    SL トリップ: 新 factor で SL 前に fill できたか timeline をスキャン。
                 fill できれば fill P&L、できなければ実 SL P&L。
    Fill トリップ: 実 fill 時刻の mid で新 close_price を計算して P&L を返す。
    """
    open_fill = trip.open_fill
    open_ts = open_fill.timestamp
    open_price = open_fill.price
    spread_pct = open_fill.spread_pct
    direction = 1 if open_fill.side == "BUY" else -1
    size = 0.001
    min_hold_end = open_ts + timedelta(seconds=min_hold_s)

    timestamps = [ms.timestamp for ms in timeline]

    if trip.sl_triggered:
        # --- SL トリップ: 新 factor で SL 前に fill できるか ---
        sl_ts = trip.close_fill.timestamp
        start_idx = bisect.bisect_right(timestamps, open_ts)

        for i in range(start_idx, len(timeline)):
            tick = timeline[i]
            if tick.timestamp > sl_ts:
                break
            if tick.timestamp < min_hold_end:
                continue

            close_price = calc_close_price(
                mid=tick.mid_price, spread_pct=spread_pct,
                factor=close_spread_factor, direction=direction,
                position_penalty=position_penalty,
            )
            if _is_fillable(close_price, tick, direction):
                fill_pnl = (close_price - open_price) * size * direction
                hold_s = (tick.timestamp - open_ts).total_seconds()
                return SimResult(
                    trip_index=trip_index, min_hold_s=min_hold_s,
                    factor=close_spread_factor, simulated_pnl=fill_pnl,
                    dominant_outcome="fill", p_fill=1.0, p_sl=0.0, p_timeout=0.0,
                    simulated_hold_s=hold_s,
                    close_delay_s=max(0.0, hold_s - min_hold_s),
                    weighted_fill_price=close_price,
                )

        # fill できなかった → 実 SL P&L を使用
        return SimResult(
            trip_index=trip_index, min_hold_s=min_hold_s,
            factor=close_spread_factor, simulated_pnl=trip.pnl_jpy,
            dominant_outcome="sl", p_fill=0.0, p_sl=1.0, p_timeout=0.0,
            simulated_hold_s=trip.hold_time_s,
            close_delay_s=max(0.0, trip.hold_time_s - min_hold_s),
            weighted_fill_price=0.0,
        )

    # --- Fill トリップ: 実 fill 時刻の mid で新 close_price を計算 ---
    close_fill = trip.close_fill
    if close_fill is None:
        # 未クローズ Trip → full scan にフォールバック
        return _counterfactual_full_scan(
            trip=trip, trip_index=trip_index, timeline=timeline,
            min_hold_s=min_hold_s, close_spread_factor=close_spread_factor,
            stop_loss_jpy=stop_loss_jpy, position_penalty=position_penalty,
            max_sim_duration_s=max_sim_duration_s,
        )
    close_mid = close_fill.mid_price

    new_close_price = calc_close_price(
        mid=close_mid, spread_pct=spread_pct,
        factor=close_spread_factor, direction=direction,
        position_penalty=position_penalty,
    )
    new_pnl = (new_close_price - open_price) * size * direction

    return SimResult(
        trip_index=trip_index, min_hold_s=min_hold_s,
        factor=close_spread_factor, simulated_pnl=new_pnl,
        dominant_outcome="fill", p_fill=1.0, p_sl=0.0, p_timeout=0.0,
        simulated_hold_s=trip.hold_time_s,
        close_delay_s=max(0.0, trip.hold_time_s - min_hold_s),
        weighted_fill_price=new_close_price,
    )


def _counterfactual_full_scan(
    trip: Trip,
    trip_index: int,
    timeline: list[MarketState],
    min_hold_s: int,
    close_spread_factor: float,
    stop_loss_jpy: float,
    position_penalty: float,
    max_sim_duration_s: float,
) -> SimResult:
    """full timeline scan（min_hold が baseline と異なる場合）。

    既知の制限: metrics mid の SL 検出は ±5 JPY のノイズあり。
    """
    open_fill = trip.open_fill
    open_ts = open_fill.timestamp
    open_price = open_fill.price
    spread_pct = open_fill.spread_pct
    direction = 1 if open_fill.side == "BUY" else -1
    size = 0.001

    min_hold_end = open_ts + timedelta(seconds=min_hold_s)
    max_end = open_ts + timedelta(seconds=max_sim_duration_s)

    timestamps = [ms.timestamp for ms in timeline]
    start_idx = bisect.bisect_right(timestamps, open_ts)

    last_mid = open_price

    for i in range(start_idx, len(timeline)):
        tick = timeline[i]
        if tick.timestamp > max_end:
            break
        last_mid = tick.mid_price

        # SL check
        unrealized = (tick.mid_price - open_price) * size * direction
        if unrealized < -stop_loss_jpy:
            hold_s = (tick.timestamp - open_ts).total_seconds()
            return SimResult(
                trip_index=trip_index, min_hold_s=min_hold_s,
                factor=close_spread_factor, simulated_pnl=unrealized,
                dominant_outcome="sl", p_fill=0.0, p_sl=1.0, p_timeout=0.0,
                simulated_hold_s=hold_s,
                close_delay_s=max(0.0, hold_s - min_hold_s),
                weighted_fill_price=0.0,
            )

        if tick.timestamp < min_hold_end:
            continue

        close_price = calc_close_price(
            mid=tick.mid_price, spread_pct=spread_pct,
            factor=close_spread_factor, direction=direction,
            position_penalty=position_penalty,
        )
        if _is_fillable(close_price, tick, direction):
            fill_pnl = (close_price - open_price) * size * direction
            hold_s = (tick.timestamp - open_ts).total_seconds()
            return SimResult(
                trip_index=trip_index, min_hold_s=min_hold_s,
                factor=close_spread_factor, simulated_pnl=fill_pnl,
                dominant_outcome="fill", p_fill=1.0, p_sl=0.0, p_timeout=0.0,
                simulated_hold_s=hold_s,
                close_delay_s=max(0.0, hold_s - min_hold_s),
                weighted_fill_price=close_price,
            )

    terminal_pnl = (last_mid - open_price) * size * direction
    hold_s = min(
        max_sim_duration_s,
        (timeline[-1].timestamp - open_ts).total_seconds(),
    )
    return _timeout_result(
        trip_index=trip_index, min_hold_s=min_hold_s,
        factor=close_spread_factor, pnl=terminal_pnl,
        hold_s=hold_s, delay_s=max(0.0, hold_s - min_hold_s),
        p_timeout=1.0,
    )


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
    fill_discount: float = 1.0,
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
        p_fill_raw = calc_fill_prob(
            close_price=close_price,
            best_bid=tick.best_bid,
            best_ask=tick.best_ask,
            sigma_1s=tick.sigma_1s,
            mid=tick.mid_price,
            direction=direction,
        )
        p_fill = p_fill_raw * fill_discount

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


# ---------------------------------------------------------------------------
# Default sweep parameters
# ---------------------------------------------------------------------------

_DEFAULT_MIN_HOLDS = [60, 90, 120, 180, 240, 300]
_DEFAULT_FACTORS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]


# ---------------------------------------------------------------------------
# simulate_close_fill
# ---------------------------------------------------------------------------

def simulate_close_fill(
    trips: list[Trip],
    timeline: list[MarketState],
    min_hold_s: int,
    close_spread_factor: float,
    stop_loss_jpy: float = 15.0,
    position_penalty: float = 50.0,
    fill_discount: float = 1.0,
    use_counterfactual: bool = True,
) -> list[SimResult]:
    """Single parameter combo for all trips.

    Args:
        use_counterfactual: True で反事実モデル（推奨）、
                            False で旧期待値モード（後方互換）
    """
    if use_counterfactual:
        return [
            simulate_counterfactual_trip(
                trip=trip, trip_index=i, timeline=timeline,
                min_hold_s=min_hold_s, close_spread_factor=close_spread_factor,
                stop_loss_jpy=stop_loss_jpy, position_penalty=position_penalty,
            )
            for i, trip in enumerate(trips)
        ]
    return [
        simulate_single_trip(
            trip=trip, trip_index=i, timeline=timeline,
            min_hold_s=min_hold_s, close_spread_factor=close_spread_factor,
            stop_loss_jpy=stop_loss_jpy, position_penalty=position_penalty,
            fill_discount=fill_discount,
        )
        for i, trip in enumerate(trips)
    ]


# ---------------------------------------------------------------------------
# run_close_fill_sweep
# ---------------------------------------------------------------------------

def run_close_fill_sweep(
    trips: list[Trip],
    timeline: list[MarketState],
    min_holds: list[int] | None = None,
    factors: list[float] | None = None,
    stop_loss_jpy: float = 15.0,
    fill_discount: float = 1.0,
    use_counterfactual: bool = True,
) -> dict[tuple[int, float], list[SimResult]]:
    """All parameter combos. Default: 6 x 7 = 42 combos."""
    if min_holds is None:
        min_holds = _DEFAULT_MIN_HOLDS
    if factors is None:
        factors = _DEFAULT_FACTORS
    results: dict[tuple[int, float], list[SimResult]] = {}
    for hold in min_holds:
        for factor in factors:
            results[(hold, factor)] = simulate_close_fill(
                trips=trips, timeline=timeline,
                min_hold_s=hold, close_spread_factor=factor,
                stop_loss_jpy=stop_loss_jpy,
                fill_discount=fill_discount,
                use_counterfactual=use_counterfactual,
            )
    return results


# ---------------------------------------------------------------------------
# aggregate_results
# ---------------------------------------------------------------------------

def aggregate_results(results: list[SimResult]) -> dict:
    """Aggregate SimResult list into summary metrics."""
    if not results:
        return {
            "total_trips": 0, "total_pnl": 0.0, "pnl_per_trip": 0.0,
            "fill_count": 0, "sl_count": 0, "timeout_count": 0,
            "win_rate": 0.0, "sl_rate": 0.0, "avg_hold_s": 0.0,
            "avg_close_delay_s": 0.0, "sharpe": 0.0, "pnl_list": [],
        }
    total = len(results)
    pnl_list = [r.simulated_pnl for r in results]
    total_pnl = sum(pnl_list)
    fill_count = sum(1 for r in results if r.dominant_outcome == "fill")
    sl_count = sum(1 for r in results if r.dominant_outcome == "sl")
    timeout_count = sum(1 for r in results if r.dominant_outcome == "timeout")
    win_count = sum(1 for r in results if r.simulated_pnl > 0)
    return {
        "total_trips": total,
        "total_pnl": total_pnl,
        "pnl_per_trip": total_pnl / total,
        "fill_count": fill_count,
        "sl_count": sl_count,
        "timeout_count": timeout_count,
        "win_rate": win_count / total,
        "sl_rate": sl_count / total,
        "avg_hold_s": sum(r.simulated_hold_s for r in results) / total,
        "avg_close_delay_s": sum(r.close_delay_s for r in results) / total,
        "sharpe": calc_sharpe_ratio(pnl_list),
        "pnl_list": pnl_list,
    }


# ---------------------------------------------------------------------------
# print_sweep_grid
# ---------------------------------------------------------------------------

def print_sweep_grid(
    sweep_results: dict[tuple[int, float], list[SimResult]],
    metric: str = "pnl_per_trip",
) -> None:
    """Grid display of sweep results."""
    if not sweep_results:
        print("  No results")
        return
    holds = sorted({k[0] for k in sweep_results})
    factors = sorted({k[1] for k in sweep_results})
    n_combos = len(sweep_results)
    all_aggs = {k: aggregate_results(v) for k, v in sweep_results.items()}

    # DSR: find best SR across all combos
    best_sr = float("-inf")
    best_pnl_list: list[float] = []
    for agg in all_aggs.values():
        if agg["sharpe"] > best_sr and len(agg["pnl_list"]) >= 2:
            best_sr = agg["sharpe"]
            best_pnl_list = agg["pnl_list"]

    dsr_result = None
    significant_keys: set[tuple[int, float]] = set()
    if best_pnl_list:
        dsr_result = evaluate_dsr(best_pnl_list, N=n_combos)
        if dsr_result["significant"]:
            for k, agg in all_aggs.items():
                if len(agg["pnl_list"]) >= 2:
                    cell_dsr = evaluate_dsr(agg["pnl_list"], N=n_combos)
                    if cell_dsr["significant"]:
                        significant_keys.add(k)

    header = f"{'':>12s}" + "".join(f"  f={f:.1f}" for f in factors)
    print(header)
    print("-" * len(header))
    for hold in holds:
        row = f"  hold={hold:3d}s "
        for factor in factors:
            key = (hold, factor)
            agg = all_aggs.get(key)
            if agg is None or agg["total_trips"] == 0:
                row += "     N/A"
                continue
            val = agg[metric]
            mark = " *" if key == (180, 0.4) else ""
            sig = " \u2713" if key in significant_keys else ""
            row += f"  {val:+6.2f}{mark}{sig}"
        print(row)

    if dsr_result:
        print()
        print(f"  {format_dsr_line(dsr=dsr_result['dsr'], N=dsr_result['N'], T=dsr_result['T'], sr_best=dsr_result['sr_best'], significant=dsr_result['significant'])}")
    print(f"\n  * = current config (min_hold=180, factor=0.4)")
