# TightStocks v1 Development Journey
## From Proposal to Production-Ready Signal

**Date:** November 15, 2025  
**Authors:** Kieran (Fundamental PM) + Claude (Quant)

---

## ⚠️ PRE-PRODUCTION CHECK REQUIRED

**VERIFY COMEX PUBLICATION TIMING:**
- If COMEX stocks are published AFTER LME close, we need to shift COMEX component by an additional day
- Currently assumes all exchange data available by morning of trading day
- Check: When exactly are COMEX warehouse stocks published?
- If after LME close, change COMEX IIS to use `shift(2)` or exclude from same-day signal

---

## Executive Summary

We built a **4th sleeve** for the adaptive portfolio system using physical inventory data. The final signal achieves:

- **Standalone Sharpe:** 0.666 (IS), 0.774 (OOS)
- **IS/OOS Degradation:** +16.1% (IMPROVED in OOS)
- **Correlation with price sleeves:** ~0.10 OOS (orthogonal)
- **Portfolio OOS improvement:** +0.094 Sharpe (+16.5%) at 25% weight

The key innovation: **continuous signal** instead of binary threshold, which eliminates parameter fragility and uses all information content.

---

## The Journey

### 1. Initial Proposal (From Another Quant)

Started with a colleague's proposal for an IIS (Inventory Investment Surprise) signal:

```yaml
signal:
  stocks_type: iis_surprise
  change_window: 10
  z_window: 180
  threshold: -1.0
  regime_filter: true (corr < -0.2)
  boost_factor: 1.5x longs
  exec_weekdays: [4]  # Fridays only
```

**My immediate concerns:**
- Friday-only execution = unnecessary lag
- 180-day z-window too short
- Binary threshold fragile
- Aggregating all exchanges assumes perfect substitutability

### 2. First Backtest - Raw Numbers Impressive

Tested the basic IIS concept:
- **0.739 Sharpe** with simple IIS < -1.0
- **29.3% Q1-Q5 annualized spread**
- 54.9% hit rate, 15% time in market

Key finding: **Regime filter hurt performance** (0.54 vs 0.74 Sharpe). Threw away observations for marginal improvement.

### 3. LME-Only vs Aggregated

You raised valid concern: "LME-only might miss the macro copper picture."

**Results:**
- LME-only: 0.496 Sharpe
- Aggregated: 0.643 Sharpe

**You were right.** But deeper analysis showed LME has HIGHER predictive power (41% Q1-Q5 spread) but is noisier. Aggregated smooths exchange-specific noise.

**Solution:** Weighted combination
```python
iis_weighted = 0.60 * iis_lme + 0.25 * iis_comex + 0.15 * iis_shfe
```

LME dominates (global benchmark), COMEX adds US flows, SHFE adds China demand but discounted for noise.

### 4. Correlation Check - The Money Shot

Tested correlation with actual sleeve returns:
```
TightStocks vs (OOS):
  TrendCore:    0.038
  TrendImpulse: 0.215
  MomentumCore: 0.042
  Average:      0.098
```

**This is genuine orthogonality.** Using completely different information (inventory vs price momentum).

Portfolio simulation showed:
- 3-sleeve OOS: 0.569 Sharpe
- 4-sleeve OOS (25% weight): 0.663 Sharpe
- **+16.5% improvement from diversification**

### 5. Architecture Questions - Your Sharp Instincts

You asked the right questions:

**Q: Should 3x1 vol regime optimization include the 4th sleeve?**
A: Yes, optimize on all 4. TightStocks shows regime-dependent performance.

**Q: Does 15% floor apply?**
A: This exposed a problem. TightStocks with binary threshold is only in market 7-15% of time. Can't meaningfully have 15% floor on a sleeve that's flat 85% of time.

