"""Trip分析モジュール。

data_loader.build_trips()で構築されたTripリストに対し、
hold_time分析・グループ別集計・close戦略変更what-if等を提供。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

from .data_loader import TradeEvent, Trip
from .market_replay import MarketState, get_mid_price_series

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# hold_time分析
# ---------------------------------------------------------------------------

_HOLD_BUCKETS: list[tuple[str, float, float]] = [
    ("0-30s", 0, 30),
    ("30-60s", 30, 60),
    ("60-120s", 60, 120),
    ("120-300s", 120, 300),
    ("300-600s", 300, 600),
    (">600s", 600, float("inf")),
]


def _assign_hold_bucket(hold_time_s: float) -> str:
    for label, lo, hi in _HOLD_BUCKETS:
        if lo <= hold_time_s < hi:
            return label
    return ">600s"


def analyze_hold_time_vs_pnl(
    trips: list[Trip],
    buckets: Optional[list[tuple[int, int]]] = None,
) -> list[dict]:
    """hold_time帯別のP&L・mid逆行を集計。

    Args:
        trips: build_trips()の結果
        buckets: カスタムバケット [(lo, hi), ...] 。Noneならデフォルト使用

    Returns:
        各バケットの {hold_bucket, count, pnl_sum, pnl_mean, adverse_mean,
                      spread_mean, win_rate, sl_count}
    """
    matched = [t for t in trips if t.close_fill is not None]

    if buckets is not None:
        bucket_defs = [
            (f"{lo}-{hi}s", lo, hi) for lo, hi in buckets
        ]
    else:
        bucket_defs = _HOLD_BUCKETS

    def assign(hold_time_s: float) -> str:
        for label, lo, hi in bucket_defs:
            if lo <= hold_time_s < hi:
                return label
        return bucket_defs[-1][0] if bucket_defs else "unknown"

    groups: dict[str, list[Trip]] = {label: [] for label, _, _ in bucket_defs}
    for t in matched:
        bucket = assign(t.hold_time_s)
        if bucket in groups:
            groups[bucket].append(t)

    rows = []
    for label, _, _ in bucket_defs:
        ts = groups.get(label, [])
        if not ts:
            rows.append({
                "hold_bucket": label,
                "count": 0,
                "pnl_sum": 0.0,
                "pnl_mean": 0.0,
                "adverse_mean": 0.0,
                "spread_mean": 0.0,
                "win_rate": 0.0,
                "sl_count": 0,
            })
            continue

        pnl_list = [t.pnl_jpy for t in ts]
        adverse_list = [t.mid_adverse_jpy for t in ts]
        spread_list = [t.spread_captured_jpy for t in ts]
        wins = sum(1 for p in pnl_list if p > 0)

        rows.append({
            "hold_bucket": label,
            "count": len(ts),
            "pnl_sum": sum(pnl_list),
            "pnl_mean": sum(pnl_list) / len(pnl_list),
            "adverse_mean": sum(adverse_list) / len(adverse_list),
            "spread_mean": sum(spread_list) / len(spread_list),
            "win_rate": wins / len(ts),
            "sl_count": sum(1 for t in ts if t.sl_triggered),
        })

    return rows


# ---------------------------------------------------------------------------
# グループ別集計
# ---------------------------------------------------------------------------

def analyze_by_group(
    trips: list[Trip],
    group_by: str = "level",
) -> list[dict]:
    """グループ別トリップ統計集計。

    Args:
        group_by: "level" / "utc_hour" / "side"
    """
    matched = [t for t in trips if t.close_fill is not None]

    def get_key(t: Trip) -> str:
        if group_by == "level":
            return f"L{t.open_fill.level}"
        if group_by == "utc_hour":
            return f"UTC{t.open_fill.timestamp.hour:02d}"
        if group_by == "side":
            return t.open_fill.side
        return "unknown"

    groups: dict[str, list[Trip]] = defaultdict(list)
    for t in matched:
        groups[get_key(t)].append(t)

    rows = []
    for key in sorted(groups.keys()):
        ts = groups[key]
        pnl_list = [t.pnl_jpy for t in ts]
        adverse_list = [t.mid_adverse_jpy for t in ts]
        spread_list = [t.spread_captured_jpy for t in ts]
        hold_list = [t.hold_time_s for t in ts]
        wins = sum(1 for p in pnl_list if p > 0)

        rows.append({
            "group": key,
            "count": len(ts),
            "pnl_sum": sum(pnl_list),
            "pnl_mean": sum(pnl_list) / len(pnl_list),
            "adverse_mean": sum(adverse_list) / len(adverse_list),
            "spread_mean": sum(spread_list) / len(spread_list),
            "hold_mean_s": sum(hold_list) / len(hold_list),
            "win_rate": wins / len(ts),
            "sl_count": sum(1 for t in ts if t.sl_triggered),
        })

    return rows


# ---------------------------------------------------------------------------
# close dynamics分析
# ---------------------------------------------------------------------------

def analyze_close_dynamics(
    trips: list[Trip],
    order_map: dict[str, list[TradeEvent]],
    timeline: list[MarketState],
) -> dict:
    """close注文のcancel/resubmit回数、各サイクルの価格変化を分析。

    1トリップのclose処理はSENT→CANCELLED→(再SENT)→...→FILLEDと複数注文にわたる。
    open fill後からclose fill前までの期間内のclose注文をすべて集計する。

    Returns:
        {
            "total_close_fills": int,
            "avg_cancel_cycles": float,
            "avg_price_adjustment": float (JPY, abs),
            "details": [
                {
                    "trip_idx": int,
                    "cancel_count": int,          # cancel回数(=close注文の試み数-1)
                    "sent_count": int,             # close注文発行総数
                    "price_adjustments": [float, ...],
                    "total_close_time_s": float,
                }
            ]
        }
    """
    # tripの期間（open_fill.ts → close_fill.ts）内のclose ORDER_SENTを収集
    # order_mapを逆引きするためにis_close=trueのSENTを時刻でインデックス化
    close_sents_by_ts: list[TradeEvent] = sorted(
        [
            e
            for events in order_map.values()
            for e in events
            if e.event == "ORDER_SENT" and e.is_close is True
        ],
        key=lambda e: e.timestamp,
    )

    details = []
    total_cancel_cycles = 0
    total_price_adjustments: list[float] = []

    for idx, trip in enumerate(trips):
        if trip.close_fill is None:
            continue

        open_ts = trip.open_fill.timestamp
        close_ts = trip.close_fill.timestamp

        # tripのopen〜close期間内に発行されたclose SENT注文をすべて取得
        period_close_sents = [
            e for e in close_sents_by_ts
            if open_ts <= e.timestamp <= close_ts and e.is_close is True
        ]
        period_close_sents.sort(key=lambda e: e.timestamp)

        sent_count = len(period_close_sents)
        # cancel回数 = sent_count - 1（最後のSENTはfillまたは継続中）
        cancel_count = max(0, sent_count - 1)

        # 価格変化: 連続するSENT間の価格差
        price_adjs: list[float] = []
        for i in range(1, len(period_close_sents)):
            adj = period_close_sents[i].price - period_close_sents[i - 1].price
            price_adjs.append(adj)

        # close全体の所要時間（初回close SENT → close fill）
        if period_close_sents:
            first_sent_ts = period_close_sents[0].timestamp
            close_time_s = (close_ts - first_sent_ts).total_seconds()
        else:
            close_time_s = 0.0

        total_cancel_cycles += cancel_count
        total_price_adjustments.extend(price_adjs)

        details.append({
            "trip_idx": idx,
            "cancel_count": cancel_count,
            "sent_count": sent_count,
            "price_adjustments": price_adjs,
            "total_close_time_s": close_time_s,
        })

    matched_count = len(details)
    avg_cancel = total_cancel_cycles / matched_count if matched_count > 0 else 0.0
    avg_price_adj = (
        sum(abs(a) for a in total_price_adjustments) / len(total_price_adjustments)
        if total_price_adjustments
        else 0.0
    )

    return {
        "total_close_fills": matched_count,
        "avg_cancel_cycles": avg_cancel,
        "avg_price_adjustment": avg_price_adj,
        "details": details,
    }


# ---------------------------------------------------------------------------
# 時間フィルタ影響分析
# ---------------------------------------------------------------------------

def calc_time_filter_impact(
    trips: list[Trip],
    utc_start: int,
    utc_end: int,
) -> dict:
    """UTC時間フィルタ変更時のP&L影響を推定。

    Args:
        utc_start: フィルタ開始時間 (包含)
        utc_end:   フィルタ終了時間 (非包含)

    Returns:
        {
            filter_spec, included: {pnl_sum, pnl_mean, count},
            excluded: {pnl_sum, pnl_mean, count},
            total: {pnl_sum, count}
        }
    """
    matched = [t for t in trips if t.close_fill is not None]

    def in_filter(t: Trip) -> bool:
        h = t.open_fill.timestamp.hour
        if utc_start <= utc_end:
            return utc_start <= h < utc_end
        # 日跨ぎ (e.g. 22-6)
        return h >= utc_start or h < utc_end

    included = [t for t in matched if in_filter(t)]
    excluded = [t for t in matched if not in_filter(t)]

    def stats(ts: list[Trip]) -> dict:
        if not ts:
            return {"pnl_sum": 0.0, "pnl_mean": 0.0, "count": 0}
        pnl_list = [t.pnl_jpy for t in ts]
        return {
            "pnl_sum": sum(pnl_list),
            "pnl_mean": sum(pnl_list) / len(pnl_list),
            "count": len(ts),
        }

    total_pnl = sum(t.pnl_jpy for t in matched)
    return {
        "filter_spec": f"UTC {utc_start:02d}-{utc_end:02d}",
        "included": stats(included),
        "excluded": stats(excluded),
        "total": {"pnl_sum": total_pnl, "count": len(matched)},
    }


# ---------------------------------------------------------------------------
# mid推移分析（個別トリップ）
# ---------------------------------------------------------------------------

def get_trip_mid_path(
    trip: Trip,
    timeline: list[MarketState],
) -> list[dict]:
    """個別トリップのmid_price推移を返す。

    Returns:
        [{"t_s": float, "mid": float, "rel_mid": float}, ...]
    """
    if trip.close_fill is None:
        return []

    open_ts = trip.open_fill.timestamp
    close_ts = trip.close_fill.timestamp
    series = get_mid_price_series(timeline, open_ts, close_ts)

    open_mid = trip.open_fill.mid_price
    sign = 1 if trip.open_fill.side == "BUY" else -1

    return [
        {
            "t_s": (ts - open_ts).total_seconds(),
            "mid": mid,
            "rel_mid": sign * (mid - open_mid),
        }
        for ts, mid in series
    ]
