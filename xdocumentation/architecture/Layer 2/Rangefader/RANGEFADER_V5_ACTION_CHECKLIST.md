# RangeFader V5 - Quick Action Checklist

**When you're ready to resume work on RangeFader V5, follow this checklist.**

---

## TL;DR Status

- **Overall Sharpe:** 0.344 (26.8 years) ✓
- **Choppy Sharpe:** 1.104 ✓✓
- **Validation:** All passed ✓
- **Recent Performance:** -1.46 Sharpe (2024-2025) ❌
- **Status:** ON HOLD pending overlays
- **Timeline to Deploy:** 6-8 weeks

---

## Phase 1: Diagnostics (Week 1)

### Day 1-2: ADX Threshold Test

```bash
# Test if tighter ADX threshold helps 2024-2025
cd C:\Code\Metals

# Test ADX thresholds: 12, 15, 17, 20
for threshold in 12 15 17 20:
    python src/cli/build_rangefader_v5.py \
      --config Config/Copper/rangefader_v5.yaml \
      --adx-override $threshold \
      --outdir outputs/Copper/RangeFader_v5_adx_$threshold
```

**Check Results:**
- [ ] Review outputs/Copper/RangeFader_v5_adx_*/summary_metrics.json
- [ ] Focus on 2024-2025 performance specifically
- [ ] If ADX 15 or 12 fixes 2024-2025 → Quick deploy, skip overlays
- [ ] If all fail → Confirms need for overlays, proceed to Phase 2

### Day 3-4: Regime Analysis

```python
# Run diagnostic script
python << 'EOF'
import pandas as pd
from src.signals.rangefader_v5 import calculate_adx_ohlc

# Load data
df = pd.read_csv('Data/copper/pricing/canonical/copper_lme_3mo.canonical.csv')
df_high = pd.read_csv('Data/copper/pricing/canonical/copper_lme_3mo_high.canonical.csv')
df_low = pd.read_csv('Data/copper/pricing/canonical/copper_lme_3mo_low.canonical.csv')

# Calculate ADX for different periods
periods = {
    'Full': ('2000-01-01', '2025-11-06'),
    'Good OOS': ('2019-01-01', '2023-12-31'),
    'Bad OOS': ('2024-01-01', '2025-11-06')
}

for name, (start, end) in periods.items():
    df_period = df[(df['date'] >= start) & (df['date'] <= end)]
    adx = calculate_adx_ohlc(df_period['high'], df_period['low'], df_period['price'])
    
    print(f"\n{name}:")
    print(f"  Mean ADX: {adx.mean():.1f}")
    print(f"  ADX < 20: {(adx < 20).mean()*100:.1f}%")
    print(f"  Price trend (90d): {df_period['price'].diff(90).mean():.2f}")
EOF
```

**Check Results:**
- [ ] Is 2024-2025 ADX distribution similar to other periods?
- [ ] Is 2024-2025 price trend stronger (more directional)?
- [ ] Document findings for overlay design

### Day 5: Decision Point 1

**IF ADX threshold fix works:**
- ✓ Update rangefader_v5.yaml with better threshold
- ✓ Run full backtest
- ✓ Deploy with monitoring
- ✓ DONE (skip to Phase 5)

**IF ADX threshold doesn't help:**
- ✓ Confirms macro confusion issue
- ✓ Proceed to Phase 2 (ChopCore)

---

## Phase 2: ChopCore Overlay (Weeks 2-3)

### Week 2 Day 1-2: Data Collection

**Bloomberg Terminal:**
```
# China demand proxies
CHPRSTOT Index  # Property starts (monthly)
CPMINDX Index   # PMI (monthly)

# Inventory data
COPISHFE Comdty # SHFE stocks (weekly)
LMCADS03 Comdty # LME stocks (daily)

# Volatility
VIX Index       # General uncertainty (daily)
```

**Save to:**
- [ ] Data/copper/macro/china_property_starts.csv
- [ ] Data/copper/macro/china_pmi.csv
- [ ] Data/copper/inventories/shfe_stocks.csv
- [ ] Data/copper/inventories/lme_stocks.csv
- [ ] Data/macro/vix.csv

