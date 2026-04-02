"""CSVデータの読み込み・パースモジュール。

TradeEvent / MetricsRow / Trip の型定義と、VPS/キャッシュからのデータ取得。
build_order_book / build_trips による注文ライフサイクル・トリップ構築。
"""
from __future__ import annotations

import logging
import os
import sys
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# 親ディレクトリのlibをimport可能にする
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from lib.data_fetch import get_data  # noqa: E402


# ---------------------------------------------------------------------------
# タイムスタンプパーサー
# ---------------------------------------------------------------------------

def _parse_ts(ts_str: str) -> datetime:
    """'+00:00' / ナノ秒対応のタイムスタンプをパースしてUTC datetimeを返す。"""
    ts_str = ts_str.replace("+00:00", "")
    if "." in ts_str:
        base, frac = ts_str.split(".", 1)
        frac = frac[:6]  # マイクロ秒まで
        ts_str = f"{base}.{frac}"
    dt = datetime.fromisoformat(ts_str)
    return dt.replace(tzinfo=timezone.utc)


def _safe_float(val: str, default: float = 0.0) -> float:
    try:
        return float(val) if val else default
    except ValueError:
        return default


def _safe_int(val: str, default: int = 0) -> int:
    try:
        return int(val) if val else default
    except ValueError:
        return default


def _safe_bool(val: str) -> Optional[bool]:
    """'true'/'false' → bool、空文字 → None。"""
    if val == "true":
        return True
    if val == "false":
        return False
    return None


# ---------------------------------------------------------------------------
# TradeEvent
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TradeEvent:
    """Trades CSVの1イベント。"""
    timestamp: datetime
    event: str           # ORDER_SENT / ORDER_FILLED / ORDER_CANCELLED / ORDER_FAILED / STOP_LOSS_TRIGGERED
    order_id: str
    side: str            # BUY / SELL / ""
    price: float         # 空なら0.0
    size: float          # 0.001固定
    mid_price: float
    is_close: Optional[bool]   # None = フィールドが空（CANCELLEDなど）
    level: int           # 0=close, 22-25=open, -1=不明
    p_fill: float
    best_ev: float
    single_leg_ev: float
    sigma_1s: float
    spread_pct: float
    t_optimal_ms: int
    order_age_ms: int    # ORDER_FILLED時のみ有効
    error: str


def _parse_trade_event(row: dict) -> TradeEvent:
    level_str = row.get("level", "")
    return TradeEvent(
        timestamp=_parse_ts(row["timestamp"]),
        event=row.get("event", ""),
        order_id=row.get("order_id", ""),
        side=row.get("side", ""),
        price=_safe_float(row.get("price", "")),
        size=_safe_float(row.get("size", ""), 0.001),
        mid_price=_safe_float(row.get("mid_price", "")),
        is_close=_safe_bool(row.get("is_close", "")),
        level=_safe_int(level_str, -1) if level_str else -1,
        p_fill=_safe_float(row.get("p_fill", "")),
        best_ev=_safe_float(row.get("best_ev", "")),
        single_leg_ev=_safe_float(row.get("single_leg_ev", "")),
        sigma_1s=_safe_float(row.get("sigma_1s", "")),
        spread_pct=_safe_float(row.get("spread_pct", "")),
        t_optimal_ms=_safe_int(row.get("t_optimal_ms", "")),
        order_age_ms=_safe_int(row.get("order_age_ms", "")),
        error=row.get("error", ""),
    )


# ---------------------------------------------------------------------------
# MetricsRow
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricsRow:
    """Metrics CSVの1行（約3秒間隔のスナップショット）。"""
    timestamp: datetime
    best_ask: float
    best_bid: float
    mid_price: float
    spread: float
    volatility: float
    sigma_1s: float
    t_optimal_ms: int
    best_ev: float
    buy_prob_avg: float
    sell_prob_avg: float
    buy_spread_pct: float
    sell_spread_pct: float
    collateral: float
    long_size: float
    short_size: float


def _parse_metrics_row(row: dict) -> MetricsRow:
    return MetricsRow(
        timestamp=_parse_ts(row["timestamp"]),
        best_ask=_safe_float(row.get("best_ask", "")),
        best_bid=_safe_float(row.get("best_bid", "")),
        mid_price=_safe_float(row.get("mid_price", "")),
        spread=_safe_float(row.get("spread", "")),
        volatility=_safe_float(row.get("volatility", "")),
        sigma_1s=_safe_float(row.get("sigma_1s", "")),
        t_optimal_ms=_safe_int(row.get("t_optimal_ms", "")),
        best_ev=_safe_float(row.get("best_ev", "")),
        buy_prob_avg=_safe_float(row.get("buy_prob_avg", "")),
        sell_prob_avg=_safe_float(row.get("sell_prob_avg", "")),
        buy_spread_pct=_safe_float(row.get("buy_spread_pct", "")),
        sell_spread_pct=_safe_float(row.get("sell_spread_pct", "")),
        collateral=_safe_float(row.get("collateral", "")),
        long_size=_safe_float(row.get("long_size", "")),
        short_size=_safe_float(row.get("short_size", "")),
    )


# ---------------------------------------------------------------------------
# 公開インターフェース
# ---------------------------------------------------------------------------

def load_trades(date: str, force_fetch: bool = False) -> list[TradeEvent]:
    """Trades CSVをロードしてTradeEventリストを返す。

    キャッシュがあれば使用、なければVPSからフェッチ。
    """
    rows = get_data("trades", date, force_fetch=force_fetch)
    if not rows:
        return []
    events = [_parse_trade_event(r) for r in rows]
    events.sort(key=lambda e: e.timestamp)
    return events


