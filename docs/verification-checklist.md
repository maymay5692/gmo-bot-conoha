# Standardized Version Verification Checklist

Every bot version update MUST be evaluated using this fixed set of metrics.
Use `scripts/verify_version.py` to compute all metrics automatically.

## Usage

```bash
# Fetch and analyze single day
python scripts/verify_version.py --fetch --date 2026-02-19 --version v0.10.0

# Analyze multiple days (aggregated)
python scripts/verify_version.py --date 2026-02-19 --date 2026-02-20 --version v0.10.0

# Compare two versions
python scripts/verify_version.py --compare .cache/verify-v0.9.5-2026-02-17.json .cache/verify-v0.10.0-2026-02-19.json

# Phase-specific judgment (shows pass/fail criteria)
python scripts/verify_version.py --fetch --date 2026-02-22 --version v0.12.1 --phase 3-0
```

## A. Operational Summary

| # | Metric | Calculation | Source |
|---|--------|------------|--------|
| A1 | Uptime (h) | last_timestamp - first_timestamp | trades |
| A2 | Total events | Row count | trades |
| A3 | Cycles | Row count | metrics |

## B. Order Flow

| # | Metric | Calculation | Source |
|---|--------|------------|--------|
| B1 | ORDER_SENT | Count of event="ORDER_SENT" | trades |
| B2 | ORDER_FILLED | Count of event="ORDER_FILLED" | trades |
| B3 | ORDER_CANCELLED | Count of event="ORDER_CANCELLED" | trades |
| B4 | ORDER_FAILED | Count of event="ORDER_FAILED" | trades |
| B5 | STOP_LOSS_TRIGGERED | Count of event="STOP_LOSS_TRIGGERED" | trades |
| B6 | Fill Rate (%) | B2 / B1 x 100 | |
| B7 | Open Fill Rate (%) | is_close=false FILLED / SENT x 100 | |
| B8 | Close Fill Rate (%) | is_close=true FILLED / SENT x 100 | |
| B9 | BUY Fill Rate (%) | side=BUY FILLED / SENT x 100 | |
| B10 | SELL Fill Rate (%) | side=SELL FILLED / SENT x 100 | |

**Judgment**: Fill rate drop >5pp from previous version = investigate SOK rejection or spread config.

## C. P&L

| # | Metric | Calculation | Source |
|---|--------|------------|--------|
| C1 | Collateral start (JPY) | First positive collateral value | metrics |
| C2 | Collateral end (JPY) | Last positive collateral value | metrics |
| C3 | P&L (JPY) | C2 - C1 | |
| C4 | P&L (%) | C3 / C1 x 100 | |
| C5 | Max Drawdown (JPY) | Peak-to-trough in collateral series | metrics |
| C6 | P&L per hour (JPY/h) | C3 / A1 | |

**Judgment**: C6 improving = good. C5 > 1000 JPY = high risk.

## D. Trip Analysis (FIFO Matched)

| # | Metric | Calculation | Source |
|---|--------|------------|--------|
| D1 | Completed trips | FIFO-matched open+close fill pairs | trades |
| D2 | P&L/trip (JPY) | Average (sell_price - buy_price) x size | trades |
| D3 | Spread capture/trip (JPY) | Sum of |fill_price - mid| for both legs / trips | trades |
| D4 | Mid adverse/trip (JPY) | Average mid movement against position x size | trades |
| D5 | Win rate (%) | Trips with P&L > 0 / D1 x 100 | |
| D6 | Avg hold time (s) | Average close_ts - open_ts | trades |
| D7 | Median hold time (s) | Median of above | trades |
| D8 | Hold distribution | Buckets: 0-5s, 5-10s, 10-30s, 30-120s, 120s+ | trades |
| D9 | Unmatched opens | Open fills without matching close | trades |
| D10 | Unmatched closes | Close fills without matching open | trades |
| D11 | Trips/hour | D1 / A1 | |

**Judgment**:
- D2 > 0 = profitable per trip (target)
- D3 > |D4| = spread capture exceeds adverse selection (healthy)
- D5 > 50% = more winning trips than losing

## E. Market Environment