**Free Sources:**
- [ ] Policy Uncertainty Index: www.policyuncertainty.com
- [ ] Download and save to Data/macro/policy_uncertainty.csv

### Week 2 Day 3-5: ChopCore v1 Implementation

**Create file:** `src/overlays/chopcore_v1.py`

```python
"""
ChopCore v1 - Macro Confusion Detector
=======================================
Detects when market is in macro confusion (structural moves appearing choppy).

Returns confusion score 0-1:
  0 = Clear regime (safe to trade mean reversion)
  1 = Max confusion (go flat)
"""

import pandas as pd
import numpy as np

def china_demand_momentum(date: pd.Timestamp, lookback: int = 90) -> float:
    """
    Calculate China demand trend strength.
    Returns 0-1, higher = weaker trend (more concerning)
    """
    # Load data
    pmi = pd.read_csv('Data/copper/macro/china_pmi.csv', parse_dates=['date'])
    prop = pd.read_csv('Data/copper/macro/china_property_starts.csv', parse_dates=['date'])
    
    # Get recent window
    pmi_recent = pmi[pmi['date'] <= date].tail(3)  # Last 3 months
    prop_recent = prop[prop['date'] <= date].tail(3)
    
    # Calculate momentum (negative = weakening)
    pmi_mom = pmi_recent['value'].pct_change().mean()
    prop_mom = prop_recent['value'].pct_change().mean()
    
    # Convert to 0-1 score (0=strong, 1=weak)
    pmi_score = 1 - (pmi_mom + 1) / 2  # Normalize
    prop_score = 1 - (prop_mom + 1) / 2
    
    return (pmi_score + prop_score) / 2

def policy_uncertainty_index(date: pd.Timestamp) -> float:
    """
    Policy uncertainty score.
    Returns 0-1, higher = more uncertain
    """
    # Load EPU index
    epu = pd.read_csv('Data/macro/policy_uncertainty.csv', parse_dates=['date'])
    epu = epu[epu['date'] <= date]
    
    # Get percentile (0-1)
    current = epu.iloc[-1]['value']
    percentile = (epu['value'] < current).mean()
    
    return percentile

def regime_stability(date: pd.Timestamp, lookback: int = 60) -> float:
    """
    Market regime stability score.
    Returns 0-1, higher = less stable
    """
    # Load price data
    df = pd.read_csv('Data/copper/pricing/canonical/copper_lme_3mo.canonical.csv', 
                     parse_dates=['date'])
    df = df[df['date'] <= date].tail(lookback)
    
    # Calculate regime changes (using simple vol clustering)
    returns = df['price'].pct_change()
    vol = returns.rolling(20).std()
    vol_changes = vol.diff().abs()
    
    # Normalize to 0-1
    instability = vol_changes.mean() / vol_changes.std() if vol_changes.std() > 0 else 0
    instability = min(instability, 1.0)
    
    return instability

def fundamental_confusion(date: pd.Timestamp) -> float:
    """
    Fundamental signals confusion (mixed messages).
    Returns 0-1, higher = more confused
    """
    # Load inventory and spread data
    lme_stocks = pd.read_csv('Data/copper/inventories/lme_stocks.csv', parse_dates=['date'])
    lme_stocks = lme_stocks[lme_stocks['date'] <= date]
    
    # Inventory direction (building = confusion)
    inv_change = lme_stocks['value'].pct_change(20).iloc[-1]  # 20-day change
    inv_score = max(0, inv_change)  # Only care about building, not drawing
    
    # Add other signals here (time spreads, TC/RCs, etc.)
    
    return inv_score

def chopcore_signal(date: pd.Timestamp, 
                   china_weight: float = 0.30,
                   policy_weight: float = 0.25,
                   regime_weight: float = 0.25,
                   fundamental_weight: float = 0.20) -> float:
    """
    Master confusion score.
    
    Returns:
        float: Confusion score 0-1 (higher = more confused, don't trade)
    """
    china_score = china_demand_momentum(date)
    policy_score = policy_uncertainty_index(date)
    regime_score = regime_stability(date)
    fundamental_score = fundamental_confusion(date)
    
    confusion = (
        china_weight * china_score +
        policy_weight * policy_score +
        regime_weight * regime_score +
        fundamental_weight * fundamental_score
    )
    
    return confusion
```

