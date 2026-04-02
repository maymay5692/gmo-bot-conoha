"""Module 1: Market State Replay

Metrics CSVからの市場状態タイムライン再構築。
指定時刻の市場状態補間、mid_price時系列取得などを提供。
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .data_loader import MetricsRow


@dataclass(frozen=True)
class MarketState:
    """特定時刻の市場状態スナップショット。"""
    timestamp: datetime
    mid_price: float
    spread: float
    sigma_1s: float
    volatility: float
    t_optimal_ms: int
    long_size: float
    short_size: float
    best_ask: float
    best_bid: float
    buy_spread_pct: float
    sell_spread_pct: float

    @property
    def has_position(self) -> bool:
        return self.long_size > 0 or self.short_size > 0


def build_market_timeline(metrics: list[MetricsRow]) -> list[MarketState]:
    """MetricsRowリストからMarketStateのタイムライン（時刻順）を構築。"""
    return [
        MarketState(
            timestamp=m.timestamp,
            mid_price=m.mid_price,
            spread=m.spread,
            sigma_1s=m.sigma_1s,
            volatility=m.volatility,
            t_optimal_ms=m.t_optimal_ms,
            long_size=m.long_size,
            short_size=m.short_size,
            best_ask=m.best_ask,
            best_bid=m.best_bid,
            buy_spread_pct=m.buy_spread_pct,
            sell_spread_pct=m.sell_spread_pct,
        )
        for m in metrics
    ]


def get_market_state_at(
    timeline: list[MarketState],
    ts: datetime,
) -> Optional[MarketState]:
    """指定時刻の直前のMarketStateを返す（ステップ補間）。

    タイムライン外（最初のエントリより前）の場合はNoneを返す。
    """
    if not timeline:
        return None

    # タイムスタンプリストでbisectを使って効率的に検索
    timestamps = [s.timestamp for s in timeline]
    idx = bisect.bisect_right(timestamps, ts) - 1

    if idx < 0:
        return None
    return timeline[idx]


def get_mid_price_series(
    timeline: list[MarketState],
    start: datetime,
    end: datetime,
) -> list[tuple[datetime, float]]:
    """指定期間のmid_price時系列を返す。

    Returns:
        [(timestamp, mid_price), ...] のリスト
    """
    return [
        (s.timestamp, s.mid_price)
        for s in timeline
        if start <= s.timestamp <= end
    ]


def calc_mid_adverse(
    timeline: list[MarketState],
    open_ts: datetime,
    open_side: str,   # "BUY" or "SELL"
    open_mid: float,
    close_ts: datetime,
    close_mid: float,
) -> dict:
    """トリップ中のmid_price変化を詳細分析。

    Args:
        open_side: open fillのside ("BUY" or "SELL")
        open_mid:  open fill時点のmid_price
        close_mid: close fill時点のmid_price

    Returns:
        hold_time_s:    保有時間（秒）
        mid_change:     close_mid - open_mid（BUYなら正が有利）
        adverse_jpy:    mid逆行のJPY換算（size=0.001固定）
        max_adverse_jpy:期間中の最大逆行
        mean_reversion: 最大逆行からの回帰度（0~1）
        mid_series:     [(datetime, mid_price), ...]
    """
    size = 0.001
    mid_series = get_mid_price_series(timeline, open_ts, close_ts)
    hold_time_s = (close_ts - open_ts).total_seconds()

    # mid変化: BUYは上昇が有利（mid上昇 → BUY側に有利）
    if open_side == "BUY":
        mid_change = close_mid - open_mid
        # 途中の最悪点（最も下がった）
        mid_prices = [p for _, p in mid_series]
        min_mid = min(mid_prices) if mid_prices else open_mid
        max_adverse = (open_mid - min_mid) * size  # 正値 = 逆行
    else:
        mid_change = open_mid - close_mid  # SELLは下落が有利
        mid_prices = [p for _, p in mid_series]
        max_mid = max(mid_prices) if mid_prices else open_mid
        max_adverse = (max_mid - open_mid) * size

    # adverse_jpy: 最終的な逆行（負値 = 利益方向）
    if open_side == "BUY":
        adverse_jpy = -mid_change * size  # 正値 = 不利
    else:
        adverse_jpy = -mid_change * size

    # mean_reversion: 最大逆行からどれだけ回復したか（0~1, 1=完全回復）
    if max_adverse > 0:
        final_loss = max(0.0, adverse_jpy)
        mean_reversion = 1.0 - (final_loss / max_adverse)
    else:
        mean_reversion = 1.0

    return {
        "hold_time_s": hold_time_s,
        "mid_change": mid_change,
        "adverse_jpy": adverse_jpy,
        "max_adverse_jpy": max_adverse,
        "mean_reversion": mean_reversion,
        "mid_series": mid_series,
    }