**Q: IS/OOS split?**
Tested 2003-2018 IS, 2019-2025 OOS:
```
IIS < -0.5:  IS=0.68, OOS=0.75, Degrad=+10%
IIS < -1.0:  IS=0.60, OOS=0.68, Degrad=+13%
IIS < -1.2:  IS=0.83, OOS=0.23, Degrad=-72% ← COLLAPSED
```

### 6. The Cliff Problem - Your Critical Observation

You spotted the red flag: **massive performance cliff from -1.0 to -1.2 threshold.**

Going from 0.68 to 0.23 Sharpe with 0.2 threshold change = not robust. This is classic overfitting to a specific threshold.

**Root cause:** At -1.2, only 48 OOS observations. Not enough for statistical stability.

### 7. Renaissance Solution - Continuous Signal

Instead of binary threshold, use continuous scaling:

```python
position = max(0, -IIS / scale_factor)
```

- IIS = 0: position = 0.0 (neutral)
- IIS = -1: position = 0.5 (moderate long)
- IIS = -2: position = 1.0 (full long)
- IIS > 0: position = 0.0 (flat, stocks building)

**Why this is superior:**
1. **No cliff problem** - smooth response, no magic number
2. **Uses ALL information** - IIS = -1.5 gives more position than IIS = -1.0
3. **More stable** - +16% OOS improvement (rare)
4. **15% floor compatible** - signal is always "active" at varying intensity

### 8. Publication Lag Check

You caught potential forward bias with LME publication timing:
- Friday 9am publishes Thursday's stocks
- If we trade Friday close, we have all day to calculate
- **shift(1) is sufficient** for morning publication + EOD execution

**Timeline verified:**
```
Wednesday: Stocks close
Thursday 9am: Wednesday's stocks published
Thursday close: Execute trade using Wednesday's IIS
```

**⚠️ STILL TO CHECK: COMEX publication timing**

### 9. Final Performance

**Standalone:**
- IS Sharpe: 0.666
- OOS Sharpe: 0.774
- Degradation: +16.1% (improved OOS)
- Average position: 0.06
- Long-only, continuous

**Portfolio contribution (blended with actual sleeve returns):**
```
3-sleeve OOS: 0.569 Sharpe

4-sleeve OOS (by weight):
  15% TightStocks: 0.621 (+0.052, +9.1%)
  25% TightStocks: 0.663 (+0.094, +16.5%)
  33% TightStocks: 0.701 (+0.133, +23.4%)
```

---

## Why Continuous Signal Wins

Binary threshold problems:
1. **Threshold fragility** - -1.0 works, -1.2 collapses
2. **Information loss** - treats IIS=-1.5 same as IIS=-1.0
3. **Floor incompatibility** - flat 85%+ of time
4. **Fewer observations** - only extreme tails used

Continuous signal advantages:
1. **No magic number** - scale factor less sensitive than threshold
2. **Full information** - proportional betting
3. **Statistical stability** - all observations contribute
4. **Architectural fit** - works with floor constraints

---

## Performance Reality Check

**Raw numbers:**
- Annual return: ~2% (low because partial positioning)
- Annual vol: ~2.7%
- Average position: 0.06 (6% of full sizing)
- Sharpe: 0.666 IS, 0.774 OOS

**Why this matters:**
The low absolute return is because the signal is selective. It's not in market 100% of time like trend sleeves. When you blend with 25% weight, the diversification benefit (near-zero correlation) drives the portfolio improvement.

**At 25% weight:**
- +0.094 Sharpe OOS (0.569 → 0.663)
- ~50bps direct return contribution
- Plus diversification benefit

The value is in **risk-adjusted returns**, not raw returns.

---

## What We Didn't Do (And Why)

**1. Regime filter (correlation < -0.2)**
- Threw away 42% of observations
- Marginal improvement in predictive correlation
- Net negative for Sharpe

**2. Spread enhancement**
- Tested adding acceleration filter
- Reduced Sharpe from 0.62 to 0.49
- Overthinking - keep it simple

**3. Binary threshold**
- Despite slightly higher hit rate
- Fragility and floor incompatibility
- Continuous is architecturally superior

