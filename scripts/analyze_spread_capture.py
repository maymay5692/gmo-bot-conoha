"""spread_capture 実測分析

目的: D案・F案シミュレーションで使用した spread_factor の妥当性を検証する。
     過去ログから「実際の close 指値の spread 捕捉率」を測定し、
     保守(0.5) vs 楽観(1.0) のどちらが現実に近いかを判定する。

測定項目:
1. open 側の spread 捕捉 (JPY/trip): 既に約定したopen fillのmid-price乖離
2. close 側の spread 捕捉 (JPY/trip): 実際に約定したclose fillのmid-price乖離 (符号付き)
3. 比率 close_spread / open_spread (同trip内)
4. SL trip と 通常close trip を分離
5. close_spread > 0 (favorable) の trip 比率

シミュレーション式の検証:
  simulated_unrealized = mid_change * size * direction + spread_captured
  ここで spread_captured = open_spread + close_spread (JPY)

  もし close_spread ≈ open_spread なら factor=1.0 が妥当
  もし close_spread ≈ 0 なら factor=0.5 相当
  もし close_spread < 0 なら factor<0.5 で実質マイナス捕捉
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

from backtester.data_loader import Trip, build_trips, load_trades

DATES = ["2026-04-02", "2026-04-03", "2026-04-04", "2026-04-05", "2026-04-06"]


def signed_open_spread(trip: Trip) -> float:
    """open 側の favorable spread (JPY, 符号付き)。

    BUY open: 板の下で買えれば favorable → (mid - price) * size
    SELL open: 板の上で売れれば favorable → (price - mid) * size
    """
    size = trip.open_fill.size
    mid = trip.open_fill.mid_price
    price = trip.open_fill.price
    if trip.open_fill.side == "BUY":
        return (mid - price) * size
    return (price - mid) * size


def signed_close_spread(trip: Trip) -> float:
    """close 側の favorable spread (JPY, 符号付き)。

    BUY close (SELL openのclose): 板の下で買えれば favorable → (mid - price) * size
    SELL close (BUY openのclose): 板の上で売れれば favorable → (price - mid) * size
    """
    if trip.close_fill is None:
        return 0.0
    size = trip.close_fill.size
    mid = trip.close_fill.mid_price
    price = trip.close_fill.price
    if trip.close_fill.side == "BUY":
        return (mid - price) * size
    return (price - mid) * size


def summarize(name: str, values: list[float]) -> None:
    if not values:
        print(f"  {name}: データなし")
        return
    n = len(values)
    mean = statistics.mean(values)
    median = statistics.median(values)
    stdev = statistics.stdev(values) if n >= 2 else 0.0
    pos = sum(1 for v in values if v > 0)
    neg = sum(1 for v in values if v < 0)
    zero = n - pos - neg
    print(
        f"  {name}: n={n}  mean={mean:+.3f}  median={median:+.3f}  std={stdev:.3f}"
    )
    print(
        f"    favorable(>0): {pos} ({pos/n*100:.1f}%)  "
        f"zero: {zero}  unfavorable(<0): {neg} ({neg/n*100:.1f}%)"
    )


def load_all_trips() -> list[Trip]:
    all_trips: list[Trip] = []
    for date in DATES:
        trades = load_trades(date)
        if not trades:
            continue
        trips = build_trips(trades)
        all_trips.extend(t for t in trips if t.close_fill is not None)
    return all_trips


def main() -> None:
    print("=" * 78)
    print("spread_capture 実測分析")
    print("=" * 78)
    print(f"対象日: {DATES[0]} ~ {DATES[-1]}")
    print()

    trips = load_all_trips()
    print(f"全trip数 (closed): {len(trips)}")
    print()

    normal_trips = [t for t in trips if not t.sl_triggered]
    sl_trips = [t for t in trips if t.sl_triggered]
    print(f"  通常close: {len(normal_trips)}")
    print(f"  SL発動: {len(sl_trips)}")
    print()

    # ------------------------------------------------------------
    # 1. open/close 側の spread 分布
    # ------------------------------------------------------------
    print("=" * 78)
    print("1. 通常close trip の spread 捕捉分布")
    print("=" * 78)
    open_spreads = [signed_open_spread(t) for t in normal_trips]
    close_spreads = [signed_close_spread(t) for t in normal_trips]
    total_spreads = [o + c for o, c in zip(open_spreads, close_spreads)]

    summarize("open_spread (JPY)", open_spreads)
    summarize("close_spread (JPY)", close_spreads)
    summarize("total (open+close)", total_spreads)
    print()

    # ------------------------------------------------------------
    # 2. 比率分析
    # ------------------------------------------------------------
    print("=" * 78)
    print("2. close/open 比率 (通常closeのみ)")
    print("=" * 78)
    ratios = [
        c / o for o, c in zip(open_spreads, close_spreads)
        if abs(o) > 0.001
    ]
    if ratios:
        ratios_sorted = sorted(ratios)
        n = len(ratios)
        print(f"  n={n}")
        print(f"  mean ratio: {statistics.mean(ratios):+.3f}")
        print(f"  median ratio: {statistics.median(ratios):+.3f}")
        print(f"  P25: {ratios_sorted[n//4]:+.3f}")
        print(f"  P75: {ratios_sorted[3*n//4]:+.3f}")
    print()

    # ------------------------------------------------------------
    # 3. 実効 spread_factor の推定
    # ------------------------------------------------------------
    print("=" * 78)
    print("3. D案シミュレーションでの実効 spread_factor 推定")
    print("=" * 78)
    print()
    print("simulated_unrealized = mid_change*size*dir + (open_spread + close_spread) * factor")
    print()
    print("factor=1.0 を仮定した場合、実際の spread_captured は:")
    total_open = sum(open_spreads)
    total_close = sum(close_spreads)
    total_sum = total_open + total_close
    print(f"  open 合計: {total_open:+.2f} JPY")
    print(f"  close 合計: {total_close:+.2f} JPY")
    print(f"  total 合計: {total_sum:+.2f} JPY")
    print()

    # 実効係数: 通常close trip の close_spread が open_spread と同じなら factor=1.0
    # close_spread が 0 なら factor = open_only = 0.5
    # close_spread が負なら factor < 0.5
    if total_open > 0:
        effective_factor = total_sum / (total_open * 2)  # 2*open_sum = 楽観想定total
        print(f"  実効 factor (close==open 仮定時の1.0基準): {effective_factor:.3f}")
    print()

    # ------------------------------------------------------------
    # 4. SL trip との比較
    # ------------------------------------------------------------
    print("=" * 78)
    print("4. SL trip の spread (参考)")
    print("=" * 78)
    if sl_trips:
        sl_open = [signed_open_spread(t) for t in sl_trips]
        sl_close = [signed_close_spread(t) for t in sl_trips]
        summarize("SL open_spread", sl_open)
        summarize("SL close_spread", sl_close)
        print()
        print("  注: SLの close_spread は error='unrealized_pnl=...' から抽出した実損益とは別物")
        print("  (SL時の price フィールドは実約定価格ではないため信頼性低い)")
    print()

    # ------------------------------------------------------------
    # 5. 日別集計
    # ------------------------------------------------------------
    print("=" * 78)
    print("5. 日別集計 (通常close trip のみ)")
    print("=" * 78)
    print(f"{'日付':<12}{'Trips':>7}{'avg_open':>11}{'avg_close':>11}{'ratio':>9}")
    print("-" * 50)
    for date in DATES:
        trades = load_trades(date)
        if not trades:
            continue
        day_trips = [t for t in build_trips(trades) if t.close_fill is not None and not t.sl_triggered]
        if not day_trips:
            continue
        os_list = [signed_open_spread(t) for t in day_trips]
        cs_list = [signed_close_spread(t) for t in day_trips]
        avg_o = sum(os_list) / len(os_list)
        avg_c = sum(cs_list) / len(cs_list)
        ratio = avg_c / avg_o if abs(avg_o) > 0.001 else 0.0
        print(f"{date:<12}{len(day_trips):>7}{avg_o:>+11.3f}{avg_c:>+11.3f}{ratio:>+9.2f}")
    print()

    # ------------------------------------------------------------
    # 6. 結論とシミュレーション補正
    # ------------------------------------------------------------
    print("=" * 78)
    print("6. 結論")
    print("=" * 78)
    pos_close = sum(1 for c in close_spreads if c > 0)
    favorable_pct = pos_close / len(close_spreads) * 100 if close_spreads else 0
    avg_open = sum(open_spreads) / len(open_spreads) if open_spreads else 0
    avg_close = sum(close_spreads) / len(close_spreads) if close_spreads else 0

    print(f"  通常close trip の平均:")
    print(f"    open_spread: {avg_open:+.3f} JPY/trip")
    print(f"    close_spread: {avg_close:+.3f} JPY/trip")
    print(f"    close favorable 比率: {favorable_pct:.1f}%")
    print()

    if avg_open > 0:
        implied_factor = (avg_open + avg_close) / (2 * avg_open)
        print(f"  実効 spread_factor = (avg_open + avg_close) / (2 * avg_open)")
        print(f"                    = ({avg_open:+.3f} + {avg_close:+.3f}) / ({2*avg_open:+.3f})")
        print(f"                    = {implied_factor:.3f}")
        print()

        if implied_factor >= 0.9:
            verdict = "楽観前提(1.0)が妥当。D案シミュの P&L は信頼できる"
        elif implied_factor >= 0.7:
            verdict = "楽観と保守の中間。D案シミュ P&L は 70-90% ディスカウントして評価すべき"
        elif implied_factor >= 0.5:
            verdict = "保守前提(0.5)が妥当。D案シミュの P&L は半額程度と見るべき"
        else:
            verdict = "close側で実質マイナス捕捉。D案シミュは過大評価、追加補正が必要"
        print(f"  判定: {verdict}")
    print()


if __name__ == "__main__":
    main()
