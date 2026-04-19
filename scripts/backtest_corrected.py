"""補正版バックテスト — GMO真値ベース + SL slippage 補正

修正点:
  1. baseline: GMO PDF からの真P&L を使用 (-864 JPY/5日)
  2. SL execution price: 真の slippage を PDF から算出して適用
  3. D/F simulation の early_sl return 値を slippage 込みに

手順:
  - 各SLについて GMO PDF の真の P&L と bot の unrealized_pnl を比較
  - avg slippage を算出
  - D/F simulation で early_sl の return 値を (-15 + slippage) に修正
"""
from __future__ import annotations

import re
import sys
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pdfplumber

SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

from backtester.data_loader import Trip, build_trips, load_metrics, load_trades
from backtester.dsr import evaluate_dsr
from backtester.market_replay import MarketState, build_market_timeline

PDF_DIR = Path("/Users/okadasusumutakashi/Desktop/名称未設定フォルダ")
DATES = ["2026-04-02", "2026-04-03", "2026-04-04", "2026-04-05", "2026-04-06"]
JST = timezone(timedelta(hours=9))

SL_TRIGGER_JPY = -15.0  # 検知閾値 (変更なし)
TP_SWEEP = [3.0, 4.0, 5.0, 6.0, 7.0]
F_MAX_HOLDS = [180, 300, 600]
SPREAD_FACTOR = 0.765  # PDF実測値

ORDER_LINE_RE = re.compile(
    r"^(\d{10})\s+(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\s+BTC/JPY\s+"
    r"(新規|決済)\s+(売|買)\s+(指値|成⾏)\s+([\d.]+)\s+([\d,]+(?:\.\d+)?)"
)


@dataclass(frozen=True)
class GmoOrder:
    order_id: str
    ts_utc: datetime
    kbn: str
    side: str
    order_type: str  # limit/market
    size: float
    price: float


def parse_pdf(path: Path) -> list[GmoOrder]:
    orders: list[GmoOrder] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            for line in text.split("\n"):
                m = ORDER_LINE_RE.match(line)
                if not m:
                    continue
                oid, ts_str, kbn, side_jp, otype_jp, size_str, price_str = m.groups()
                ts_jst = datetime.strptime(ts_str, "%Y/%m/%d %H:%M:%S").replace(tzinfo=JST)
                ts_utc = ts_jst.astimezone(timezone.utc)
                orders.append(GmoOrder(
                    order_id=oid,
                    ts_utc=ts_utc,
                    kbn=kbn,
                    side="BUY" if side_jp == "買" else "SELL",
                    order_type="limit" if otype_jp == "指値" else "market",
                    size=float(size_str),
                    price=float(price_str.replace(",", "")),
                ))
    orders.sort(key=lambda o: o.ts_utc)
    return orders


def gmo_trips(orders: list[GmoOrder]) -> list[dict]:
    """FIFO matching でGMO trip 構築。"""
    open_buys: deque[GmoOrder] = deque()
    open_sells: deque[GmoOrder] = deque()
    trips: list[dict] = []
    for o in orders:
        if o.kbn == "新規":
            (open_buys if o.side == "BUY" else open_sells).append(o)
        else:
            if o.side == "SELL" and open_buys:
                op = open_buys.popleft()
                pnl = (o.price - op.price) * o.size
                trips.append({"open": op, "close": o, "pnl": pnl, "is_market": o.order_type == "market"})
            elif o.side == "BUY" and open_sells:
                op = open_sells.popleft()
                pnl = (op.price - o.price) * o.size
                trips.append({"open": op, "close": o, "pnl": pnl, "is_market": o.order_type == "market"})
    return trips


