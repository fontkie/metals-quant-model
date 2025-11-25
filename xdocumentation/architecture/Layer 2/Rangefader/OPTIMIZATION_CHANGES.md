# RangeFader V5 Optimization - Parameter Range Update

## Changes Made

### Entry Threshold Range
**OLD:** `[0.6, 0.8, 1.0, 1.2]` (4 values)  
**NEW:** `[0.6, 0.7, 0.8, 0.9, 1.0]` (5 values)

### Total Combinations
**OLD:** 180 combinations (5 × 4 × 3 × 3)  
**NEW:** 225 combinations (5 × 5 × 3 × 3)

### Estimated Runtime
**OLD:** 6-8 minutes  
**NEW:** 7-9 minutes

---

## Why This Change?

### Problem with Previous Optimization

Your first optimization found:
```yaml
entry: 1.2 std    # TOO WIDE
exit: 0.2 std
lookback: 70
adx_threshold: 15
```

**Results:**
- ✓ Excellent Sharpe: 2.06 OOS choppy Sharpe (incredible!)
- ✗ Too selective: Only 3-5% activity
- ✗ **Failed validation: 52.7% activity in choppy (target >60%)**

### Root Cause

The **1.2 std entry** forces the strategy to wait for extreme moves, creating:
- High quality trades (great Sharpe)
- But too infrequent (misses many choppy opportunities)
- Doesn't fulfill the role of "choppy market specialist"

This is a **"cherry-picking" solution** rather than a robust mean reversion strategy.

---

## What the New Range Does

### More Granular Search
```
OLD: [0.6, ----, 0.8, ----, 1.0, ----, 1.2]  (large gaps)
NEW: [0.6, 0.7, 0.8, 0.9, 1.0, ----]         (0.1 increments)
```

### Benefits
1. **Finer resolution** in the 0.6-1.0 range where optimal likely exists
2. **Removes 1.2** which proved too wide
3. **Better balance** between activity and quality
4. **More likely to pass validation** (>60% activity in choppy)

### Expected Outcome

The optimizer should find parameters that:
- ✓ Still achieve good Sharpe (0.40-0.60 choppy Sharpe)
- ✓ Higher activity (8-15% vs 3-5%)
- ✓ Pass validation (>60% activity in choppy)
- ✓ Fulfill role as choppy market specialist

---

## Expected Results

### Activity Profile
```
Entry 1.2 → 3-5% activity   (too selective)
Entry 0.8 → 8-12% activity  (likely optimal)
Entry 0.6 → 15-20% activity (might be too noisy)
```

### Performance Expectations
```
IS Sharpe:  0.30-0.45 (vs 0.43 previously)
OOS Sharpe: 0.25-0.40 (vs 0.40 previously)
Choppy:     0.60-1.00 (vs 2.06 previously)
```

**Trade-off:** Slightly lower Sharpe, but much higher activity and regime fit.

---

## Run Instructions

1. **Run the new optimization:**
   ```
   run_rangefader_v5_optimize.bat
   ```

2. **Look for parameters with:**
   - Net Sharpe IS: >0.30
   - Net Sharpe OOS: >0.25
   - Choppy Sharpe: >0.60
   - Activity: 8-15%
   - **Validation: ALL PASS** ✓

3. **Likely optimal range:**
   - Entry: **0.7-0.9 std** (sweet spot)
   - Exit: 0.2-0.3 std
   - Lookback: 60-70 days
   - ADX: 15-17

---

## Philosophy

**Previous approach:** "Find the highest Sharpe possible"  
→ Found 2.06 OOS, but too selective (3% activity)

**New approach:** "Find robust mean reversion parameters"  
→ Target 0.60+ choppy Sharpe with 8-15% activity

**Goal:** A strategy that actually **fills the choppy market gap** (13% of time) rather than cherry-picking extreme moves.

---

## Next Steps After Optimization

1. **Review results** in `optimization_summary.json`
2. **Check validation passes** (all_passed: true)
3. **Verify activity** (target: 8-15%)
4. **Update config** in `rangefader_v5.yaml`
5. **Build full backtest** with `run_rangefader_v5.bat`
6. **Test in portfolio** with adaptive blending

---

## Files Modified

- `optimize_rangefader_v5.py` - Updated entry_range parameter
- `run_rangefader_v5_optimize.bat` - Updated parameter documentation

**Download both files and run the new optimization!**
