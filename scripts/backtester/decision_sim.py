"""EVパラメータシミュレーター。

異なるalphaやEV計算式でのlevel選択をシミュレートし、
現行の選択との差分を検証する。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from .data_loader import MetricsRow, TradeEvent, Trip
from .ev_formulas import (
    calc_all_formulas,
    current_formula,
    hold_time_formula,
    mean_reversion_formula,
    sqrt_t_formula,
)
from .market_replay import MarketState, build_market_timeline, get_market_state_at

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EVParams
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EVParams:
    """EV計算パラメータ（変更対象）。"""
    alpha: float = 0.7
    ev_formula: str = "current"  # "current" / "sqrt_t" / "hold_time" / "mean_reversion"
    price_step_start: int = 4    # 最小step (L22=step4, L25=step7)

    @property
    def min_level(self) -> int:
        return 18 + self.price_step_start


_OPEN_LEVELS = [22, 23, 24, 25]


# ---------------------------------------------------------------------------
# EV計算
# ---------------------------------------------------------------------------

def calc_ev_for_level(
    level: int,
    p_fill: float,
    market: MarketState,
    params: EVParams,
    hold_time_s: float = 30.0,
) -> float:
    """指定levelのEVを計算。"""
    formula = params.ev_formula
    if formula == "current":
        return current_formula(
            p_fill, market.mid_price, level, market.volatility, params.alpha,
        )
    if formula == "sqrt_t":
        return sqrt_t_formula(
            p_fill, market.mid_price, level, market.sigma_1s,
            market.t_optimal_ms, params.alpha,
        )
    if formula == "hold_time":
        return hold_time_formula(
            p_fill, market.mid_price, level, market.sigma_1s,
            hold_time_s, params.alpha,
        )
    if formula == "mean_reversion":
        return mean_reversion_formula(
            p_fill, market.mid_price, level, market.volatility, params.alpha,
        )
    raise ValueError(f"Unknown formula: {formula}")


def select_best_level(
    market: MarketState,
    p_fill_by_level: dict[int, float],
    params: EVParams,
) -> tuple[int, float]:
    """EVが最大のlevelを選択。

    Returns:
        (best_level, best_ev)
    """
    best_level = -1
    best_ev = float("-inf")

    levels = [lv for lv in _OPEN_LEVELS if lv >= params.min_level]

    for level in levels:
        p_fill = p_fill_by_level.get(level, 0.0)
        ev = calc_ev_for_level(level, p_fill, market, params)
        if ev > best_ev:
            best_ev = ev
            best_level = level

    return best_level, best_ev


# ---------------------------------------------------------------------------
# level選択シミュレーション
# ---------------------------------------------------------------------------

def simulate_level_selection(
    trades: list[TradeEvent],
    metrics: list[MetricsRow],
    params: EVParams,
) -> list[dict]:
    """各ORDER_SENT（open）タイミングで、変更パラメータでのlevel選択をシミュレート。

    Returns:
        [
          {
            timestamp, actual_level, sim_level, actual_ev, sim_ev,
            actual_p_fill, sim_p_fill, changed: bool
          },
          ...
        ]
    """
    timeline = build_market_timeline(metrics)

    sent_open = [
        e for e in trades
        if e.event == "ORDER_SENT" and e.is_close is False
    ]

    # 同一タイムスタンプのSENTをペアとして処理
    by_ts: dict[str, list[TradeEvent]] = defaultdict(list)
    for e in sent_open:
        key = e.timestamp.isoformat()
        by_ts[key].append(e)

    results = []
    for ts_key in sorted(by_ts.keys()):
        events = by_ts[ts_key]
        rep = next((e for e in events if e.side == "BUY"), events[0])

        market = get_market_state_at(timeline, rep.timestamp)
        if market is None:
            continue

        actual_level = rep.level
        actual_ev = rep.single_leg_ev
        actual_p_fill = rep.p_fill

        # 全levelのp_fillマップ
        p_fill_map = {e.level: e.p_fill for e in events if e.level > 0}

        sim_level, sim_ev = select_best_level(market, p_fill_map, params)
        sim_p_fill = p_fill_map.get(sim_level, actual_p_fill)

        results.append({
            "timestamp": rep.timestamp,
            "actual_level": actual_level,
            "sim_level": sim_level,
            "actual_ev": actual_ev,
            "sim_ev": sim_ev,
            "actual_p_fill": actual_p_fill,
            "sim_p_fill": sim_p_fill,
            "changed": actual_level != sim_level,
        })

    return results


# ---------------------------------------------------------------------------
# 全EV式比較
# ---------------------------------------------------------------------------

def compare_ev_formulas(
    trades: list[TradeEvent],
    metrics: list[MetricsRow],
    alpha: float = 0.7,
    sample_hold_time_s: float = 30.0,
) -> list[dict]:
    """全EV計算式を各ORDER_SENTタイミングで比較。"""
    timeline = build_market_timeline(metrics)
    sent_open = [
        e for e in trades
        if e.event == "ORDER_SENT" and e.is_close is False
    ]

    results = []
    for e in sent_open:
        if e.level <= 0:
            continue
        market = get_market_state_at(timeline, e.timestamp)
        if market is None:
            continue

        evs = calc_all_formulas(
            p_fill=e.p_fill,
            mid_price=market.mid_price,
            level=e.level,
            volatility=market.volatility,
            sigma_1s=market.sigma_1s,
            t_optimal_ms=market.t_optimal_ms,
            alpha=alpha,
            hold_time_s=sample_hold_time_s,
        )

        results.append({
            "timestamp": e.timestamp,
            "level": e.level,
            "p_fill": e.p_fill,
            **{f"ev_{k}": v for k, v in evs.items()},
        })

    return results


# ---------------------------------------------------------------------------
# alpha感度分析
# ---------------------------------------------------------------------------

def analyze_alpha_sensitivity(
    trades: list[TradeEvent],
    metrics: list[MetricsRow],
    alpha_range: list[float],
) -> list[dict]:
    """異なるalpha値でのlevel選択変化を分析。

    Returns:
        [
          {"alpha": float, "level_22_pct": float, "level_23_pct": float, ...
           "avg_ev": float, "change_rate": float},
          ...
        ]
    """
    baseline_params = EVParams(alpha=0.7)
    results = []

    for alpha in alpha_range:
        params = EVParams(alpha=alpha)
        sims = simulate_level_selection(trades, metrics, params)

        if not sims:
            continue

        level_counts: dict[int, int] = defaultdict(int)
        ev_sum = 0.0
        changed = 0

        for s in sims:
            level_counts[s["sim_level"]] += 1
            ev_sum += s["sim_ev"]
            if s["changed"]:
                changed += 1

        total = len(sims)
        row: dict = {
            "alpha": alpha,
            "avg_ev": ev_sum / total,
            "change_rate": changed / total,
        }
        for lv in _OPEN_LEVELS:
            row[f"level_{lv}_pct"] = level_counts.get(lv, 0) / total

        results.append(row)

    return results