def compute_sl_slippage() -> tuple[float, int, list[float]]:
    """全SLについて GMO真P&L と bot unrealized_pnl の差を算出。

    Returns:
        (avg_slippage_jpy, sl_count, slippage_list)
    """
    slippages: list[float] = []
    for date in DATES:
        # PDF の成行decisive close 群を取得
        path = PDF_DIR / f"report_{date.replace('-', '')}.pdf"
        if not path.exists():
            continue
        gmo_orders = parse_pdf(path)
        gtrips = gmo_trips(gmo_orders)
        # 成行close = SL trip
        sl_gtrips = [t for t in gtrips if t["is_market"]]

        # bot の SL trip
        bot_trades = load_trades(date)
        bot_trips = [t for t in build_trips(bot_trades) if t.sl_triggered and t.close_fill is not None]

        # FIFO で対応 (時刻順マッチング)
        sl_gtrips.sort(key=lambda t: t["close"].ts_utc)
        bot_trips.sort(key=lambda t: t.close_fill.timestamp)

        n = min(len(sl_gtrips), len(bot_trips))
        for i in range(n):
            true_pnl = sl_gtrips[i]["pnl"]
            bot_pnl = bot_trips[i].pnl_jpy
            slippage = true_pnl - bot_pnl  # 負なら真値の方が悪い
            slippages.append(slippage)

    if slippages:
        avg = sum(slippages) / len(slippages)
        return (avg, len(slippages), slippages)
    return (0.0, 0, [])


def trip_open_spread_jpy(trip: Trip) -> float:
    size = trip.open_fill.size
    mid = trip.open_fill.mid_price
    price = trip.open_fill.price
    if trip.open_fill.side == "BUY":
        return (mid - price) * size
    return (price - mid) * size


def simulate_d(
    trip: Trip,
    timeline: list[MarketState],
    profit_target: float,
    spread_factor: float,
    sl_return_jpy: float,
) -> float:
    """D案: min_hold無効化, TP/SL early close。"""
    if trip.close_fill is None:
        return trip.pnl_jpy

    open_ts = trip.open_fill.timestamp
    close_ts = trip.close_fill.timestamp
    open_mid = trip.open_fill.mid_price
    direction = 1.0 if trip.open_fill.side == "BUY" else -1.0
    size = trip.open_fill.size
    open_spread = trip_open_spread_jpy(trip)
    spread_cap = 2.0 * open_spread * spread_factor

    for state in timeline:
        if state.timestamp <= open_ts:
            continue
        if state.timestamp > close_ts:
            break
        mid_change = state.mid_price - open_mid
        unrealized = mid_change * size * direction + spread_cap
        if unrealized <= SL_TRIGGER_JPY:
            return sl_return_jpy  # 補正版
        if unrealized >= profit_target:
            return unrealized

    # フォールバック: 履歴値を spread_factor 補正
    if trip.sl_triggered:
        return trip.pnl_jpy
    delta = spread_cap - trip.spread_captured_jpy
    return trip.pnl_jpy + delta


def simulate_f(
    trip: Trip,
    timeline: list[MarketState],
    profit_target: float,
    max_hold_s: float,
    spread_factor: float,
    sl_return_jpy: float,
) -> float:
    """F案: D + max_hold."""
    if trip.close_fill is None:
        return trip.pnl_jpy

    open_ts = trip.open_fill.timestamp
    close_ts = trip.close_fill.timestamp
    open_mid = trip.open_fill.mid_price
    direction = 1.0 if trip.open_fill.side == "BUY" else -1.0
    size = trip.open_fill.size
    open_spread = trip_open_spread_jpy(trip)
    spread_cap = 2.0 * open_spread * spread_factor

    last_unrealized = 0.0
    last_has_state = False
    for state in timeline:
        if state.timestamp <= open_ts:
            continue
        if state.timestamp > close_ts:
            break
        elapsed = (state.timestamp - open_ts).total_seconds()
        mid_change = state.mid_price - open_mid
        unrealized = mid_change * size * direction + spread_cap
        if unrealized <= SL_TRIGGER_JPY:
            return sl_return_jpy
        if unrealized >= profit_target:
            return unrealized
        if elapsed >= max_hold_s:
            return unrealized
        last_unrealized = unrealized
        last_has_state = True

    if last_has_state:
        return last_unrealized
    if trip.sl_triggered:
        return trip.pnl_jpy
    delta = spread_cap - trip.spread_captured_jpy
    return trip.pnl_jpy + delta


