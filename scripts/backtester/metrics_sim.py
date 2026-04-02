"""24h Market Hours シミュレーション。

メトリクスデータ (24h記録) と取引時間帯の実績から、
非取引時間帯 (UTC 15-23) での推定P&Lを算出する。

手法: EV-to-P&L比率スケーリング
  1. 取引時間帯: actual trips / metricsからキャリブレーション係数を算出
  2. 非取引時間帯: metrics × 係数で推定P&Lを計算
  3. 取引 vs 非取引を比較 → EXPAND / KEEP_FILTER 判定
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from .data_loader import MetricsRow, Trip

logger = logging.getLogger(__name__)

# 現在の取引時間帯 (UTC)
TRADING_HOURS_START = 0
TRADING_HOURS_END = 15  # 0-14 が取引可能


@dataclass(frozen=True)
class HourlyMetrics:
    """UTC時間別のメトリクス集計。"""
    utc_hour: int
    count: int
    avg_best_ev: float
    avg_volatility: float
    avg_spread: float
    avg_p_fill: float  # (buy_prob_avg + sell_prob_avg) / 2
    avg_mid_price: float


@dataclass(frozen=True)
class HourlyTrips:
    """UTC時間別のトリップ実績。"""
    utc_hour: int
    trip_count: int
    pnl_sum: float
    pnl_mean: float
    win_rate: float
    hours_observed: float  # その時間帯のデータが存在する時間数


@dataclass(frozen=True)
class CalibrationFactors:
    """取引時間帯の実績から算出するキャリブレーション係数。"""
    pnl_per_trip: float
    avg_best_ev: float
    ev_to_pnl_ratio: float
    fill_rate: float
    trips_per_hour: float
    trading_hours_observed: float


@dataclass(frozen=True)
class HourEstimate:
    """1時間あたりの推定/実績。"""
    utc_hour: int
    is_actual: bool
    trips: int
    pnl_per_trip: float
    pnl_per_hour: float
    best_ev: float
    volatility: float
    spread: float
    p_fill: float
    # クロスバリデーション用: 推定値 (is_actual=Trueの場合のみ有効)
    est_pnl_per_trip: float = 0.0
    est_pnl_per_hour: float = 0.0


def aggregate_metrics_by_hour(metrics: list[MetricsRow]) -> list[HourlyMetrics]:
    """UTC時間別にspread/vol/best_ev/p_fill平均を集計。"""
    buckets: dict[int, list[MetricsRow]] = defaultdict(list)
    for m in metrics:
        buckets[m.timestamp.hour].append(m)

    results = []
    for hour in range(24):
        rows = buckets.get(hour, [])
        if not rows:
            continue
        n = len(rows)
        results.append(HourlyMetrics(
            utc_hour=hour,
            count=n,
            avg_best_ev=sum(r.best_ev for r in rows) / n,
            avg_volatility=sum(r.volatility for r in rows) / n,
            avg_spread=sum(r.spread for r in rows) / n,
            avg_p_fill=sum((r.buy_prob_avg + r.sell_prob_avg) / 2 for r in rows) / n,
            avg_mid_price=sum(r.mid_price for r in rows) / n,
        ))
    return results


def aggregate_trips_by_hour(trips: list[Trip], metrics: list[MetricsRow]) -> list[HourlyTrips]:
    """UTC時間別に実際のtrip数/P&L集計。

    hours_observedはメトリクスの最初/最後のタイムスタンプから算出。
    """
    matched = [t for t in trips if t.close_fill is not None]

    # メトリクスから各時間帯の観測時間を算出
    hour_timestamps: dict[int, list[float]] = defaultdict(list)
    for m in metrics:
        hour_timestamps[m.timestamp.hour].append(m.timestamp.timestamp())

    trip_buckets: dict[int, list[Trip]] = defaultdict(list)
    for t in matched:
        trip_buckets[t.open_fill.timestamp.hour].append(t)

    results = []
    for hour in range(24):
        trips_in_hour = trip_buckets.get(hour, [])
        ts_list = hour_timestamps.get(hour, [])

        if not ts_list:
            hours_obs = 0.0
        else:
            hours_obs = (max(ts_list) - min(ts_list)) / 3600.0
            hours_obs = max(hours_obs, 1 / 60)  # 最低1分

        n = len(trips_in_hour)
        pnl_sum = sum(t.pnl_jpy for t in trips_in_hour)
        wins = sum(1 for t in trips_in_hour if t.pnl_jpy > 0)

        results.append(HourlyTrips(
            utc_hour=hour,
            trip_count=n,
            pnl_sum=pnl_sum,
            pnl_mean=pnl_sum / n if n > 0 else 0.0,
            win_rate=wins / n if n > 0 else 0.0,
            hours_observed=hours_obs,
        ))
    return results


def calc_calibration_factors(
    hourly_metrics: list[HourlyMetrics],
    hourly_trips: list[HourlyTrips],
) -> CalibrationFactors:
    """取引時間帯 (UTC 0-14) のデータからキャリブレーション係数を算出。"""
    trading_metrics = [
        m for m in hourly_metrics
        if TRADING_HOURS_START <= m.utc_hour < TRADING_HOURS_END
    ]
    trading_trips = [
        t for t in hourly_trips
        if TRADING_HOURS_START <= t.utc_hour < TRADING_HOURS_END
    ]

    total_trips = sum(t.trip_count for t in trading_trips)
    total_pnl = sum(t.pnl_sum for t in trading_trips)
    total_hours = sum(t.hours_observed for t in trading_trips)

    pnl_per_trip = total_pnl / total_trips if total_trips > 0 else 0.0
    trips_per_hour = total_trips / total_hours if total_hours > 0 else 0.0

    total_ev_weight = sum(m.count for m in trading_metrics)
    avg_ev = (
        sum(m.avg_best_ev * m.count for m in trading_metrics) / total_ev_weight
        if total_ev_weight > 0 else 0.0
    )

    ev_to_pnl = pnl_per_trip / avg_ev if avg_ev != 0 else 0.0

    # fill rate: trips / (想定注文数)。order_interval=3s → 1200 orders/h
    orders_per_hour = 3600 / 3.0
    fill_rate = trips_per_hour * 2 / orders_per_hour if orders_per_hour > 0 else 0.0

    return CalibrationFactors(
        pnl_per_trip=pnl_per_trip,
        avg_best_ev=avg_ev,
        ev_to_pnl_ratio=ev_to_pnl,
        fill_rate=fill_rate,
        trips_per_hour=trips_per_hour,
        trading_hours_observed=total_hours,
    )


def estimate_non_trading_hours(
    hourly_metrics: list[HourlyMetrics],
    hourly_trips: list[HourlyTrips],
    calibration: CalibrationFactors,
) -> list[HourEstimate]:
    """全24時間のP&L推定を生成。

    取引時間帯は実績値、非取引時間帯はキャリブレーション係数による推定値。
    """
    metrics_by_hour = {m.utc_hour: m for m in hourly_metrics}
    trips_by_hour = {t.utc_hour: t for t in hourly_trips}

    # 取引時間帯のP(fill)加重平均を事前計算 (ループ外)
    trading_m = [
        m for m in hourly_metrics
        if TRADING_HOURS_START <= m.utc_hour < TRADING_HOURS_END
    ]
    trading_weight = sum(m.count for m in trading_m)
    avg_trading_p_fill = (
        sum(m.avg_p_fill * m.count for m in trading_m) / trading_weight
        if trading_weight > 0 else 0.0
    )

    def _calc_est(m: HourlyMetrics) -> tuple[float, float]:
        """メトリクスからP&L/trip, P&L/hの推定値を算出。"""
        e_pnl = m.avg_best_ev * calibration.ev_to_pnl_ratio
        p_ratio = m.avg_p_fill / avg_trading_p_fill if avg_trading_p_fill > 0 else 1.0
        e_trips_h = calibration.trips_per_hour * p_ratio
        return e_pnl, e_pnl * e_trips_h

    estimates = []
    for hour in range(24):
        m = metrics_by_hour.get(hour)
        t = trips_by_hour.get(hour)
        has_trips = t is not None and t.trip_count > 0

        # tripデータがあれば常にactual (取引/非取引時間帯を問わない)
        if has_trips and m is not None:
            pnl_h = t.pnl_sum / t.hours_observed if t.hours_observed > 0 else 0.0
            e_pnl_trip, e_pnl_h = _calc_est(m)
            estimates.append(HourEstimate(
                utc_hour=hour,
                is_actual=True,
                trips=t.trip_count,
                pnl_per_trip=t.pnl_mean,
                pnl_per_hour=pnl_h,
                best_ev=m.avg_best_ev,
                volatility=m.avg_volatility,
                spread=m.avg_spread,
                p_fill=m.avg_p_fill,
                est_pnl_per_trip=e_pnl_trip,
                est_pnl_per_hour=e_pnl_h,
            ))
        elif has_trips:
            pnl_h = t.pnl_sum / t.hours_observed if t.hours_observed > 0 else 0.0
            estimates.append(HourEstimate(
                utc_hour=hour,
                is_actual=True,
                trips=t.trip_count,
                pnl_per_trip=t.pnl_mean,
                pnl_per_hour=pnl_h,
                best_ev=0.0,
                volatility=0.0,
                spread=0.0,
                p_fill=0.0,
            ))
        elif m is not None:
            e_pnl_trip, e_pnl_h = _calc_est(m)
            estimates.append(HourEstimate(
                utc_hour=hour,
                is_actual=False,
                trips=0,
                pnl_per_trip=e_pnl_trip,
                pnl_per_hour=e_pnl_h,
                best_ev=m.avg_best_ev,
                volatility=m.avg_volatility,
                spread=m.avg_spread,
                p_fill=m.avg_p_fill,
            ))
        else:
            estimates.append(HourEstimate(
                utc_hour=hour,
                is_actual=False,
                trips=0,
                pnl_per_trip=0.0,
                pnl_per_hour=0.0,
                best_ev=0.0,
                volatility=0.0,
                spread=0.0,
                p_fill=0.0,
            ))

    return estimates


def format_summary(estimates: list[HourEstimate]) -> str:
    """EXPAND/KEEP_FILTER判定を含むサマリー文字列を返す。

    取引時間帯 (UTC 0-14) と非取引時間帯 (UTC 15-23) を比較。
    非取引時間帯はactual (24hデータ時) または estimated を使う。
    """
    trading = [e for e in estimates if 0 <= e.utc_hour < 15]
    non_trading = [e for e in estimates if e.utc_hour >= 15]

    trading_with_data = [e for e in trading if e.is_actual or e.best_ev > 0]
    non_trading_with_data = [e for e in non_trading if e.is_actual or e.best_ev > 0]

    trading_pnl_h = (
        sum(e.pnl_per_hour for e in trading_with_data) / len(trading_with_data)
        if trading_with_data else 0.0
    )

    # 非取引時間帯: actualがあればactual、なければestimated
    non_trading_actual = [e for e in non_trading_with_data if e.is_actual]
    if non_trading_actual:
        non_trading_pnl_h = (
            sum(e.pnl_per_hour for e in non_trading_actual) / len(non_trading_actual)
        )
        nt_label = f"actual, {len(non_trading_actual)} hours"
    else:
        non_trading_est = [e for e in non_trading_with_data if e.best_ev > 0]
        non_trading_pnl_h = (
            sum(e.pnl_per_hour for e in non_trading_est) / len(non_trading_est)
            if non_trading_est else 0.0
        )
        nt_label = f"estimated, {len(non_trading_est)} hours"

    lines = [
        f"  Trading (UTC 00-14) P&L/h:     {trading_pnl_h:+.1f} JPY/h"
        f" ({len(trading_with_data)} hours)",
        f"  Non-trading (UTC 15-23) P&L/h: {non_trading_pnl_h:+.1f} JPY/h"
        f" ({nt_label})",
    ]

    if not non_trading_with_data:
        recommendation = "INCONCLUSIVE (no non-trading data)"
    elif non_trading_pnl_h > 0:
        recommendation = "EXPAND (non-trading hours estimated positive)"
    elif trading_pnl_h < 0 and non_trading_pnl_h > trading_pnl_h:
        recommendation = "EXPAND (non-trading hours less negative)"
    else:
        recommendation = "KEEP_FILTER (non-trading hours worse)"

    lines.append(f"  Recommendation: {recommendation}")
    return "\n".join(lines)
