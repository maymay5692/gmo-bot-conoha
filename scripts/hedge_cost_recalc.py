"""Recompute paper trade P&L with realistic hedge costs added.

Current paper (fr_monitor.py) counts only perp fee (0.06%*2=0.12% of notional).
Missing: spot-side fees, borrow rate (for negative-FR legs), slippage.

This script parses fr_paper_trades.csv and reapplies net P&L assumptions
based on 3 cost presets (optimistic / base / conservative).

Usage:
    python3 scripts/hedge_cost_recalc.py
    python3 scripts/hedge_cost_recalc.py --borrow-apr 10
"""
import argparse
import csv
import math
import statistics
from datetime import datetime
from pathlib import Path

PAPER_TRADES = Path(__file__).parent / "data_cache" / "fr_paper_trades.csv"


COST_MODELS = {
    "optimistic": {
        "spot_fee_bps": 10,       # 0.1% per side (Bitget spot taker)
        "slippage_bps": 20,       # 0.2% total slippage across 4 legs
        "borrow_apr": 0.05,       # 5% APR on SHORT-spot side
    },
    "base": {
        "spot_fee_bps": 10,
        "slippage_bps": 40,       # 0.4% — more realistic for altcoins
        "borrow_apr": 0.15,       # 15% APR — typical for alts on Bitget
    },
    "conservative": {
        "spot_fee_bps": 10,
        "slippage_bps": 80,       # 0.8% — thin book, extreme alt
        "borrow_apr": 0.50,       # 50% APR — high-demand coins
    },
    # MEXC 2026: all spot pairs zero-fee; futures taker 0.02% (already in perp_fee note).
    # Here spot_fee_bps=0 since mexc paper log already accounts for perp side.
    "mexc_base": {
        "spot_fee_bps": 0,
        "slippage_bps": 40,
        "borrow_apr": 0.15,
    },
    "mexc_optimistic": {
        "spot_fee_bps": 0,
        "slippage_bps": 20,
        "borrow_apr": 0.05,
    },
}


def parse_note(note: str) -> dict:
    parts = {}
    for kv in note.split(", "):
        if "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        parts[k.strip()] = float(v.replace("$", "").strip())
    return parts


def recalc(closes, opens_by_sym, cost_model):
    results = []
    spot_fee = cost_model["spot_fee_bps"] / 10000.0
    slip = cost_model["slippage_bps"] / 10000.0
    borrow_apr = cost_model["borrow_apr"]

    for close in closes:
        sym = close["symbol"]
        size = float(close["size_usd"])
        direction = close["direction"]
        # Parse original fee/price/fr components
        note = parse_note(close["note"])
        price_pnl = note.get("price_pnl", 0)
        fr_pnl = note.get("fr", 0)
        perp_fee = note.get("fee", 0)

        # Spot side fees (buy+sell spot leg)
        extra_spot_fee = size * spot_fee * 2  # round-trip
        # Slippage across 4 legs (perp in/out + spot in/out)
        slippage_cost = size * slip

        # Borrow cost only when SHORT-spot (LONG perp, negative FR case)
        borrow_cost = 0
        if direction == "LONG":
            # find matching OPEN
            opens = opens_by_sym.get(sym, [])
            # match by FIFO: find open before this close timestamp
            close_ts = datetime.fromisoformat(close["timestamp"])
            matched_open = None
            for o in opens:
                o_ts = datetime.fromisoformat(o["timestamp"])
                if o_ts <= close_ts:
                    matched_open = o
            if matched_open:
                o_ts = datetime.fromisoformat(matched_open["timestamp"])
                hours = (close_ts - o_ts).total_seconds() / 3600.0
                # Borrow: size × APR × (hours / (365×24))
                borrow_cost = size * borrow_apr * (hours / (365.0 * 24.0))

        new_pnl = price_pnl + fr_pnl - perp_fee - extra_spot_fee - slippage_cost - borrow_cost
        results.append({
            "symbol": sym,
            "direction": direction,
            "orig_pnl": float(close["pnl"]),
            "new_pnl": new_pnl,
            "added_cost": extra_spot_fee + slippage_cost + borrow_cost,
        })
    return results