def main() -> None:
    print("=" * 78)
    print("補正版バックテスト — GMO真値ベース + SL slippage 補正")
    print("=" * 78)

    # ------------------------------------------------------------
    # SL slippage 算出
    # ------------------------------------------------------------
    print()
    print("=" * 78)
    print("Step 1: SL slippage 算出 (PDF真値 vs bot unrealized_pnl)")
    print("=" * 78)
    avg_slip, n_sl, slips = compute_sl_slippage()
    if n_sl == 0:
        print("  SL trip なし。中止")
        return

    sorted_slips = sorted(slips)
    print(f"  SL件数: {n_sl}")
    print(f"  avg slippage: {avg_slip:+.2f} JPY")
    print(f"  median: {sorted_slips[n_sl//2]:+.2f} JPY")
    print(f"  P25: {sorted_slips[n_sl//4]:+.2f} JPY")
    print(f"  P75: {sorted_slips[3*n_sl//4]:+.2f} JPY")
    print(f"  min: {min(slips):+.2f} / max: {max(slips):+.2f}")

    sl_return_jpy = SL_TRIGGER_JPY + avg_slip  # -15 + slippage
    print()
    print(f"  → 補正後の early_sl return 値: {sl_return_jpy:.2f} JPY")
    print(f"    (検知 -15.0 + slippage {avg_slip:+.2f})")

    # ------------------------------------------------------------
    # GMO真値 baseline
    # ------------------------------------------------------------
    print()
    print("=" * 78)
    print("Step 2: GMO真値 baseline (5日合計)")
    print("=" * 78)
    total_truth = 0.0
    total_trips = 0
    for date in DATES:
        path = PDF_DIR / f"report_{date.replace('-', '')}.pdf"
        if not path.exists():
            continue
        orders = parse_pdf(path)
        gtrips = gmo_trips(orders)
        pnl = sum(t["pnl"] for t in gtrips)
        total_truth += pnl
        total_trips += len(gtrips)
        print(f"  {date}: {len(gtrips):>4} trips, P&L={pnl:+.0f} JPY")
    print(f"  合計: {total_trips} trips, P&L={total_truth:+.0f} JPY")
    truth_per_trip = total_truth / total_trips if total_trips else 0
    print(f"  P&L/trip = {truth_per_trip:+.2f}, 日次平均 = {total_truth/5:+.0f} JPY/日")

    # ------------------------------------------------------------
    # D/F案 簡易比較用に bot trip + timeline をロード
    # ------------------------------------------------------------
    matched: list[Trip] = []
    timeline: list[MarketState] = []
    for date in DATES:
        bot_trades = load_trades(date)
        metrics = load_metrics(date)
        if not bot_trades or not metrics:
            continue
        trips = build_trips(bot_trades)
        matched.extend(t for t in trips if t.close_fill is not None)
        timeline.extend(build_market_timeline(metrics))
    timeline.sort(key=lambda s: s.timestamp)

    n_bot_trips = len(matched)

    # ------------------------------------------------------------
    # D案 補正版
    # ------------------------------------------------------------
    print()
    print("=" * 78)
    print("Step 3: D案 補正版 (factor=0.765, SL return=" f"{sl_return_jpy:.2f})")
    print("=" * 78)
    print(f"GMO真値 baseline: {total_truth:+.0f} JPY")
    print()
    print(f"{'TP':>5}{'P&L':>10}{'P&L/trip':>11}{'差':>11}{'SR':>8}{'DSR':>8}{'有意':>6}")
    print("-" * 59)
    n_trials = len(TP_SWEEP)
    best_d_tp = None
    best_d_pnl = float("-inf")
    for tp in TP_SWEEP:
        pnls = [simulate_d(t, timeline, tp, SPREAD_FACTOR, sl_return_jpy) for t in matched]
        total = sum(pnls)
        per_trip = total / n_bot_trips
        delta = total - total_truth
        dsr_eval = evaluate_dsr(pnls, N=n_trials)
        mark = "✓" if dsr_eval["significant"] else "-"
        print(
            f"{int(tp):>5}{total:>+10.0f}{per_trip:>+11.2f}{delta:>+11.0f}"
            f"{dsr_eval['sr_best']:>+8.3f}{dsr_eval['dsr']:>8.2f}{mark:>6}"
        )
        if total > best_d_pnl:
            best_d_pnl = total
            best_d_tp = tp

    # ------------------------------------------------------------
    # F案 補正版
    # ------------------------------------------------------------
    print()
    print("=" * 78)
    print("Step 4: F案 補正版 (factor=0.765, SL return=" f"{sl_return_jpy:.2f})")
    print("=" * 78)
    print(f"GMO真値 baseline: {total_truth:+.0f} JPY")
    print()
    print(f"{'TP':>4}{'max_hold':>10}{'P&L':>10}{'P&L/trip':>11}{'差':>11}{'SR':>8}{'DSR':>8}{'有意':>6}")
    print("-" * 68)
    n_trials_f = len([3.0, 5.0, 7.0]) * len(F_MAX_HOLDS)
    best_f = None
    best_f_pnl = float("-inf")
    for tp in [3.0, 5.0, 7.0]:
        for mh in F_MAX_HOLDS:
            pnls = [simulate_f(t, timeline, tp, float(mh), SPREAD_FACTOR, sl_return_jpy) for t in matched]
            total = sum(pnls)
            per_trip = total / n_bot_trips
            delta = total - total_truth
            dsr_eval = evaluate_dsr(pnls, N=n_trials_f)
            mark = "✓" if dsr_eval["significant"] else "-"
            print(
                f"{int(tp):>4}{mh:>10}{total:>+10.0f}{per_trip:>+11.2f}{delta:>+11.0f}"
                f"{dsr_eval['sr_best']:>+8.3f}{dsr_eval['dsr']:>8.2f}{mark:>6}"
            )
            if total > best_f_pnl:
                best_f_pnl = total
                best_f = (tp, mh)

    # ------------------------------------------------------------
    # 結論
    # ------------------------------------------------------------
    print()
    print("=" * 78)
    print("結論")
    print("=" * 78)
    print(f"  GMO真値 baseline: {total_truth:+.0f} JPY (5日, 日次 {total_truth/5:+.0f})")
    print()
    print(f"  D案最良: TP={int(best_d_tp)} → P&L={best_d_pnl:+.0f} JPY")
    print(f"           改善 {best_d_pnl - total_truth:+.0f} JPY (日次 {(best_d_pnl - total_truth)/5:+.0f}/日)")
    print(f"           絶対値 {best_d_pnl/5:+.0f} JPY/日")
    print()
    print(f"  F案最良: TP={int(best_f[0])}, max_hold={best_f[1]}s → P&L={best_f_pnl:+.0f} JPY")
    print(f"           改善 {best_f_pnl - total_truth:+.0f} JPY (日次 {(best_f_pnl - total_truth)/5:+.0f}/日)")
    print(f"           絶対値 {best_f_pnl/5:+.0f} JPY/日")
    print()
    if best_f_pnl > 0:
        print("  ★ F案で黒字化見込み")
    elif best_f_pnl > total_truth:
        print(f"  △ F案で改善するが赤字 ({best_f_pnl/5:+.0f} JPY/日)")
    else:
        print("  ❌ 改善なし")


if __name__ == "__main__":
    main()
