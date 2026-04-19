"""GMO公式取引履歴 PDF を真値として全分析

優先順位:
  1. GMO真P&L算出 (5日合計の絶対値)
  2. bot backtester vs GMO真値の差分検証
  3. 真の spread 捕捉率 (mid_price 比較)
  4. データ欠落・整合性監査
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

from backtester.data_loader import build_trips, load_metrics, load_trades
from backtester.market_replay import build_market_timeline, get_market_state_at

PDF_DIR = Path("/Users/okadasusumutakashi/Desktop/名称未設定フォルダ")
DATES = ["2026-04-02", "2026-04-03", "2026-04-04", "2026-04-05", "2026-04-06"]
JST = timezone(timedelta(hours=9))

ORDER_LINE_RE = re.compile(
    r"^(\d{10})\s+(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\s+BTC/JPY\s+"
    r"(新規|決済)\s+(売|買)\s+(指値|成⾏)\s+([\d.]+)\s+([\d,]+(?:\.\d+)?)\s+([\d,.\-]+)?\s*([\d,.\-]+)?$"
)
# 約定金額の後に手数料があるパターン用
ORDER_LINE_RELAXED = re.compile(
    r"^(\d{10})\s+(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\s+BTC/JPY\s+"
    r"(新規|決済)\s+(売|買)\s+(指値|成⾏)\s+([\d.]+)\s+([\d,]+(?:\.\d+)?)"
)


@dataclass(frozen=True)
class GmoOrder:
    order_id: str
    ts_jst: datetime
    ts_utc: datetime
    kbn: str            # "新規" or "決済"
    side: str           # "BUY" or "SELL"
    order_type: str     # "limit" or "market"
    size: float
    price: float        # 約定レート (JPY)
    fee: float          # 手数料


def parse_pdf(pdf_path: Path) -> list[GmoOrder]:
    """1日分の取引報告書PDFから注文を抽出。"""
    orders: list[GmoOrder] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            for line in text.split("\n"):
                m = ORDER_LINE_RELAXED.match(line)
                if not m:
                    continue
                order_id, ts_str, kbn, side_jp, order_type_jp, size_str, price_str = m.groups()
                # 末尾の手数料を抽出 (matched部分の後)
                tail = line[m.end():].strip()
                tail_parts = tail.split()
                fee = 0.0
                if tail_parts:
                    try:
                        fee = float(tail_parts[-1].replace(",", ""))
                    except ValueError:
                        fee = 0.0

                ts_jst = datetime.strptime(ts_str, "%Y/%m/%d %H:%M:%S").replace(tzinfo=JST)
                ts_utc = ts_jst.astimezone(timezone.utc)
                side = "BUY" if side_jp == "買" else "SELL"
                otype = "limit" if order_type_jp == "指値" else "market"
                price = float(price_str.replace(",", ""))
                size = float(size_str)
                orders.append(GmoOrder(
                    order_id=order_id,
                    ts_jst=ts_jst,
                    ts_utc=ts_utc,
                    kbn=kbn,
                    side=side,
                    order_type=otype,
                    size=size,
                    price=price,
                    fee=fee,
                ))
    orders.sort(key=lambda o: o.ts_utc)
    return orders


def gmo_trip_pnl(orders: list[GmoOrder]) -> tuple[float, list[dict]]:
    """GMO注文リストからFIFOマッチングで真のP&Lを算出。

    新規(open) → 決済(close) を side逆方向でマッチング。
    BUY新規 ↔ SELL決済 (longをcloseするためにsell)
    SELL新規 ↔ BUY決済 (shortをcloseするためにbuy)
    """
    open_buys: deque[GmoOrder] = deque()   # long position
    open_sells: deque[GmoOrder] = deque()  # short position
    trips: list[dict] = []
    total_pnl = 0.0
    total_fee = 0.0

    for o in orders:
        total_fee += o.fee
        if o.kbn == "新規":
            if o.side == "BUY":
                open_buys.append(o)
            else:
                open_sells.append(o)
        else:  # 決済
            if o.side == "SELL" and open_buys:  # close long
                op = open_buys.popleft()
                pnl = (o.price - op.price) * o.size  # long: close - open
                trips.append({
                    "open": op, "close": o, "side": "LONG",
                    "pnl": pnl, "hold_s": (o.ts_utc - op.ts_utc).total_seconds(),
                    "is_market_close": o.order_type == "market",
                })
                total_pnl += pnl
            elif o.side == "BUY" and open_sells:  # close short
                op = open_sells.popleft()
                pnl = (op.price - o.price) * o.size  # short: open - close
                trips.append({
                    "open": op, "close": o, "side": "SHORT",
                    "pnl": pnl, "hold_s": (o.ts_utc - op.ts_utc).total_seconds(),
                    "is_market_close": o.order_type == "market",
                })
                total_pnl += pnl

    return total_pnl - total_fee, trips


def signed_spread_at(metrics_state, side: str, price: float, size: float) -> float | None:
    """orderの約定価格と当時のmid_priceから favorable spread (JPY) を返す。"""
    if metrics_state is None or metrics_state.mid_price <= 0:
        return None
    mid = metrics_state.mid_price
    if side == "BUY":
        return (mid - price) * size  # 板の下で買えば favorable
    return (price - mid) * size      # 板の上で売れば favorable


def main() -> None:
    print("=" * 78)
    print("GMO公式取引履歴 PDF 全分析")
    print("=" * 78)

    # ------------------------------------------------------------
    # PDF読み込み
    # ------------------------------------------------------------
    pdfs: dict[str, list[GmoOrder]] = {}
    for date in DATES:
        date_compact = date.replace("-", "")
        path = PDF_DIR / f"report_{date_compact}.pdf"
        if not path.exists():
            print(f"  ✗ PDFなし: {path}")
            continue
        orders = parse_pdf(path)
        pdfs[date] = orders
        n_open = sum(1 for o in orders if o.kbn == "新規")
        n_close = sum(1 for o in orders if o.kbn == "決済")
        n_market = sum(1 for o in orders if o.order_type == "market")
        print(f"  ✓ {date}: {len(orders)}件 (新規={n_open}, 決済={n_close}, 成行={n_market})")

    # ------------------------------------------------------------
    # 1. GMO真P&L (絶対値)
    # ------------------------------------------------------------
    print()
    print("=" * 78)
    print("1. GMO真P&L (公式取引履歴ベース)")
    print("=" * 78)
    print(f"{'日付':<12}{'注文数':>8}{'Trips':>8}{'真P&L':>12}{'P&L/trip':>11}{'手数料':>10}")
    print("-" * 62)
    gmo_results: dict[str, dict] = {}
    total_truth_pnl = 0.0
    total_truth_trips = 0
    for date, orders in pdfs.items():
        pnl, trips = gmo_trip_pnl(orders)
        per_trip = pnl / len(trips) if trips else 0.0
        fee_sum = sum(o.fee for o in orders)
        print(f"{date:<12}{len(orders):>8}{len(trips):>8}{pnl:>+12.0f}{per_trip:>+11.2f}{fee_sum:>+10.0f}")
        gmo_results[date] = {"orders": orders, "trips": trips, "pnl": pnl}
        total_truth_pnl += pnl
        total_truth_trips += len(trips)
    print("-" * 62)
    avg_per_trip = total_truth_pnl / total_truth_trips if total_truth_trips else 0.0
    print(f"{'合計':<12}{sum(len(o) for o in pdfs.values()):>8}{total_truth_trips:>8}{total_truth_pnl:>+12.0f}{avg_per_trip:>+11.2f}")

    # ------------------------------------------------------------
    # 2. bot backtester vs GMO真値 比較
    # ------------------------------------------------------------
    print()
    print("=" * 78)
    print("2. bot backtester (build_trips) vs GMO真値")
    print("=" * 78)
    print(f"{'日付':<12}{'GMO真P&L':>12}{'bot calc':>12}{'差分':>10}{'GMO Trips':>11}{'bot Trips':>11}")
    print("-" * 68)
    total_bot_pnl = 0.0
    for date in DATES:
        if date not in gmo_results:
            continue
        bot_trades = load_trades(date)
        bot_trips = [t for t in build_trips(bot_trades) if t.close_fill is not None]
        bot_pnl = sum(t.pnl_jpy for t in bot_trips)
        gmo_pnl = gmo_results[date]["pnl"]
        diff = bot_pnl - gmo_pnl
        print(f"{date:<12}{gmo_pnl:>+12.0f}{bot_pnl:>+12.0f}{diff:>+10.0f}{len(gmo_results[date]['trips']):>11}{len(bot_trips):>11}")
        total_bot_pnl += bot_pnl
    print("-" * 68)
    diff_total = total_bot_pnl - total_truth_pnl
    print(f"{'合計':<12}{total_truth_pnl:>+12.0f}{total_bot_pnl:>+12.0f}{diff_total:>+10.0f}")
    print()
    accuracy = abs(diff_total) / abs(total_truth_pnl) * 100 if total_truth_pnl else 0
    print(f"  bot backtesterの誤差: {diff_total:+.0f} JPY ({accuracy:.1f}%)")

    # ------------------------------------------------------------
    # 3. 真のspread捕捉率 (mid_price比較)
    # ------------------------------------------------------------
    print()
    print("=" * 78)
    print("3. 真のspread捕捉率 (PDF約定価格 vs metrics mid_price)")
    print("=" * 78)
    print(f"{'日付':<12}{'open_avg':>11}{'close_avg':>11}{'ratio':>9}{'open_n':>8}{'close_n':>8}")
    print("-" * 59)
    all_open_spreads: list[float] = []
    all_close_spreads: list[float] = []
    for date in DATES:
        if date not in gmo_results:
            continue
        metrics = load_metrics(date)
        if not metrics:
            continue
        timeline = build_market_timeline(metrics)

        open_spreads_day = []
        close_spreads_day = []
        for trip in gmo_results[date]["trips"]:
            if trip["is_market_close"]:
                continue  # 成行closeは対象外
            op = trip["open"]
            cl = trip["close"]
            open_state = get_market_state_at(timeline, op.ts_utc)
            close_state = get_market_state_at(timeline, cl.ts_utc)
            os_val = signed_spread_at(open_state, op.side, op.price, op.size)
            cs_val = signed_spread_at(close_state, cl.side, cl.price, cl.size)
            if os_val is not None:
                open_spreads_day.append(os_val)
            if cs_val is not None:
                close_spreads_day.append(cs_val)

        if open_spreads_day and close_spreads_day:
            avg_o = sum(open_spreads_day) / len(open_spreads_day)
            avg_c = sum(close_spreads_day) / len(close_spreads_day)
            ratio = avg_c / avg_o if abs(avg_o) > 0.001 else 0
            print(f"{date:<12}{avg_o:>+11.3f}{avg_c:>+11.3f}{ratio:>+9.2f}{len(open_spreads_day):>8}{len(close_spreads_day):>8}")
            all_open_spreads.extend(open_spreads_day)
            all_close_spreads.extend(close_spreads_day)

    if all_open_spreads and all_close_spreads:
        print("-" * 59)
        avg_o = sum(all_open_spreads) / len(all_open_spreads)
        avg_c = sum(all_close_spreads) / len(all_close_spreads)
        ratio = avg_c / avg_o if abs(avg_o) > 0.001 else 0
        effective_factor = (1.0 + ratio) / 2.0
        print(f"{'合計':<12}{avg_o:>+11.3f}{avg_c:>+11.3f}{ratio:>+9.2f}{len(all_open_spreads):>8}{len(all_close_spreads):>8}")
        print()
        print(f"  実効 spread_factor = (1 + ratio) / 2 = {effective_factor:.3f}")
        print(f"  (前回の bot CSVベース計測: 0.699)")

    # ------------------------------------------------------------
    # 4. データ欠落・差分監査
    # ------------------------------------------------------------
    print()
    print("=" * 78)
    print("4. データ欠落・整合性監査 (PDF order_id ↔ bot trade.csv)")
    print("=" * 78)
    print(f"{'日付':<12}{'PDF件数':>9}{'bot件数':>9}{'PDFのみ':>9}{'botのみ':>9}{'価格不一致':>13}")
    print("-" * 61)
    for date in DATES:
        if date not in pdfs:
            continue
        bot_trades = load_trades(date)
        bot_filled = {t.order_id: t for t in bot_trades if t.event == "ORDER_FILLED" and t.order_id}
        pdf_orders = {o.order_id: o for o in pdfs[date]}

        only_pdf = set(pdf_orders) - set(bot_filled)
        only_bot = set(bot_filled) - set(pdf_orders)
        common = set(pdf_orders) & set(bot_filled)
        price_mismatch = sum(
            1 for oid in common
            if abs(pdf_orders[oid].price - bot_filled[oid].price) > 0.5
        )
        print(f"{date:<12}{len(pdf_orders):>9}{len(bot_filled):>9}{len(only_pdf):>9}{len(only_bot):>9}{price_mismatch:>13}")

    # ------------------------------------------------------------
    # 結論
    # ------------------------------------------------------------
    print()
    print("=" * 78)
    print("結論")
    print("=" * 78)
    print(f"  GMO公式 5日合計 P&L: {total_truth_pnl:+.0f} JPY")
    print(f"  日次平均: {total_truth_pnl/5:+.0f} JPY/日")
    print(f"  P&L/trip: {avg_per_trip:+.2f} JPY")
    print()
    if total_bot_pnl != 0:
        print(f"  bot backtester計算: {total_bot_pnl:+.0f} JPY (誤差 {diff_total:+.0f} JPY)")
    if all_open_spreads and all_close_spreads:
        print(f"  実効 spread_factor: {effective_factor:.3f}")


if __name__ == "__main__":
    main()
