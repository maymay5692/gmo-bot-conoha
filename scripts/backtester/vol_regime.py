"""ボラティリティレジーム分析モジュール。

EWMA volatilityのパーセンタイルで低・中・高の3レジームに分類し、
レジーム別P&L集計とフィルタwhat-ifシミュレーションを提供する。
"""
from __future__ import annotations

from datetime import datetime

from .market_replay import MarketState


def _percentile(sorted_values: list[float], pct: float) -> float:
    """ソート済みリストのパーセンタイル値を返す（線形補間）。"""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    k = (n - 1) * pct / 100.0
    f = int(k)
    c = f + 1
    if c >= n:
        return sorted_values[-1]
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])


def classify_vol_regime(
    timeline: list[MarketState],
    percentiles: tuple[float, float] = (25, 75),
) -> dict:
    """volatility分布のパーセンタイルで各時刻にレジームラベルを付与。

    Args:
        timeline: build_market_timeline()の結果
        percentiles: (低/中の境界, 中/高の境界) パーセンタイル

    Returns:
        {
            "boundaries": {"low": float, "high": float},
            "labels": {datetime: "low" | "mid" | "high"},
        }
    """
    if not timeline:
        return {
            "boundaries": {"low": 0.0, "high": 0.0},
            "labels": {},
        }

    vols = sorted(s.volatility for s in timeline)
    p_low = _percentile(vols, percentiles[0])
    p_high = _percentile(vols, percentiles[1])

    # 全volatilityが同一の場合、全てmid領域
    if p_low == p_high:
        labels = {s.timestamp: "mid" for s in timeline}
        return {"boundaries": {"low": p_low, "high": p_high}, "labels": labels}

    labels: dict[datetime, str] = {}
    for s in timeline:
        if s.volatility < p_low:
            labels[s.timestamp] = "low"
        elif s.volatility >= p_high:
            labels[s.timestamp] = "high"
        else:
            labels[s.timestamp] = "mid"

    return {
        "boundaries": {"low": p_low, "high": p_high},
        "labels": labels,
    }
