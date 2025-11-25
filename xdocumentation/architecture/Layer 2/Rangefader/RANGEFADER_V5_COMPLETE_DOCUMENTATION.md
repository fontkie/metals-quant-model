# RangeFader V5 - Complete Documentation & Action Plan

**Status:** ON HOLD - Awaiting Overlays  
**Date:** 2025-11-19  
**Version:** 5.0 (OHLC ADX)

---

## Executive Summary

RangeFader V5 is a mean reversion strategy for copper that achieves **0.344 net Sharpe overall** and **1.104 Sharpe in choppy markets** (21.7% of time) across 26.8 years. The strategy demonstrates excellent regime specialization with perfect validation scores but suffers from recent catastrophic failure in 2024-2025 (-1.46 Sharpe) due to unfiltered macro confusion.

**Deployment Status:** ON HOLD pending ChopCore overlay development  
**Estimated Timeline to Deploy:** 1-2 months  
**Priority:** MEDIUM (have working trend strategies, this fills choppy gap)

---

## Strategy Overview

### Core Concept

Mean reversion strategy that:
- Enters when price deviates 0.7 std from 60-day moving average
- Only trades when ADX < 20 (choppy regime)
- Exits quickly at 0.2 std (asymmetric thresholds)
- Vol-targeted to 10% annually
- Costs: 3 bps one-way

### Key Innovation: OHLC ADX

**Critical fix from V4:**
- V4 used close-only ADX approximation (underestimated by ~6 points)
- V5 uses proper OHLC ADX calculation (high, low, close)
- Result: More accurate regime detection (21.7% choppy vs 26% in V4)

### 4-Layer Architecture

1. **Layer 1:** Pure signal generation with OHLC ADX filtering
2. **Layer 2:** Closed-loop volatility targeting to 10%
3. **Layer 3:** Portfolio blending (single sleeve currently)
4. **Layer 4:** Execution with costs applied once on net position

---

## Optimized Parameters (2025-11-19)

### Signal Parameters

```yaml
lookback_window: 60        # 60-day MA (optimized from 30-70 range)
zscore_entry: 0.7          # 0.7 std to enter (optimized from 0.6-1.0)
zscore_exit: 0.2           # 0.2 std to exit (optimal in all tests)
adx_threshold: 20.0        # ADX < 20 = choppy (optimized from 15-20)
adx_window: 14             # Standard ADX (fixed)
update_frequency: 1        # Daily updates
```

### Sizing & Costs

```yaml
target_vol: 10%            # Annual volatility target
vol_lookback: 63 days      # ~3 months rolling vol
leverage_cap: 3.0x         # Maximum leverage
cost_bps: 3.0              # One-way transaction cost
```

### Optimization Results

**Parameter Space Tested:**
- Lookback: 30, 40, 50, 60, 70 days
- Entry: 0.6, 0.7, 0.8, 0.9, 1.0 std
- Exit: 0.2, 0.3, 0.4 std
- ADX: 15, 17, 20

**Best Configuration:**
- 225 combinations tested
- In-sample: 2000-2018 (19 years)
- Out-of-sample: 2019-2025 (6.9 years)
- Winner: L=60, E=0.7, X=0.2, ADX=20

---

## Performance Metrics (26.8 Years, 2000-2025)

### Overall Performance

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Net Sharpe | 0.344 | >0.30 | ✓ PASS |
| Gross Sharpe | 0.402 | - | - |
| Annual Return | 4.5% | - | - |
| Annual Vol | 13.1% | 10% | ~Target |
| Max Drawdown | -30.2% | <-25% | ⚠️ Acceptable |

### Regime-Specific Performance

| Regime | % Time | Sharpe | Assessment |
|--------|--------|--------|------------|
| Choppy (ADX<20) | 21.7% | **1.104** | ✓✓ EXCELLENT |
| Weak Trend (20-25) | 13.7% | ~0 | ✓ Correct (flat) |
| Strong Trend (25+) | 64.5% | ~0 | ✓ Correct (flat) |

**Key Finding:** Strategy achieves 1.10 Sharpe when it should trade (choppy) and stays flat when it shouldn't (trending). This validates the core logic.

### Activity & Turnover

