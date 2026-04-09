# Counterfactual Close Fill Model — Design Spec

**Date**: 2026-04-10
**Replaces**: Brownian `calc_fill_prob` in `close_fill_sim.py`

## Problem

Brownian fill model `2Φ(-d/(σ√t))` overestimates per-tick fill probability by ~130x
(Brownian 0.39/tick vs empirical effective rate 0.003/tick). Three root causes:

1. **Fill rate 35x overcount** — bot sends close orders every ~107s (1/35.5 ticks),
   sim checks every 3s tick
2. **SL detection mismatch** — metrics 3s snapshots don't match bot's actual SL timing;
   45% of non-SL trips cross -15 in metrics without SL trigger
3. **Expected value mode bias** — timeline extends hours beyond trip, accumulating
   positive spread-capture P&L indefinitely

No combination of per-tick fill rate, SL threshold, or timeline truncation achieves
both P&L ±30% and SL ±5pp simultaneously in expected value mode.

## Solution — Counterfactual Close Price Model

Replace expected-value per-tick simulation with a **deterministic counterfactual model**
that uses actual trip outcomes as anchors and varies only the close price calculation.

### Core Principle

> "What P&L would each trip produce if we had used factor X instead of factor Y?"

For the **baseline** parameters (factor=0.4, min_hold=180):
- Fill trips: counterfactual close_price = actual close_price → P&L matches exactly
- SL trips: SL P&L is mid-movement-based, factor-independent → P&L matches exactly
- **Result: P&L error = 0%, SL error = 0pp**

For **what-if** parameters (different factor or min_hold):
- Close_price changes → fill P&L changes
- Some trips may switch between fill and SL outcomes
- Deterministic resolution via timeline scanning

### What Changes

| Component | Before | After |
|-----------|--------|-------|
| `calc_fill_prob` | Brownian `2Φ(-d/(σ√t))` | Deterministic: `bid >= close_price ? 1.0 : 0.0` |
| `simulate_single_trip` | Expected value mode (p_survive accumulation) | `simulate_counterfactual_trip` (deterministic scan) |
| Fill determination | Per-tick probability weighted | Binary: fill at first viable tick |
| SL determination | Per-tick unrealized check (noisy) | Actual outcome for baseline; deterministic scan for what-if |

### What Stays

- `SimResult` dataclass — unchanged
- `calc_close_price` — unchanged (accurate to +0.01 JPY)
- `aggregate_results`, `print_sweep_grid` — unchanged
- `run_close_fill_sweep` — updated to call new sim function
- Test helpers — reusable

## Architecture

### `simulate_counterfactual_trip`

```
Input: trip, timeline, min_hold_s, close_spread_factor, stop_loss_jpy
Output: SimResult

Algorithm:
1. Extract open_fill metadata (price, side, spread_pct, timestamp)
2. Compute direction, min_hold_end

3. If trip.sl_triggered AND min_hold_s == actual_min_hold (180):
   → SL outcome is anchored to actual
   → BUT: check if a fill would have occurred BEFORE SL with new factor
   → Scan timeline [min_hold_end, sl_time] for deterministic fill
   → If fill found: return fill SimResult with counterfactual P&L
   → If no fill: return SL SimResult with actual SL P&L

4. If NOT trip.sl_triggered AND min_hold_s == actual_min_hold:
   → Fill is anchored to actual fill time
   → Compute new close_price at actual fill time with new factor
   → Check viability: would bid >= new_close_price at actual fill tick?
     → If yes: fill at actual time with new P&L
     → If no: scan forward from actual fill time
       → At each tick: check SL, then check deterministic fill
       → First viable tick: fill with new P&L
       → SL first: return SL P&L

5. If min_hold_s != actual_min_hold (180):
   → Full deterministic scan from min_hold_end
   → At each tick: check SL (unrealized < -stop_loss_jpy)
   → Then check fill (bid >= close_price for long, ask <= close_price for short)
   → First resolution wins
   → Timeline capped at max_sim_duration (default 7200s)
```

### Fill Viability Check

```python
def _is_fillable(close_price, tick, direction):
    """Deterministic fill check: would this close order fill at this tick?"""
    if direction == 1:  # long → SELL limit
        return tick.best_bid >= close_price
    else:               # short → BUY limit
        return tick.best_ask <= close_price
```

This replaces the Brownian `calc_fill_prob`. No probability — binary yes/no.

### SL Handling for min_hold Changes

When min_hold changes, the hold/close phase boundary shifts:
- **Shorter min_hold** (e.g., 120s): close phase starts earlier, more fill opportunities
  before SL. Some SL trips may convert to fills.
- **Longer min_hold** (e.g., 240s): more exposure during hold phase. SL trips that
  triggered during 180-240s are now hold-phase SLs (earlier). Some fill trips that
  filled at 180-240s now need to survive longer.

The deterministic scan handles this correctly by starting from the new min_hold_end.

**Known limitation**: SL detection uses metrics mid snapshots, which have ±5 JPY
uncertainty vs actual bot SL. For min_hold changes, this introduces noise in
marginal SL cases. This is acceptable for what-if analysis (relative comparison)
but not for absolute prediction.

### `calc_fill_prob` — Backward Compatibility

Keep `calc_fill_prob` as a function but change its implementation:

```python
def calc_fill_prob(close_price, best_bid, best_ask, sigma_1s, mid, direction, dt=3.0):
    """Deterministic fill check (replaces Brownian model).

    Returns 1.0 if the close order would fill at current market state, 0.0 otherwise.
    """
    if direction == 1:  # SELL limit
        return 1.0 if best_bid >= close_price else 0.0
    else:               # BUY limit
        return 1.0 if best_ask <= close_price else 0.0
```

This makes `simulate_single_trip` (expected value mode) equivalent to the
counterfactual scan for p_fill ∈ {0, 1}. The old Brownian formula is removed.

## Validation Criteria

### Baseline (min_hold=180, factor=0.4)
- **P&L**: sim matches actual ±0.01 JPY (rounding only)
- **SL count**: sim matches actual exactly (18/122)
- **SL rate**: 14.8% ± 0pp

### Factor Sweep (min_hold=180, factor=0.1-0.7)
- **Monotonicity**: higher factor → higher P&L per fill (more spread capture)
- **SL stability**: SL count should be stable or decrease with lower factor
  (closer close price fills earlier, possibly before SL)
- **P&L plausibility**: within reasonable range based on spread capture analysis

### Min_hold Sweep (factor=0.4, min_hold=60-300)
- **Shorter min_hold**: more fills (close starts earlier), possibly fewer SLs
- **Longer min_hold**: fewer fills in timeline, more SL exposure
- **Known noise**: ±5 JPY SL detection uncertainty affects marginal cases

## Test Plan

1. **Unit tests for `_is_fillable`** — boundary cases (at price, above, below)
2. **Unit tests for `simulate_counterfactual_trip`**:
   - Baseline factor matches actual P&L per trip (sample 5 trips)
   - Higher factor → higher fill P&L
   - Lower factor → lower fill P&L
   - SL trip stays SL when factor changes don't help
   - SL trip converts to fill when lower factor enables earlier fill
3. **Integration test**: baseline sweep at factor=0.4, min_hold=180
   - Total P&L matches actual ±0.01
   - SL count = 18
4. **Regression**: all existing `calc_close_price` tests still pass
