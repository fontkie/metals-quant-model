# BASELINE PORTFOLIO - INSTALLATION GUIDE

**Date:** November 19, 2025  
**Purpose:** Build equal-weight 3-sleeve portfolio (TM + MC + RF)  
**Expected Result:** 0.773 Sharpe

---

## INSTALLATION (5 MINUTES)

### Step 1: Create Folder Structure

```cmd
REM From your C:\Code\Metals directory:

mkdir src\portfolio
mkdir src\cli\portfolio
mkdir Config\Copper
mkdir outputs\Copper\Portfolio_Baseline
```

### Step 2: Copy Files

**Copy these files from /mnt/user-data/outputs/ to your project:**

```
From outputs/ → To your project:

blender.py                        → src\portfolio\blender.py
portfolio__init__.py              → src\portfolio\__init__.py
build_baseline_portfolio.py       → src\cli\portfolio\build_baseline_portfolio.py
portfolio_baseline.yaml           → Config\Copper\portfolio_baseline.yaml
run_build_baseline_portfolio.bat  → scripts\run_build_baseline_portfolio.bat
```

**Also create empty __init__.py:**
```cmd
REM Create empty file (makes it a Python package)
type nul > src\cli\portfolio\__init__.py
```

### Step 3: Update Config Paths

**Edit `Config\Copper\portfolio_baseline.yaml`:**

Update the sleeve paths to match your actual file locations:

```yaml
sleeves:
  TrendMedium: outputs/Copper/TrendMedium_v2/daily_series.csv
  MomentumCore: outputs/Copper/MomentumCore_v2/daily_series.csv
  RangeFader: outputs/Copper/RangeFader_v5/daily_series.csv
```

**If your files are named differently or in different locations, update accordingly.**

---

## USAGE

### Option A: Double-Click (Easiest)

```
Double-click: scripts\run_build_baseline_portfolio.bat
```

### Option B: Command Line

```cmd
REM Activate virtual environment
.venv\Scripts\activate.bat

REM Run builder
python src\cli\portfolio\build_baseline_portfolio.py ^
    --config Config\Copper\portfolio_baseline.yaml ^
    --outdir outputs\Copper\Portfolio_Baseline
```

---

## EXPECTED OUTPUT

After running, you should see:

```
Loading config from Config\Copper\portfolio_baseline.yaml...
Loading TrendMedium from outputs/Copper/TrendMedium_v2/daily_series.csv...
Loading MomentumCore from outputs/Copper/MomentumCore_v2/daily_series.csv...
Loading RangeFader from outputs/Copper/RangeFader_v5/daily_series.csv...

Loaded 3 sleeves
Date range: 2000-01-04 to 2025-11-12
Total days: 6747

Blending sleeves (equal-weight)...
Calculating attribution...
Calculating correlations...
Calculating IS/OOS metrics...

Saving daily series...
  Saved: outputs\Copper\Portfolio_Baseline\daily_series.csv
Saving summary metrics...
  Saved: outputs\Copper\Portfolio_Baseline\summary_metrics.json
Saving sleeve attribution...
  Saved: outputs\Copper\Portfolio_Baseline\sleeve_attribution.json
Saving correlation matrix...
  Saved: outputs\Copper\Portfolio_Baseline\correlation_matrix.csv
Saving validation report...
  Saved: outputs\Copper\Portfolio_Baseline\validation_report.txt

================================================================================
PORTFOLIO BUILD COMPLETE
================================================================================

Portfolio Sharpe:     0.773
IS Sharpe:            0.774
OOS Sharpe:           0.767
OOS/IS Ratio:         99.0%
Diversification:      +42.5%

Outputs saved to: outputs\Copper\Portfolio_Baseline

Next step: Review validation_report.txt
```

---

## VALIDATION

**Check these numbers match:**

```
Expected:
  Portfolio Sharpe (Full):  0.773
  IS Sharpe (2000-2019):    0.774
  OOS Sharpe (2020-2025):   0.767
  OOS/IS Ratio:             99.0%
  Diversification Benefit:  +42-43%
```

**Open:** `outputs\Copper\Portfolio_Baseline\validation_report.txt`

Should show:
- ✅ Portfolio Sharpe > 0
- ✅ Diversification benefit: +42-43%
- ✅ OOS retention: 99.0% (good)
- ✅ Low avg correlation: ~0.00 (good diversification)

---

## OUTPUT FILES

**Created in `outputs\Copper\Portfolio_Baseline\`:**

1. **daily_series.csv**
   - Date, TrendMedium PnL, MomentumCore PnL, RangeFader PnL, Portfolio PnL
   - Full time series for further analysis

2. **summary_metrics.json**
   - Portfolio Sharpe, returns, vol
   - IS/OOS breakdown
   - Diversification metrics
   - Configuration used

3. **sleeve_attribution.json**
   - Individual sleeve performance
   - Portfolio performance
   - Detailed metrics

4. **correlation_matrix.csv**
   - Pairwise correlations between sleeves
   - Should show near-zero average (~0.00)

5. **validation_report.txt**
   - Human-readable summary
   - Pass/fail checks
   - Ready to share with risk managers

---

## TROUBLESHOOTING

### Error: "No module named 'portfolio'"

**Fix:** Make sure you created `src\portfolio\__init__.py`

### Error: "FileNotFoundError: [file] not found"

**Fix:** Update paths in `Config\Copper\portfolio_baseline.yaml` to match your actual file locations

### Error: "Sleeve missing 'pnl_net' column"

**Fix:** Your sleeve files need a `pnl_net` column (Layer 4 output). These should already exist in your TM/MC/RF daily_series.csv files.

### Numbers don't match (0.773 Sharpe)

**Check:**
1. Are you using the correct sleeve files (TM v2, MC v2, RF v5)?
2. Do the files have recent data (through Nov 2025)?
3. Run on command line to see error messages

---

## WHAT'S NEXT?

Once baseline is working (0.773 Sharpe validated):

### Phase 1: Regime-Adaptive Weights
- Add ADX-based regime detection
- Adjust TM/MC/RF weights by regime
- Expected: +0.03-0.05 Sharpe → **0.80+ target**

### Phase 2: CopperDemand Overlay
- Add China demand scalar (your fundamental edge)
- Scale positions by demand YoY
- Expected: +0.05-0.07 Sharpe → **0.82-0.87 target**

### Phase 3: Additional Overlays
- TightnessIndex (supply disruption amplifier)
- Other fundamental overlays as validated

---

## CODE ARCHITECTURE

**What you built:**

```
Layer 1: Signal Generation     (in each sleeve already)
Layer 2: Vol Targeting         (in each sleeve already)
Layer 3: Portfolio Blending    (blender.py) ← YOU BUILT THIS
Layer 4: Costs & Execution     (in each sleeve already)
```

**Layer 3 responsibilities:**
- Combine sleeve PnLs
- Apply weights (equal for now, regime-adaptive later)
- Calculate attribution
- Generate metrics

**Future Layer 3 enhancements:**
- Regime-based weights
- Fundamental overlays
- Dynamic allocation
- Risk management overlays

---

## SUPPORT

**If you get stuck:**
1. Check validation_report.txt for error details
2. Verify file paths in config YAML
3. Ensure sleeve files have pnl_net column
4. Check Python version (3.8+)

**Common fixes:**
- Path separators: Use forward slashes (/) in YAML, even on Windows
- Virtual environment: Make sure .venv is activated
- Package imports: Ensure __init__.py files exist

---

**Status:** Ready to install ✅  
**Time:** ~5 minutes  
**Difficulty:** Easy (copy files, update config, run)

**Let's build your baseline! 🚀**