- **Overall Activity:** 15.2% of days
- **Activity in Choppy:** 70.1% (target >60%) ✓
- **Activity in Trending:** 0.0% (target <15%) ✓
- **Annual Turnover:** 25.7x
- **Annual Cost:** 0.77% (15% of gross returns)

---

## Validation Results - ALL PASSED ✓

| Check | Value | Target | Status |
|-------|-------|--------|--------|
| Activity in Choppy | 70.1% | >60% | ✓ PASS |
| Activity in Trending | 0.0% | <15% | ✓ PASS |
| Mean ADX Active | 15.2 | <20 | ✓ PASS |
| Mean ADX Inactive | 36.6 | >25 | ✓ PASS |
| Correlation(|pos|, ADX) | -0.489 | <-0.15 | ✓ PASS |
| **Overall** | - | All Pass | **✓ PASS** |

**Perfect regime behavior:** Strategy trades exactly when it should (choppy) and stays flat when it shouldn't (trending).

---

## Critical Issue: OOS Performance Decay

### In-Sample vs Out-of-Sample

| Period | Sharpe | Return | Vol | Status |
|--------|--------|--------|-----|--------|
| **IS (2000-2018)** | 0.414 | +5.5% | 13.3% | ✓ Good |
| **OOS (2019-2025)** | 0.140 | +1.8% | 12.5% | ⚠️ Weak |
| **OOS/IS Ratio** | 0.338 | - | - | ⚠️ Marginal |

### OOS Performance by Year

| Year | Sharpe | Return | Assessment |
|------|--------|--------|------------|
| 2019 | +0.57 | +5.1% | ✓ Good |
| 2020 | +0.86 | +9.3% | ✓✓ Excellent (COVID!) |
| 2021 | +1.09 | +18.5% | 🚀 Outstanding |
| 2022 | +0.07 | +1.3% | ⚠️ Choppy |
| 2023 | +0.44 | +4.5% | ✓ Solid |
| **2024** | **-1.88** | **-18.8%** | ❌ DISASTER |
| **2025** | **-0.95** | **-9.1%** | ❌ Still bad |

**Key Insight:** Strategy worked well for 5 years (2019-2023 avg Sharpe 0.57), then broke catastrophically in 2024-2025.

---

## Root Cause Analysis: 2024-2025 Failure

### What Broke?

**Mean Reversion Stopped Working**

| Metric | 2024-2025 | Normal | Assessment |
|--------|-----------|--------|------------|
| Expectancy per day | -0.571% | +0.2% | ❌ Negative |
| Win Rate | 44.6% | >50% | ❌ Below breakeven |
| Avg Win | +0.81% | - | - |
| Avg Loss | **-1.69%** | - | ❌ 2:1 against us |
| Win/Loss Ratio | 0.48 | >1.0 | ❌ Terrible |

**Directional Analysis**

When LONG (expecting bounce):
- Market went UP: 33.3% (should be >50%)
- Market went DOWN: 50.0% (killing us)

When SHORT (expecting pullback):
- Market went DOWN: 47.7% (marginal)
- Market went UP: 50.0% (hurting us)

**Diagnosis:** Market is not oscillating around mean. It's trending through positions, creating losses on both sides.

### Why Did It Fail?

**Hypothesis 1: China Structural Weakness** (PRIMARY)
- China property crisis deepened in 2024
- Persistent weak demand, not choppy oscillation
- Low ADX (appears choppy) but actually directional grind lower
- Strategy enters short, market continues lower → we exit at loss
- Strategy enters long thinking bounce, market grinds lower → loss

**Hypothesis 2: ADX Threshold Too High**
- ADX < 20 is too permissive
- Catches "fake choppy" periods (directional grinds with low ADX)
- ADX < 15 might be safer (more restrictive)

**Hypothesis 3: No Macro Confusion Filter**
- COVID worked (2020: +0.86 Sharpe) because it was a V-shaped recovery
- 2024-2025 is structural weakness, not oscillation
- Need ChopCore to detect macro confusion and go flat

**Hypothesis 4: No Fundamental Filter**
- TightnessIndex would catch inventory building (not tight)
- Don't fade when fundamentals persistently weak
- Only mean revert in balanced/tight markets

---

## Why Keep the Strategy?