**Checklist:**
- [ ] File created: src/overlays/chopcore_v1.py
- [ ] All four scoring functions implemented
- [ ] Data loading works for all sources
- [ ] Returns 0-1 scores as expected

### Week 3 Day 1-3: ChopCore Testing

**Create test script:** `test_chopcore.py`

```python
import pandas as pd
from src.overlays.chopcore_v1 import chopcore_signal

# Test on known periods
test_dates = {
    'COVID Crash (Should be low)': '2020-03-15',
    'China Weak (Should be high)': '2024-06-15',
    'Normal (Should be medium)': '2021-06-15',
}

print("ChopCore Test Results:")
print("=" * 60)

for name, date in test_dates.items():
    score = chopcore_signal(pd.Timestamp(date))
    print(f"\n{name}:")
    print(f"  Date: {date}")
    print(f"  Confusion Score: {score:.3f}")
    
    if score < 0.3:
        print(f"  Assessment: LOW confusion - safe to trade")
    elif score < 0.6:
        print(f"  Assessment: MEDIUM confusion - cautious")
    else:
        print(f"  Assessment: HIGH confusion - avoid trading")
```

**Expected Results:**
- [ ] COVID 2020: Low confusion (~0.2-0.3)
- [ ] China weak 2024: High confusion (~0.7-0.8)
- [ ] Normal 2021: Medium confusion (~0.4-0.5)

**If scores don't match expectations:**
- [ ] Adjust component weights
- [ ] Review scoring functions
- [ ] Check data quality

### Week 3 Day 4-5: Integrate with RangeFader

**Modify:** `src/signals/rangefader_v5.py`

```python
# Add at top of file
from src.overlays.chopcore_v1 import chopcore_signal

# In generate_rangefader_signal() function, after ADX check:
def generate_rangefader_signal(
    df: pd.DataFrame,
    lookback_window: int = 60,
    zscore_entry: float = 0.7,
    zscore_exit: float = 0.2,
    adx_threshold: float = 20.0,
    adx_window: int = 14,
    update_frequency: int = 1,
    enable_chopcore: bool = False,  # NEW
    confusion_threshold: float = 0.5,  # NEW
) -> pd.Series:
    
    # ... existing code ...
    
    # After calculating is_choppy:
    is_choppy = adx < adx_threshold
    
    # NEW: Add confusion filter
    if enable_chopcore:
        confusion_scores = pd.Series(index=df.index, dtype=float)
        for date in df.index:
            confusion_scores.loc[date] = chopcore_signal(date)
        
        is_confused = confusion_scores > confusion_threshold
        is_choppy = is_choppy & ~is_confused  # Only choppy AND not confused
    
    # ... rest of existing code ...
```

**Test integration:**
```bash
python src/cli/build_rangefader_v5.py \
  --config Config/Copper/rangefader_v5.yaml \
  --enable-chopcore \
  --confusion-threshold 0.5 \
  --outdir outputs/Copper/RangeFader_v5_chopcore
```

**Checklist:**
- [ ] Integration successful (no errors)
- [ ] ChopCore reduces activity in 2024-2025
- [ ] ChopCore doesn't block 2019-2021 (good periods)

### Week 3 End: Decision Point 2

**Review Results:**
```python
# Compare baseline vs chopcore
import pandas as pd

baseline = pd.read_json('outputs/Copper/RangeFader_v5/summary_metrics.json')
chopcore = pd.read_json('outputs/Copper/RangeFader_v5_chopcore/summary_metrics.json')

print("Impact of ChopCore:")
print(f"Overall Sharpe: {baseline['net_sharpe']:.3f} → {chopcore['net_sharpe']:.3f}")
print(f"Activity: {baseline['activity_pct']:.1f}% → {chopcore['activity_pct']:.1f}%")

# Load daily series and check 2024-2025 specifically
df_base = pd.read_csv('outputs/Copper/RangeFader_v5/daily_series.csv')
df_chop = pd.read_csv('outputs/Copper/RangeFader_v5_chopcore/daily_series.csv')

df_base_24 = df_base[df_base['date'] >= '2024-01-01']
df_chop_24 = df_chop[df_chop['date'] >= '2024-01-01']

sharpe_base_24 = (df_base_24['pnl_net'].mean() / df_base_24['pnl_net'].std()) * np.sqrt(252)
sharpe_chop_24 = (df_chop_24['pnl_net'].mean() / df_chop_24['pnl_net'].std()) * np.sqrt(252)

print(f"\n2024-2025 Improvement:")
print(f"Baseline: {sharpe_base_24:.3f}")
print(f"ChopCore: {sharpe_chop_24:.3f}")
```