| # | Metric | Calculation | Source |
|---|--------|------------|--------|
| E1 | Avg mid price (JPY) | Mean of mid_price | metrics |
| E2 | Avg volatility | Mean of volatility | metrics |
| E3 | Avg sigma_1s | Mean of sigma_1s | metrics |
| E4 | Avg spread_pct | Mean of (buy_spread_pct + sell_spread_pct) / 2 | metrics |
| E5 | Avg t_optimal_ms | Mean of t_optimal_ms | metrics |
| E6 | Avg best_ev | Mean of best_ev | metrics |

**Judgment**: When comparing versions, E1-E3 differences indicate market regime change.
Normalize P&L comparisons by E2 (volatility) when market conditions differ significantly.

## F. Errors & Anomalies

| # | Metric | Calculation | Source |
|---|--------|------------|--------|
| F1 | ERR-201 (Margin) | Failed orders with ERR-201 | trades |
| F2 | ERR-422 (Ghost) | Failed orders with ERR-422 | trades |
| F3 | ERR-5003 (SOK) | Failed orders with ERR-5003 | trades |
| F4 | ERR-5122 (Already filled) | Failed orders with ERR-5122 | trades |
| F5 | Stop-loss total (JPY) | Sum of unrealized_pnl from STOP_LOSS events | trades |

**Judgment**:
- F1 > 0 = margin issues, may need to reduce position size
- F3 increasing = SOK rejections high, consider spread adjustment
- F5 < -100 JPY = stop-loss dominating losses

## G. Stop-Loss Detailed Analysis

| # | Metric | Calculation | Purpose |
|---|--------|------------|---------|
| G1 | SL count/hour | B5 / A1 | SL frequency normalized by uptime |
| G2 | SL loss/event (JPY) | F5 / B5 | Average loss per SL event |
| G3 | SL impact/trip (JPY) | F5 / D1 | SL cost per completed trip |
| G4 | P&L ex-SL/trip (JPY) | D2 - G3 | Structural profitability excluding SL |
| G5 | SL recovery trips | abs(G2) / G4 (when G4>0) | Trips needed to recover from one SL |
| G6 | Max single SL loss (JPY) | min(unrealized_pnl per SL event) | Worst-case single SL loss |

**Judgment**:
- G1 < 0.5/h = SL frequency acceptable
- G3 > -0.50 JPY = SL cost per trip manageable
- G4 > 0 = structurally profitable when excluding SL
- G5 < 30 = can recover from SL within reasonable number of trips

**Baselines (v0.12.1, 2026-02-22)**:
- G1: 0.94/h, G2: -19.85 JPY, G3: -1.11 JPY, G4: +0.45 JPY, G5: 44.1 trips

## Phase 3-0 Judgment Criteria (SL Threshold)

**Config change**: stop_loss_jpy: -10 -> -15

**Monitoring (1h intervals)**:
- G1 < 0.5/h (baseline: 0.94) -> SL frequency halved
- G3 > -0.50 JPY/trip (baseline: -1.11) -> SL cost halved

**Success (after 24h, 300+ trips, 3+ SL events)**:
- D2 > -0.30 (baseline: -0.66) -> P&L/trip improved
- C6 > -15 JPY/h (baseline: -26.5) -> P&L/h improved
- G4 > +0.30 maintained (baseline: +0.45) -> structural profit preserved

**Rollback triggers**:
- C5 > 1500 JPY -> revert to SL -10 immediately
- D2 < -1.0 -> revert within 24h
- D6 > 600s -> investigate bug

**Usage**:
```bash
python scripts/verify_version.py --fetch --date YYYY-MM-DD --version v0.12.2 --phase 3-0
```

## Version Comparison Guidelines

1. **Minimum data**: 24h of data covering all sessions (Asia, Europe, US)
2. **Market normalization**: If E2 (volatility) differs >30%, normalize P&L by volatility
3. **Improvement threshold**: D2 (P&L/trip) improvement >0.5 JPY = significant
4. **Degradation threshold**: B6 (fill rate) drop >5pp = investigate immediately
5. **Go/No-go**: C3 positive after 48h = continue. C3 < -1000 JPY after 24h = revert