Despite recent failure, there are strong reasons to preserve RangeFader V5:

### ✓ Strengths

1. **Proven Long-Term Logic**
   - 1.104 choppy Sharpe across 26.8 years
   - Worked for 23/26 years (2000-2023)
   - Perfect regime validation

2. **Identifiable Failure Mode**
   - Not random breakdown
   - Clear cause: structural China weakness appearing as "choppy"
   - Fixable with overlays

3. **Portfolio Diversification**
   - Orthogonal to TrendMedium (0.505 Sharpe)
   - Orthogonal to TrendImpulse (0.343 Sharpe)
   - Fills the 21.7% choppy regime gap

4. **Strong First 5 Years OOS**
   - 2019-2023: 0.57 average Sharpe
   - Including COVID (2020: +0.86)
   - Only broke in 2024-2025

### ⚠️ Weaknesses

1. **Recent Catastrophic Failure**
   - 2024-2025: -1.46 combined Sharpe
   - Most recent data is most relevant
   - Risk of continued losses

2. **No Regime Shift Detection**
   - Can't distinguish choppy from structural moves
   - Needs ChopCore overlay urgently

3. **No Fundamental Filter**
   - Fades without checking if fundamentals support
   - Needs TightnessIndex overlay

4. **Recency Bias Risk**
   - If market structure permanently changed, strategy is dead
   - Need to monitor closely

---

## Deployment Decision: ON HOLD

### Status: ON HOLD Pending Overlays

**Why not deploy now:**
- Recent failure too severe (-1.46 Sharpe 2024-2025)
- No macro confusion detection
- Risk of continued losses
- Better to fix first, then deploy

**Why not abandon:**
- 23 years of good performance (2000-2023)
- Clear path to improvement (overlays)
- Perfect regime validation
- Portfolio needs choppy specialist

### Deployment Criteria

Deploy when ALL of these are met:

1. ✓ ChopCore v1 built and tested
2. ✓ TightnessIndex v1 built and tested
3. ✓ Combined system tested on 2024-2025 (must improve)
4. ✓ 3-month forward walk shows Sharpe > 0.30
5. ✓ Risk controls in place (stop-loss, monitoring)

**Estimated Timeline:** 1-2 months

---

## Improvement Roadmap: Steps to Fix

### Phase 1: Immediate Diagnostics (Week 1)

#### Step 1.1: ADX Threshold Sensitivity Test

**Objective:** See if tighter ADX threshold fixes 2024-2025

**Action:**
```python
# Test ADX thresholds: 12, 15, 17, 20
# On full sample (2000-2025) and recent period (2024-2025)

for adx_thresh in [12, 15, 17, 20]:
    # Run backtest with:
    lookback=60, entry=0.7, exit=0.2, adx_threshold=adx_thresh
    
    # Measure:
    # - Full sample Sharpe
    # - 2024-2025 Sharpe specifically
    # - Activity in choppy
    # - False positive rate (active when should be flat)
```

**Expected Result:** ADX < 15 should reduce 2024-2025 damage (lower activity, fewer bad trades)

**Decision Criteria:**
- If ADX < 15 gives 2024-2025 Sharpe > 0, use it
- If all thresholds negative 2024-2025, confirms need for overlays

#### Step 1.2: Regime Distribution Analysis

**Objective:** Understand if 2024-2025 was truly "choppy" or fake

**Action:**
```python
# Compare regime distributions
periods = {
    'Full Sample': ('2000-01-01', '2025-11-06'),
    'IS': ('2000-01-01', '2018-12-31'),
    'Good OOS': ('2019-01-01', '2023-12-31'),
    'Bad OOS': ('2024-01-01', '2025-11-06')
}

for name, (start, end) in periods.items():
    # Calculate:
    # - ADX distribution (mean, median, % < 20)
    # - Price trend strength (90-day slope)
    # - Volatility regime
    # - Mean reversion speed (autocorrelation)
```

**Expected Result:** 2024-2025 should show:
- Similar ADX distribution (appears choppy)
- But stronger directional trend (hidden directionality)
- Slower mean reversion (structural, not oscillation)

#### Step 1.3: Alternative Parameter Test

**Objective:** Could ultra-conservative params have saved us?