**IF ChopCore improves 2024-2025 to >0:**
- ✓ Proceed to Phase 3 (TightnessIndex)

**IF ChopCore doesn't help:**
- ⚠️  Review component scores (are they detecting confusion?)
- ⚠️  Adjust weights or thresholds
- ⚠️  If still fails, consider abandoning RangeFader

---

## Phase 3: TightnessIndex Overlay (Weeks 4-5)

### Week 4: TightnessIndex Implementation

**Create file:** `src/overlays/tightness_v1.py`

```python
"""
TightnessIndex v1 - Market Tightness Detector
==============================================
Only allow mean reversion when market is tight (not building inventory).
"""

def inventory_drawdown_rate(date: pd.Timestamp, lookback: int = 90) -> float:
    """Returns 0-1, higher = faster drawdown (tighter)"""
    # Implementation here
    pass

def iscg_balance_normalized(date: pd.Timestamp) -> float:
    """Returns 0-1, 1=deficit (tight), 0=surplus (loose)"""
    # Implementation here
    pass

def time_spread_percentile(date: pd.Timestamp) -> float:
    """Returns 0-1, higher = more backwardated (tighter)"""
    # Implementation here
    pass

def tightness_score(date: pd.Timestamp) -> float:
    """Master tightness score 0-1"""
    # Combine components
    pass
```

**Checklist:**
- [ ] Inventory data loaded correctly
- [ ] ISCG balance interpolated to daily
- [ ] Time spreads calculated
- [ ] Scores make sense on known tight/loose periods

### Week 5: Integration & Testing

**Integrate with RangeFader + ChopCore:**

```python
# In generate_rangefader_signal():
if enable_tightness:
    tightness_scores = pd.Series(index=df.index, dtype=float)
    for date in df.index:
        tightness_scores.loc[date] = tightness_score(date)
    
    is_tight = tightness_scores > tightness_threshold
    is_choppy = is_choppy & is_tight  # Only choppy AND tight
```

**Test combined system:**
```bash
python src/cli/build_rangefader_v5.py \
  --config Config/Copper/rangefader_v5.yaml \
  --enable-chopcore \
  --enable-tightness \
  --outdir outputs/Copper/RangeFader_v5_full
```

**Checklist:**
- [ ] Both overlays working together
- [ ] 2024-2025 Sharpe > 0 (or at least > -0.3)
- [ ] Overall Sharpe still >0.30
- [ ] Activity reduced but quality improved

---

## Phase 4: Validation (Week 6)

### Walk-Forward Test

```python
# Create test script: scripts/validate_rangefader_overlays.py

import pandas as pd
from src.signals.rangefader_v5 import generate_rangefader_signal

# Expanding window walk-forward
test_periods = [
    ('2000-01-01', '2019-12-31', '2020-01-01', '2020-12-31'),  # Test 2020
    ('2000-01-01', '2020-12-31', '2021-01-01', '2021-12-31'),  # Test 2021
    ('2000-01-01', '2021-12-31', '2022-01-01', '2022-12-31'),  # Test 2022
    ('2000-01-01', '2022-12-31', '2023-01-01', '2023-12-31'),  # Test 2023
    ('2000-01-01', '2023-12-31', '2024-01-01', '2024-12-31'),  # Test 2024
]

results = []
for train_start, train_end, test_start, test_end in test_periods:
    # Optimize overlay thresholds on train
    # Test on test period
    # Record Sharpe
    pass

# Check results
print("Walk-Forward Results:")
for i, (sharpe, period) in enumerate(results):
    print(f"  {period}: {sharpe:.3f}")
```