def dsr_check(pnls, n_trials=10, sr_variance=0.25):
    n = len(pnls)
    if n < 2:
        return None
    m = statistics.mean(pnls)
    s = statistics.stdev(pnls)
    sr = m / s if s > 0 else 0.0
    # Skew/kurt
    mu = m
    std = statistics.pstdev(pnls)
    if std == 0:
        return {"n": n, "mean": m, "std": s, "sr": sr, "psr": 0, "dsr": 0}
    skew = sum((p - mu) ** 3 for p in pnls) / (n * std ** 3)
    kurt = sum((p - mu) ** 4 for p in pnls) / (n * std ** 4)
    # PSR
    denom = math.sqrt(max(1e-9, 1 - skew * sr + ((kurt - 1) / 4) * sr * sr))
    z = sr * math.sqrt(n - 1) / denom
    psr = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    # DSR threshold (SR*)
    euler = 0.5772156649
    # inverse CDF approx
    def inv(p):
        # Beasley-Springer
        a = [-39.69683028665376, 220.9460984245205, -275.9285104469687,
             138.3577518672690, -30.66479806614716, 2.506628277459239]
        b = [-54.47609879822406, 161.5858368580409, -155.6989798598866,
             66.80131188771972, -13.28068155288572]
        c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838,
             -2.549732539343734, 4.374664141464968, 2.938163982698783]
        d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996,
             3.754408661907416]
        pl, ph = 0.02425, 1 - 0.02425
        if p < pl:
            q = math.sqrt(-2 * math.log(p))
            return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
        if p <= ph:
            q = p - 0.5
            r = q * q
            return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    sr_star = math.sqrt(sr_variance) * ((1 - euler) * inv(1 - 1/n_trials) + euler * inv(1 - 1/(n_trials * math.e)))
    # DSR
    z2 = (sr - sr_star) * math.sqrt(n - 1) / denom
    dsr = 0.5 * (1 + math.erf(z2 / math.sqrt(2)))
    return {"n": n, "mean": m, "std": s, "sr": sr, "skew": skew, "kurt": kurt,
            "psr": psr, "dsr": dsr, "sr_star": sr_star}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=str(PAPER_TRADES))
    ap.add_argument("--borrow-apr", type=float, default=None,
                    help="Override borrow APR for all models")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.path)))
    opens = [r for r in rows if r["action"] == "OPEN"]
    closes = [r for r in rows if r["action"] == "CLOSE"]
    opens_by_sym = {}
    for o in opens:
        opens_by_sym.setdefault(o["symbol"], []).append(o)

    print(f"Loaded {len(closes)} CLOSE trades from {args.path}\n")

    # Baseline (as-logged)
    orig_pnls = [float(r["pnl"]) for r in closes]
    baseline_stats = dsr_check(orig_pnls)
    print(f"=== Baseline (as-logged, no extra hedge costs) ===")
    print(f"  Total P&L:  ${sum(orig_pnls):.2f}   n={len(orig_pnls)}   mean=${sum(orig_pnls)/len(orig_pnls):.3f}")
    print(f"  Sharpe: {baseline_stats['sr']:.3f}  PSR: {baseline_stats['psr']:.3f}  DSR: {baseline_stats['dsr']:.3f}  (SR*={baseline_stats['sr_star']:.3f})")
    print()

    # Apply each cost model
    for name, model in COST_MODELS.items():
        if args.borrow_apr is not None:
            model = {**model, "borrow_apr": args.borrow_apr}
        results = recalc(closes, opens_by_sym, model)
        pnls = [r["new_pnl"] for r in results]
        cost_total = sum(r["added_cost"] for r in results)
        stats = dsr_check(pnls)
        print(f"=== Cost model: {name}  "
              f"(spot_fee={model['spot_fee_bps']}bps, slip={model['slippage_bps']}bps, borrow={model['borrow_apr']*100:.0f}% APR) ===")
        print(f"  Total P&L:  ${sum(pnls):.2f}   net change: -${cost_total:.2f}   mean=${sum(pnls)/len(pnls):.3f}")
        wins = sum(1 for p in pnls if p > 0)
        print(f"  Win rate:   {wins}/{len(pnls)} = {wins/len(pnls)*100:.0f}%")
        print(f"  Sharpe: {stats['sr']:.3f}  PSR: {stats['psr']:.3f}  DSR: {stats['dsr']:.3f}  (SR*={stats['sr_star']:.3f})")
        # Verdict
        gate1 = (stats['psr'] >= 0.95) and (stats['dsr'] >= 0.95)
        print(f"  Gate 1: {'PASS' if gate1 else 'FAIL'}")
        print()


if __name__ == "__main__":
    main()