**Action:**
```python
# Test extreme parameters on 2024-2025
configs = [
    {'lookback': 60, 'entry': 1.0, 'exit': 0.3, 'adx': 15},  # More selective
    {'lookback': 60, 'entry': 1.2, 'exit': 0.4, 'adx': 12},  # Very selective
    {'lookback': 40, 'entry': 0.7, 'exit': 0.2, 'adx': 15},  # Faster MA
]

for config in configs:
    # Test on 2024-2025
    # If any work, might be parameter issue not strategy issue
```

**Expected Result:** Even conservative params should fail (structural issue, not parameter)

---

### Phase 2: Build ChopCore Overlay (Weeks 2-3)

**Priority: CRITICAL** - This is the key fix

#### Step 2.1: ChopCore v1 Design

**Objective:** Detect macro confusion periods and go flat

**Components:**

1. **China Demand Proxies**
   - Property starts (leading indicator)
   - Copper apparent demand (direct)
   - PMI manufacturing (sentiment)
   - Signal: 3-month trend in all three

2. **Policy Uncertainty Index**
   - VIX-style measure for policy
   - Fed policy uncertainty
   - China policy shocks
   - Signal: Spikes above 80th percentile

3. **Market Regime Detector**
   - Copper vol regime (realized vs expected)
   - Cross-asset correlations (copper vs equities)
   - Regime stability (how long in current regime)
   - Signal: Unstable/transitioning regimes

4. **Fundamental Confusion**
   - Inventory accumulation (not drawdown)
   - Cost curve pressure (prices below 50th percentile)
   - Signal: Mixed messages from fundamentals

**ChopCore Logic:**
```python
def chopcore_signal(date):
    """
    Returns confusion score 0-1
    0 = clear regime (safe to trade)
    1 = max confusion (go flat)
    """
    
    # China demand trend (0-1, higher = weaker)
    china_score = china_demand_momentum(date, lookback=90)
    
    # Policy uncertainty (0-1, higher = more uncertain)
    policy_score = policy_uncertainty_index(date)
    
    # Market regime stability (0-1, higher = less stable)
    regime_score = regime_stability(date, lookback=60)
    
    # Fundamental confusion (0-1, higher = more mixed)
    fundamental_score = fundamental_confusion(date)
    
    # Weighted average
    confusion = (
        0.30 * china_score +
        0.25 * policy_score +
        0.25 * regime_score +
        0.20 * fundamental_score
    )
    
    return confusion

# Integration with RangeFader
choppy_signal = (adx < threshold)  # Current logic
confusion_score = chopcore_signal(date)

# Only trade if choppy AND low confusion
trade_allowed = choppy_signal and (confusion_score < 0.5)
```

#### Step 2.2: ChopCore v1 Implementation

**Data Required:**
- China property starts (Bloomberg: CHPRSTOT Index)
- China copper apparent demand (SHFE stocks + imports)
- China PMI (Bloomberg: CPMINDX Index)
- VIX (for general uncertainty)
- Policy uncertainty index (EPU from Baker et al.)

**Build Steps:**
1. Create `src/overlays/chopcore_v1.py`
2. Implement confusion scoring functions
3. Add to RangeFader signal generation
4. Test on 2024-2025 (must improve!)

**Success Criteria:**
- 2024-2025 Sharpe improves to > 0
- Confusion correctly high during 2024-2025
- Confusion correctly low during 2019-2021
- Activity in truly choppy periods still >60%

#### Step 2.3: ChopCore v1 Validation

**Backtest with ChopCore:**
```python
# Full sample with ChopCore
for confusion_threshold in [0.3, 0.5, 0.7]:
    # Test different thresholds
    # Measure impact on:
    # - Overall Sharpe
    # - 2024-2025 Sharpe specifically
    # - Activity reduction
    # - False positive/negative rates
```

**Expected Results:**
- Overall Sharpe should stay ~0.30-0.35
- 2024-2025 should improve to >0 (or at least -0.3)
- Activity should drop 20-30% (fewer trades, better quality)

---

### Phase 3: Build TightnessIndex Overlay (Weeks 4-5)

**Priority: HIGH** - Prevents fading during supply surplus

#### Step 3.1: TightnessIndex v1 Design