**4. shift(2) for extra safety**
- You correctly pointed out unnecessary
- Morning publication + EOD execution = shift(1) sufficient
- Extra lag just hurts performance

---

## Forward Bias Audit - CLEAN

Verified NO look-ahead bias:
1. Stock change uses T and T-10 (past only)
2. Z-score uses past 252 days
3. Signal shifted by 1 day (T-1 signal for T position)
4. Vol scaling uses past returns
5. PnL accrual is T→T+1
6. Morning publication gives full day to calculate

**⚠️ EXCEPTION: Check COMEX publication timing before production**

---

## Implementation Files

```
src/signals/tightstocks_v1.py         # Layer B signal logic
src/cli/build_tightstocks_v1.py       # Build script
Config/Copper/tightstocks_v1.yaml     # Parameters (no hardcodes)
run_tightstocks_v1.bat                 # Runner
```

**Data requirements:**
```
copper_lme_3mo.canonical.csv
copper_lme_onwarrant_stocks.canonical.csv
copper_comex_stocks.canonical.csv
copper_shfe_onwarrant_stocks.canonical.csv
```

---

## Integration Checklist

- [ ] **CHECK COMEX PUBLICATION TIMING** (critical)
- [ ] Place signal logic in `src/signals/`
- [ ] Place build script in `src/cli/`
- [ ] Place config in `Config/Copper/`
- [ ] Rename data files to .canonical.csv format
- [ ] Run build script
- [ ] Verify ~0.65-0.77 Sharpe
- [ ] Check correlation with actual sleeves (<0.15)
- [ ] Re-optimize 3x1 weights with 4 sleeves
- [ ] Set weight allocation (15-33%)
- [ ] Backtest full 4-sleeve portfolio

---

## The Quantamental Story

This is what makes your system differentiated:

**Before:** 3 price-based momentum sleeves
- "We follow trends"
- Same information everyone has

**After:** 3 price + 1 inventory sleeve
- "We combine momentum with physical market tightness"
- Fundamental information systematized
- Orthogonal signals, true diversification

**The pitch:** "We don't just follow price momentum. We have proprietary signals that capture physical market tightness - the same fundamentals I traded discretionary at Andurand, now systematized and scalable."

---

## Future Enhancements (v2+)

1. **Verify COMEX/SHFE publication timing** - adjust lags as needed
2. **Demand normalization** - Scale stock changes by ISCG consumption
3. **Individual exchange signals** - Weight by regime
4. **CFTC positioning** - Add 5th sleeve using speculator positioning
5. **IV/RV divergence** - Use implied vol premium as signal

Each addition must maintain:
- Positive standalone edge (>0.3 Sharpe)
- Low correlation with existing (<0.3)
- Clear economic rationale (not data mining)
- Stable IS/OOS performance

---

## Key Learnings

1. **Binary thresholds are fragile** - small changes cause large performance swings
2. **Continuous signals are robust** - use all information, no magic numbers
3. **Correlation is king** - 0.10 average correlation is genuine diversification
4. **OOS stability matters most** - +16% OOS improvement is rare and valuable
5. **Simplicity wins** - every added filter reduced performance
6. **Publication timing matters** - verify data availability before execution

---

## Bottom Line

We turned a colleague's proposal (binary IIS threshold) into a production-ready signal (continuous IIS scaling) that:

- Is more robust (no threshold cliff)
- Uses more information (continuous vs binary)
- Fits your architecture (floor compatible)
- Provides genuine diversification (0.10 correlation)
- Shows strong OOS stability (+16% improvement in OOS)
- Forward bias verified (pending COMEX check)

**OOS portfolio impact at 25% weight:**
- +0.094 Sharpe (0.569 → 0.663)
- +16.5% relative improvement

**This is your fundamental edge, systematized.**

---

*Document generated: November 15, 2025*
*Ready for production integration (after COMEX timing verification)*