def load_metrics(date: str, force_fetch: bool = False) -> list[MetricsRow]:
    """Metrics CSVをロードしてMetricsRowリストを返す。

    キャッシュがあれば使用、なければVPSからフェッチ。
    """
    rows = get_data("metrics", date, force_fetch=force_fetch)
    if not rows:
        return []
    metrics = [_parse_metrics_row(r) for r in rows]
    metrics.sort(key=lambda m: m.timestamp)
    return metrics


# ---------------------------------------------------------------------------
# Trip
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Trip:
    """open fill → close fill (or SL) の1トリップ。"""
    open_fill: TradeEvent
    close_fill: Optional[TradeEvent]  # None = 未クローズ
    sl_triggered: bool
    hold_time_s: float
    pnl_jpy: float
    mid_adverse_jpy: float
    spread_captured_jpy: float


def _calc_trip_fields(
    open_fill: TradeEvent,
    close_fill: Optional[TradeEvent],
    sl_triggered: bool,
) -> Trip:
    """open/close fillからTrip指標を計算して返す。"""
    if close_fill is None:
        return Trip(
            open_fill=open_fill,
            close_fill=None,
            sl_triggered=False,
            hold_time_s=0.0,
            pnl_jpy=0.0,
            mid_adverse_jpy=0.0,
            spread_captured_jpy=0.0,
        )

    hold_time_s = (close_fill.timestamp - open_fill.timestamp).total_seconds()

    # direction: BUY open → +1 (long), SELL open → -1 (short)
    direction = 1.0 if open_fill.side == "BUY" else -1.0
    size = open_fill.size

    # pnl_jpy = (close_price - open_price) * size * direction
    pnl_jpy = (close_fill.price - open_fill.price) * size * direction

    # mid_adverse: (close_mid - open_mid) の逆行成分
    # BUY(long): mid下落が逆行 → adverse = -(close_mid - open_mid) * size
    # SELL(short): mid上昇が逆行 → adverse = (close_mid - open_mid) * size
    mid_change = close_fill.mid_price - open_fill.mid_price
    mid_adverse_jpy = -mid_change * size * direction

    # spread_captured: open時の|price - mid| + close時の|price - mid|
    open_spread = abs(open_fill.price - open_fill.mid_price) * size
    close_spread = abs(close_fill.price - close_fill.mid_price) * size
    spread_captured_jpy = open_spread + close_spread

    return Trip(
        open_fill=open_fill,
        close_fill=close_fill,
        sl_triggered=sl_triggered,
        hold_time_s=hold_time_s,
        pnl_jpy=pnl_jpy,
        mid_adverse_jpy=mid_adverse_jpy,
        spread_captured_jpy=spread_captured_jpy,
    )


def build_trips(trades: list[TradeEvent]) -> list[Trip]:
    """TradeEventリストからTripリストを構築する。

    Position state machine:
    1. ORDER_FILLEDでis_close=False → open_fillキューに追加
    2. ORDER_FILLEDでis_close=True → FIFOでopen_fillとマッチ
    3. STOP_LOSS_TRIGGERED → FIFOでopen_fillとマッチ (sl_triggered=True)
    """
    # side別のopenポジションキュー (FIFO)
    open_buys: deque[TradeEvent] = deque()
    open_sells: deque[TradeEvent] = deque()
    trips: list[Trip] = []

    for event in trades:
        if event.event == "ORDER_FILLED" and event.is_close is False:
            # Open fill
            if event.side == "BUY":
                open_buys.append(event)
            elif event.side == "SELL":
                open_sells.append(event)

        elif event.event == "ORDER_FILLED" and event.is_close is True:
            # Close fill - マッチする逆サイドのopenを探す
            # BUY close → SELL openを決済, SELL close → BUY openを決済
            if event.side == "BUY" and open_sells:
                open_fill = open_sells.popleft()
                trips.append(_calc_trip_fields(open_fill, event, False))
            elif event.side == "SELL" and open_buys:
                open_fill = open_buys.popleft()
                trips.append(_calc_trip_fields(open_fill, event, False))
            else:
                logger.warning(
                    "Close fill with no matching open: %s %s @ %s",
                    event.side, event.order_id, event.timestamp,
                )

        elif event.event == "STOP_LOSS_TRIGGERED":
            # SL: BUY SL → SELL openを決済 (成行買いで決済)
            #     SELL SL → BUY openを決済 (成行売りで決済)
            if event.side == "BUY" and open_sells:
                open_fill = open_sells.popleft()
                trips.append(_calc_trip_fields(open_fill, event, True))
            elif event.side == "SELL" and open_buys:
                open_fill = open_buys.popleft()
                trips.append(_calc_trip_fields(open_fill, event, True))
            else:
                logger.warning(
                    "SL with no matching open: %s @ %s",
                    event.side, event.timestamp,
                )

    # 未クローズのポジションもTripとして記録
    for open_fill in open_buys:
        trips.append(_calc_trip_fields(open_fill, None, False))
    for open_fill in open_sells:
        trips.append(_calc_trip_fields(open_fill, None, False))

    if open_buys or open_sells:
        logger.info(
            "Unclosed positions: %d buys, %d sells",
            len(open_buys), len(open_sells),
        )

    trips.sort(key=lambda t: t.open_fill.timestamp)
    return trips


# ---------------------------------------------------------------------------
# Order Book
# ---------------------------------------------------------------------------

def build_order_book(trades: list[TradeEvent]) -> dict[str, list[TradeEvent]]:
    """order_id → イベントリストのマップを構築。

    各注文のライフサイクル（SENT→FILLED/CANCELLED）を追跡するために使用。
    """
    book: dict[str, list[TradeEvent]] = {}
    for event in trades:
        if event.order_id:
            if event.order_id not in book:
                book[event.order_id] = []
            book[event.order_id] = [*book[event.order_id], event]
    return book