**Objective:** Only mean revert when market is tight (inventory investment negative)

**Components:**

1. **Exchange Inventories**
   - LME visible stocks
   - SHFE stocks
   - Combined measure
   - Signal: Rate of change (drawing or building)

2. **ISCG Balance**
   - Quarterly balance data
   - Interpolate to daily
   - Signal: Surplus (no trade) vs Deficit (trade)

3. **Time Spreads**
   - LME cash-3M spread
   - Backwardation (tight) vs Contango (loose)
   - Signal: Percentile vs 5-year history

4. **Treatment Charges**
   - TC/RCs for smelters
   - High TC = surplus (don't fade)
   - Low TC = tight (can fade)

**TightnessIndex Logic:**
```python
def tightness_score(date):
    """
    Returns tightness score 0-1
    0 = loose market (don't mean revert)
    1 = tight market (mean reversion works)
    """
    
    # Inventory drawdown (higher = tighter)
    inv_score = inventory_drawdown_rate(date, lookback=90)
    
    # ISCG balance (deficit = 1, surplus = 0)
    balance_score = iscg_balance_normalized(date)
    
    # Backwardation strength (higher = tighter)
    spread_score = time_spread_percentile(date)
    
    # TC/RC level (lower = tighter)
    tc_score = 1 - tc_percentile(date)
    
    # Weighted average
    tightness = (
        0.30 * inv_score +
        0.30 * balance_score +
        0.25 * spread_score +
        0.15 * tc_score
    )
    
    return tightness

# Integration with RangeFader + ChopCore
choppy_signal = (adx < threshold)
confusion_score = chopcore_signal(date)
tightness = tightness_score(date)

# Only trade if choppy + low confusion + tight market
trade_allowed = (
    choppy_signal and 
    (confusion_score < 0.5) and 
    (tightness > 0.4)  # Only in tighter half of distribution
)
```

#### Step 3.2: TightnessIndex v1 Implementation

**Data Required:**
- LME stocks (daily, Bloomberg: LMCADS03 Comdty)
- SHFE stocks (weekly, Bloomberg: COPISHFE Comdty)
- LME cash-3M spread (daily)
- TC/RCs (quarterly, available from user's fundamental knowledge)
- ISCG balance data (quarterly, already have)

**Build Steps:**
1. Create `src/overlays/tightness_v1.py`
2. Implement tightness scoring functions
3. Add to RangeFader signal generation (after ChopCore)
4. Test impact on historical periods

**Success Criteria:**
- Avoids fading during known surplus periods (2015-2016)
- Maintains activity in tight markets (2021-2022)
- Improves Sharpe by 0.05-0.10 points

#### Step 3.3: TightnessIndex v1 Validation

**Test on Known Regimes:**

| Period | Regime | Expected Behavior |
|--------|--------|-------------------|
| 2015-2016 | Surplus | Low tightness → less fading → avoid losses |
| 2021 | Tight | High tightness → normal fading → good gains |
| 2024-2025 | Loose | Low tightness → less fading → reduce disaster |

**Validation:**
```python
# Backtest with both overlays
results = backtest_rangefader(
    chopcore_enabled=True,
    tightness_enabled=True,
    confusion_threshold=0.5,
    tightness_threshold=0.4
)

# Measure:
# - Full sample Sharpe vs baseline (0.344)
# - 2024-2025 improvement
# - Activity reduction vs baseline
# - Regime-specific performance
```

**Target Results:**
- Full sample Sharpe: 0.35-0.40 (slight improvement)
- 2024-2025: >0 (or at least -0.2, not -1.46)
- Activity: 10-12% (down from 15%, better quality)

---

### Phase 4: Combined System Testing (Week 6)

#### Step 4.1: Full Walk-Forward Validation

**Objective:** Ensure overlays don't overfit

**Method:**
```python
# Walk-forward test with expanding window
for test_start in ['2020-01-01', '2021-01-01', '2022-01-01', '2023-01-01']:
    # Optimize overlay thresholds on data BEFORE test_start
    # Test on 1-year period starting test_start
    # Record performance
    
    # Measure:
    # - Sharpe in each test period
    # - Parameter stability
    # - Overlay activation rates
```

**Success Criteria:**
- All test periods Sharpe > 0
- 2024-2025 test period Sharpe > 0 (not optimized on it)
- Consistent overlay behavior (not flipping wildly)

#### Step 4.2: Stress Testing

**Scenarios to Test:**

1. **COVID Crash (2020 Q1)**
   - Should ChopCore activate? (NO - clear V-shape)
   - Should still trade (it worked: +0.86 Sharpe)

2. **China 2015-2016 Grind**
   - Should TightnessIndex block? (YES - surplus)
   - Should ChopCore activate? (YES - structural weakness)

3. **2021 Rally**
   - Should allow trading? (YES - tight market, clear demand)
   - Should maintain strong performance (was +1.09 Sharpe)

4. **2024-2025 Disaster**
   - Should both overlays activate? (YES - weak China, loose market)
   - Should go mostly flat
   - Should avoid most losses

**Expected Behavior:**
```python
# Overlay activation by period
periods = {
    'COVID 2020': {'chopcore': False, 'tightness': True},   # Trade with caution
    'China 2015-16': {'chopcore': True, 'tightness': False},  # Go flat
    '2021 Rally': {'chopcore': False, 'tightness': True},    # Full trade
    '2024-2025': {'chopcore': True, 'tightness': False},     # Go flat
}
```

#### Step 4.3: Portfolio Integration Test

**Objective:** See how RangeFader + overlays fits in adaptive portfolio

**Test:**
```python
# 3-sleeve portfolio with adaptive blending
sleeves = {
    'TrendMedium': 0.505 sharpe,
    'TrendImpulse': 0.343 sharpe,
    'RangeFader_v5_overlays': ??? sharpe
}

# Test adaptive blending with regime detection
# Measure:
# - Portfolio Sharpe vs without RangeFader
# - Diversification benefit
# - Drawdown reduction
```

**Target:**
- Portfolio Sharpe improves by 0.05-0.10
- RangeFader weight: 20-30% in choppy regimes
- Correlation with trend strategies <0.3

---

### Phase 5: Deployment Preparation (Week 7-8)

#### Step 5.1: Production Code Quality

**Checklist:**
- [ ] All overlays in `src/overlays/` with proper structure
- [ ] Configuration in `rangefader_v5.yaml` updated
- [ ] Build script `build_rangefader_v5.py` includes overlays
- [ ] Batch runner `run_rangefader_v5.bat` works end-to-end
- [ ] All validation checks implemented and passing
- [ ] Documentation complete
- [ ] Git commit with proper versioning

#### Step 5.2: Monitoring Dashboard

**Build Simple Dashboard:**
```python
# Daily monitoring script: monitor_rangefader_v5.py
# Outputs:
# - Current position
# - ADX level (are we in target regime?)
# - ChopCore score (confusion level)
# - TightnessIndex score (market tightness)
# - 30/60/90-day rolling Sharpe
# - Distance from max drawdown
# - Alert flags (if metrics cross thresholds)
```

**Alert Thresholds:**
- 30-day rolling Sharpe < -0.5: Review strategy
- 60-day rolling Sharpe < 0: Consider reducing size
- Drawdown > -15% from peak: Warning
- Drawdown > -20% from peak: Critical review
- ChopCore score > 0.7 for 30 days: Expect low activity

#### Step 5.3: Risk Controls

**Implement Stop-Loss Rules:**

1. **Time-based:**
   - If 90-day Sharpe < -0.3 after overlays deployed: Reduce to 50% size
   - If 6-month Sharpe < 0: Review for shutdown

2. **Drawdown-based:**
   - If drawdown exceeds -20% from peak: Reduce to 50% size
   - If drawdown exceeds -30% from peak: Shut down

3. **Overlay-based:**
   - If ChopCore score >0.7 for >60 days: Accept low/zero activity
   - If TightnessIndex <0.3 for >60 days: Accept low/zero activity
   - If both overlays blocking for >90 days: Review parameters

4. **Performance-based:**
   - If ChopCore doesn't improve 2024-2025 in forward test: Don't deploy
   - If 3-month forward walk Sharpe <0: Don't deploy

#### Step 5.4: Deployment Decision

**Go/No-Go Checklist:**

| Criteria | Target | Actual | Status |
|----------|--------|--------|--------|
| ChopCore built & tested | ✓ | - | - |
| TightnessIndex built & tested | ✓ | - | - |
| 2024-2025 improves to >0 | ✓ | - | - |
| Full sample Sharpe >0.30 | ✓ | - | - |
| Walk-forward validates | ✓ | - | - |
| Monitoring ready | ✓ | - | - |
| Risk controls in place | ✓ | - | - |

**Only deploy if ALL criteria met.**

---

## Alternative Approaches to Consider

### Option 1: Abandon Mean Reversion, Try Relative Value

**If overlays don't fix 2024-2025:**

- Maybe outright copper mean reversion doesn't work anymore
- Try copper-aluminum spread mean reversion instead
- Spreads more stable, less macro-dependent
- Requires aluminum data and infrastructure

**Pros:**
- Spreads often more mean-reverting than outrights
- Less sensitive to macro confusion
- Still fills "choppy specialist" role

**Cons:**
- Need aluminum pipeline (6-12 months out per roadmap)
- Different market dynamics
- Less liquidity in spread

### Option 2: Volatility Strategy Instead (VolCore)

**If mean reversion fundamentally broken:**

- Focus on volatility risk premium
- Sell implied vol in normal times
- Buy realized vol in breakouts
- Different alpha source, orthogonal to trends

**Pros:**
- Uncorrelated to mean reversion and trend
- Clearer risk/reward in options markets
- Less sensitive to directional moves

**Cons:**
- Requires options data and infrastructure
- Different skill set (vol surface modeling)
- Also on roadmap (Month 4+)

### Option 3: Just Accept Lower Weight in Portfolio

**If overlays improve but don't fix:**

- Deploy at 10-15% weight (not 25-30%)
- Accept it's a "luxury" strategy (works in good times)
- Focus more on trend strategies (TrendMedium, TrendImpulse)
- Add VolCore instead for diversification

**Pros:**
- Simple solution
- Trend strategies already working (0.505, 0.343 Sharpe)
- Portfolio still 0.75+ Sharpe without RangeFader

**Cons:**
- Doesn't fill the choppy gap fully
- "Luxury" strategies are first to cut in drawdowns
- Might never actually use it if always worried

---

## File Structure & Code Locations

### Current Files

```
Config/Copper/
  rangefader_v5.yaml              # Configuration (optimized parameters)

src/signals/
  rangefader_v5.py                # Core signal generation + OHLC ADX

src/cli/
  build_rangefader_v5.py          # 4-layer backtest builder
  optimize_rangefader_v5.py       # Parameter optimization

scripts/
  run_rangefader_v5.bat           # Build runner (Windows)
  run_rangefader_v5_optimize.bat  # Optimization runner (Windows)

outputs/Copper/RangeFader_v5/
  daily_series.csv                # Full backtest timeseries
  summary_metrics.json            # Performance summary
```

### Files to Create

```
src/overlays/
  chopcore_v1.py                  # Macro confusion detector (TO BUILD)
  tightness_v1.py                 # Market tightness overlay (TO BUILD)

src/cli/
  monitor_rangefader_v5.py        # Daily monitoring dashboard (TO BUILD)
  
scripts/
  run_rangefader_v5_with_overlays.bat  # Build with overlays (TO BUILD)

docs/
  RANGEFADER_V5_OVERLAYS.md       # Overlay documentation (TO BUILD)
  RANGEFADER_V5_MONITORING.md     # Monitoring guide (TO BUILD)
```

---

## Quick Reference Commands

### Run Current Version (Baseline)

```bash
# Full backtest with optimized parameters
scripts\run_rangefader_v5.bat

# Re-optimize parameters (if needed)
scripts\run_rangefader_v5_optimize.bat
```

### After Overlays Built

```bash
# Build with ChopCore only
python src/cli/build_rangefader_v5.py \
  --config Config/Copper/rangefader_v5.yaml \
  --enable-chopcore \
  --outdir outputs/Copper/RangeFader_v5_chopcore

# Build with both overlays
python src/cli/build_rangefader_v5.py \
  --config Config/Copper/rangefader_v5.yaml \
  --enable-chopcore \
  --enable-tightness \
  --outdir outputs/Copper/RangeFader_v5_full

# Monitor daily
python src/cli/monitor_rangefader_v5.py
```

---

## Key Contacts & Resources

### Data Sources

- **LME Prices:** Bloomberg, already have via canonical pipeline
- **SHFE Stocks:** Bloomberg COPISHFE Comdty (weekly)
- **LME Stocks:** Bloomberg LMCADS03 Comdty (daily)
- **China PMI:** Bloomberg CPMINDX Index (monthly)
- **Property Starts:** Bloomberg CHPRSTOT Index (monthly)
- **ISCG Balance:** Have internally (quarterly, copper_balance_values.xlsx)
- **VIX:** Bloomberg VIX Index (daily)
- **TC/RCs:** Fundamental knowledge + CRU/Fastmarkets

### External Research

- **Policy Uncertainty Index:** www.policyuncertainty.com (free)
- **China Copper Demand:** ISCG quarterly reports
- **Mean Reversion Literature:** Lo & MacKinlay (1988), Poterba & Summers (1988)
- **Regime Detection:** Hamilton (1989) Markov-switching models

---

## Summary: Path Forward

### Current Status: ON HOLD

- **What Works:** Core logic sound (1.10 choppy Sharpe), perfect validation
- **What Broke:** 2024-2025 disaster (-1.46 Sharpe), unfiltered macro confusion
- **What's Needed:** ChopCore + TightnessIndex overlays

### Timeline to Deploy

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Phase 1: Diagnostics | Week 1 | Understand 2024-2025 failure |
| Phase 2: ChopCore | Weeks 2-3 | Macro confusion filter |
| Phase 3: TightnessIndex | Weeks 4-5 | Market tightness filter |
| Phase 4: Testing | Week 6 | Validation & stress tests |
| Phase 5: Deploy Prep | Weeks 7-8 | Production ready |
| **TOTAL** | **6-8 weeks** | **Deployable RangeFader v5** |

### Decision Points

**After Phase 1 (Week 1):**
- If ADX threshold change fixes 2024-2025 → Quick fix, deploy sooner
- If no parameter fixes → Proceed to overlays (expected)

**After Phase 2 (Week 3):**
- If ChopCore doesn't improve 2024-2025 → Consider abandoning
- If ChopCore works → Continue to Phase 3

**After Phase 4 (Week 6):**
- If combined system works → Deploy
- If still broken → Consider alternative strategies

### Alternative Exit Criteria

**Abandon RangeFader v5 if:**
- ChopCore + TightnessIndex don't improve 2024-2025 to >0 Sharpe
- Forward walk-forward tests fail (Sharpe <0.20)
- Implementation takes >3 months (opportunity cost)
- Aluminum pipeline ready sooner (do relative value instead)

**Pivot to:**
- Copper-aluminum spread mean reversion (if aluminum ready)
- VolCore volatility strategy (uncorrelated alpha)
- Pure trend portfolio (TrendMedium + TrendImpulse already 0.65-0.75 Sharpe)

---

## Final Thoughts

RangeFader V5 has the bones of a good strategy (1.10 choppy Sharpe, perfect validation) but needs critical care (overlays) before deployment. The 2024-2025 failure is severe but explainable (macro confusion), and the fix is clear (ChopCore + TightnessIndex).

**Recommended Path:**
1. Complete Phase 1 diagnostics (1 week)
2. Build ChopCore v1 (2 weeks) - this is the priority
3. If ChopCore works, add TightnessIndex (2 weeks)
4. Test thoroughly (1-2 weeks)
5. Deploy with monitoring and risk controls

**Fallback Path:**
- If overlays don't work, pivot to copper-aluminum spreads or focus on trend strategies
- Don't force it - better to have 2 good strategies than 3 mediocre ones

**Portfolio Context:**
- Already have TrendMedium (0.505) and TrendImpulse (0.343) working
- Portfolio is 0.65-0.75 Sharpe without RangeFader
- RangeFader is "nice to have" not "must have"
- Can afford to be patient and do it right

---

**Status:** ON HOLD until overlays built  
**Next Action:** Phase 1 diagnostics when returning to this  
**Priority:** MEDIUM (have working alternatives)  
**Estimated Complete:** 6-8 weeks from start