**Success Criteria:**
- [ ] All test periods Sharpe > 0
- [ ] 2024 test period Sharpe > 0 (critical)
- [ ] No period < -0.3
- [ ] Average across periods >0.25

---

## Phase 5: Deployment (Weeks 7-8)

### Week 7: Production Prep

**Checklist:**
- [ ] All code in proper structure (src/overlays/, src/cli/)
- [ ] Configuration updated in rangefader_v5.yaml
- [ ] Batch runner works end-to-end
- [ ] Documentation complete
- [ ] Git commit with proper version tag

### Week 8: Monitoring Setup

**Create:** `src/cli/monitor_rangefader_v5.py`

```python
"""Daily monitoring dashboard for RangeFader v5"""

import pandas as pd
from datetime import datetime, timedelta

# Load latest data
# Calculate current metrics
# Display dashboard

print("=" * 70)
print("RANGEFADER V5 DAILY MONITOR")
print("=" * 70)

# Current position
# Current ADX
# ChopCore score
# TightnessIndex score
# 30/60/90-day rolling Sharpe
# Alerts
```

**Set up alerts:**
- [ ] 30-day Sharpe < -0.5 → Email alert
- [ ] Drawdown > -15% → Email alert
- [ ] ChopCore score >0.7 for 30 days → Note in log

### Deploy Decision

**Final Checklist:**

| Item | Status |
|------|--------|
| ChopCore built & tested | [ ] |
| TightnessIndex built & tested | [ ] |
| 2024-2025 Sharpe > 0 | [ ] |
| Full sample Sharpe > 0.30 | [ ] |
| Walk-forward validates | [ ] |
| Monitoring ready | [ ] |
| Risk controls documented | [ ] |

**Only deploy if ALL boxes checked.**

---

## Emergency Contacts & Resources

### Data Issues
- Bloomberg Terminal in office
- Canonical data pipeline: `Data/copper/pricing/canonical/`
- ISCG balance: `copper_balance_values.xlsx`

### Research Papers
- Policy Uncertainty: www.policyuncertainty.com
- Mean Reversion: Lo & MacKinlay (1988)
- Regime Detection: Hamilton (1989)

### Support Files
- Full docs: `RANGEFADER_V5_COMPLETE_DOCUMENTATION.md`
- Optimization results: `outputs/Copper/RangeFader_v5_optimization/`
- Current backtest: `outputs/Copper/RangeFader_v5/`

---

## Quick Decision Tree

```
START HERE
    ↓
Run ADX threshold test (Day 1-2)
    ↓
Does ADX < 15 fix 2024-2025?
    ├─ YES → Quick deploy, DONE
    └─ NO → Continue
        ↓
    Build ChopCore (Week 2-3)
        ↓
    Does ChopCore improve 2024-2025?
        ├─ YES → Continue to TightnessIndex
        └─ NO → Review/abandon
            ↓
        Build TightnessIndex (Week 4-5)
            ↓
        Does combined system work?
            ├─ YES → Deploy
            └─ NO → Consider alternatives
```

---

## Expected Time Investment

| Phase | Best Case | Expected | Worst Case |
|-------|-----------|----------|------------|
| Diagnostics | 2 days | 3 days | 5 days |
| ChopCore | 1 week | 2 weeks | 3 weeks |
| TightnessIndex | 1 week | 2 weeks | 3 weeks |
| Testing | 3 days | 5 days | 1 week |
| Deploy Prep | 3 days | 1 week | 2 weeks |
| **TOTAL** | **4 weeks** | **6 weeks** | **10 weeks** |

---

## When to Abandon

**Stop working on RangeFader v5 if:**
- [ ] ChopCore doesn't improve 2024-2025 at all
- [ ] Combined overlays still give negative Sharpe 2024-2025
- [ ] Timeline exceeds 10 weeks
- [ ] Aluminum pipeline ready (do spreads instead)
- [ ] VolCore shows more promise (pivot there)

**Alternative:** Focus on trend strategies (already working) and add VolCore for diversification.

---

**Last Updated:** 2025-11-19  
**Next Review:** When ready to resume RangeFader work  
**Priority:** MEDIUM (have working alternatives)
