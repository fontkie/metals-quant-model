# Chinese Demand Overlay - Complete Workflow

**Date:** November 18, 2025  
**Status:** Production-ready with canonical data conversion  
**Performance:** +0.07 Sharpe (OOS, 2-month lag)

---

## Complete File List (All Ready to Download)

### 🔄 Data Conversion (Step 1)
1. **[make_canonical_copper_demand.py](computer:///mnt/user-data/outputs/make_canonical_copper_demand.py)** → `C:\Code\Metals\tools\`
2. **[run_make_canonical_copper_demand.bat](computer:///mnt/user-data/outputs/run_make_canonical_copper_demand.bat)** → `C:\Code\Metals\`
3. **[CANONICAL_CONVERSION_GUIDE.md](computer:///mnt/user-data/outputs/CANONICAL_CONVERSION_GUIDE.md)** → Reference guide

### 🎯 Core Overlay (Step 2)
4. **[chinese_demand.py](computer:///mnt/user-data/outputs/chinese_demand.py)** → `C:\Code\Metals\src\overlays\`
5. **[build_chinese_demand.py](computer:///mnt/user-data/outputs/build_chinese_demand.py)** → `C:\Code\Metals\src\cli\`
6. **[chinese_demand.yaml](computer:///mnt/user-data/outputs/chinese_demand.yaml)** → `C:\Code\Metals\Config\copper\`
7. **[run_chinese_demand.bat](computer:///mnt/user-data/outputs/run_chinese_demand.bat)** → `C:\Code\Metals\`

### 📚 Documentation
8. **[PROJECT_COMPLETE.md](computer:///mnt/user-data/outputs/PROJECT_COMPLETE.md)** - Project summary
9. **[INSTALLATION_INSTRUCTIONS.md](computer:///mnt/user-data/outputs/INSTALLATION_INSTRUCTIONS.md)** - Quick setup
10. **[SETUP_GUIDE.md](computer:///mnt/user-data/outputs/SETUP_GUIDE.md)** - Detailed usage
11. **[VALIDATION_RESULTS.md](computer:///mnt/user-data/outputs/VALIDATION_RESULTS.md)** - Test results

### 🧪 Testing (Optional)
12. **[validate_chinese_demand.py](computer:///mnt/user-data/outputs/validate_chinese_demand.py)** - Validation suite

---

## Complete Workflow (3 Steps)

### Step 1: Convert Demand Data to Canonical Format ✨ NEW

**What:** Convert Bloomberg Excel to standard CSV format

**Files needed:**
- Input: `C:\Code\Metals\Data\copper\fundamentals\china_demand_values.xlsx`
- Script: `make_canonical_copper_demand.py` → Goes in `tools\`
- Batch: `run_make_canonical_copper_demand.bat` → Goes in root

**Installation:**
```batch
REM Copy scripts
copy make_canonical_copper_demand.py C:\Code\Metals\tools\
copy run_make_canonical_copper_demand.bat C:\Code\Metals\
```

**Run conversion:**
```batch
cd C:\Code\Metals
run_make_canonical_copper_demand.bat
```

**Expected output:**
```
C:\Code\Metals\Data\copper\fundamentals\canonical\chinese_demand_proxy.canonical.csv
```

**Format:**
```csv
date,demand_index
2012-04-30,7.4
2012-05-31,7.7
2012-06-30,5.9
...
```

**Troubleshooting:**
- Sheet not found? Edit script line 83 (change `"Raw"` to your sheet name)
- Column not found? Edit script line 84, 86 (update column names)
- See CANONICAL_CONVERSION_GUIDE.md for details

---

### Step 2: Install Overlay Code

**What:** Copy overlay module and build scripts to your project

**Files needed:**
- `chinese_demand.py` → `src\overlays\`
- `build_chinese_demand.py` → `src\cli\`
- `chinese_demand.yaml` → `Config\copper\`
- `run_chinese_demand.bat` → Root directory

**Installation:**
```batch
REM Copy overlay files
copy chinese_demand.py C:\Code\Metals\src\overlays\
copy build_chinese_demand.py C:\Code\Metals\src\cli\
copy chinese_demand.yaml C:\Code\Metals\Config\copper\
copy run_chinese_demand.bat C:\Code\Metals\

REM Create __init__.py if needed
echo. > C:\Code\Metals\src\overlays\__init__.py
```

**Verify paths in config:**
Edit `Config\copper\chinese_demand.yaml` line 53 - should already be correct:
```yaml
data:
  demand_proxy:
    filepath: "Data/copper/fundamentals/canonical/chinese_demand_proxy.canonical.csv"
```

---

### Step 3: Build and Run Overlay

**What:** Apply overlay to your baseline portfolio

**Prerequisites:**
- ✅ Canonical demand data created (Step 1)
- ✅ Overlay code installed (Step 2)
- ✅ Baseline portfolio exists (e.g., `daily_series_blended_33pct_20251118.csv`)

**Run build:**
```batch
cd C:\Code\Metals
run_chinese_demand.bat
```

**Expected output:**
```
outputs\Copper\ChineseDemand\
├── daily_series_china_demand_2mo_20251118.csv
├── summary_metrics_2mo_20251118.json
└── summary_2mo_20251118.txt
```

**Success criteria:**
- ✅ Sharpe improvement ~0.07 (±0.01)
- ✅ NEUTRAL regime validation passes
- ✅ No errors in console output

---

## Visual Workflow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: Convert Data to Canonical Format                    │
│                                                              │
│ Input:  china_demand_values.xlsx                            │
│         └─ Raw sheet with Date + demand columns             │
│                                                              │
│ Script: run_make_canonical_copper_demand.bat                │
│         └─ Calls: tools\make_canonical_copper_demand.py     │
│                                                              │
│ Output: canonical\chinese_demand_proxy.canonical.csv        │
│         └─ Format: date,demand_index                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: Install Overlay Code                                │
│                                                              │
│ Files:                                                       │
│   src\overlays\chinese_demand.py                            │
│   src\cli\build_chinese_demand.py                           │
│   Config\copper\chinese_demand.yaml                         │
│   run_chinese_demand.bat                                    │
│                                                              │
│ Config: Set filepath in YAML (should auto-detect)           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: Build Overlay                                       │
│                                                              │
│ Input:  daily_series_blended_33pct_*.csv (baseline)         │
│         chinese_demand_proxy.canonical.csv (demand data)    │
│                                                              │
│ Script: run_chinese_demand.bat                              │
│         └─ Calls: src\cli\build_chinese_demand.py           │
│                                                              │
│ Output: daily_series_china_demand_2mo_*.csv                 │
│         summary_metrics_2mo_*.json                          │
│         summary_2mo_*.txt                                   │
│                                                              │
│ Result: +0.07 Sharpe improvement ✅                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Reference: File Locations

| What | Where |
|------|-------|
| **INPUT: Excel data** | `Data\copper\fundamentals\china_demand_values.xlsx` |
| **OUTPUT: Canonical CSV** | `Data\copper\fundamentals\canonical\chinese_demand_proxy.canonical.csv` |
| **SCRIPT: Conversion** | `tools\make_canonical_copper_demand.py` |
| **SCRIPT: Overlay** | `src\overlays\chinese_demand.py` |
| **SCRIPT: Build** | `src\cli\build_chinese_demand.py` |
| **CONFIG: Parameters** | `Config\copper\chinese_demand.yaml` |
| **RUN: Conversion** | `run_make_canonical_copper_demand.bat` |
| **RUN: Overlay** | `run_chinese_demand.bat` |
| **OUTPUT: Results** | `outputs\Copper\ChineseDemand\` |

---

## Adjusting the Lag Parameter

You can adjust the publication lag in 3 places:

### 1. Default in YAML (Recommended)
Edit `Config\copper\chinese_demand.yaml` line 25:
```yaml
overlay:
  lag_months: 2  # Change to 0, 1, or 2
```

### 2. Override in Batch File
Edit `run_chinese_demand.bat` line 23:
```batch
set LAG_OVERRIDE=--lag 1  # Uncomment and set
```

### 3. Command Line (Testing)
```batch
python src\cli\build_chinese_demand.py --lag 1 --baseline [...] --config [...]
```

**Expected performance by lag:**
- 0-month: +0.11 Sharpe (unrealistic)
- 1-month: +0.08 Sharpe (investigate!)
- 2-month: +0.07 Sharpe (production default)

---

## Common Issues & Solutions

### Issue: "Excel file not found"
**Solution:** Check that `china_demand_values.xlsx` exists in the fundamentals folder

### Issue: "Sheet 'Raw' not found"
**Solution:** Edit `make_canonical_copper_demand.py` line 83 with your sheet name

### Issue: "Column 'Date' not found"
**Solution:** Edit `make_canonical_copper_demand.py` line 84 with your date column name

### Issue: "Canonical CSV has wrong column names"
**Solution:** 
- Should have: `date,demand_index`
- Check that series name contains "demand" or "proxy"

### Issue: "Config file not found"
**Solution:** Ensure `chinese_demand.yaml` is in `Config\copper\`

### Issue: "Baseline missing required columns"
**Solution:** Baseline needs: date, price, ret, pos, cost, pnl_net

### Issue: "ModuleNotFoundError: No module named 'overlays'"
**Solution:** Create `__init__.py`:
```batch
echo. > C:\Code\Metals\src\overlays\__init__.py
```

### Issue: "NEUTRAL regime doesn't match baseline"
**Solution:** This indicates a bug - contact support (should pass automatically)

---

## Testing Different Configurations

### Test All Lags
```batch
REM 0-month lag
python src\cli\build_chinese_demand.py --lag 0 [...] --outdir outputs\Copper\ChineseDemand\Lag0

REM 1-month lag
python src\cli\build_chinese_demand.py --lag 1 [...] --outdir outputs\Copper\ChineseDemand\Lag1

REM 2-month lag
python src\cli\build_chinese_demand.py --lag 2 [...] --outdir outputs\Copper\ChineseDemand\Lag2
```

### Test Scale Factors
```batch
python src\cli\build_chinese_demand.py --scale 1.2 [...] --outdir [...]\Scale1.2
python src\cli\build_chinese_demand.py --scale 1.4 [...] --outdir [...]\Scale1.4
```

---

## Validation Checklist

### ✅ Step 1: Data Conversion
- [ ] Excel file exists at correct location
- [ ] Canonical CSV created successfully
- [ ] Format is: `date,demand_index`
- [ ] At least 100+ rows of data
- [ ] Dates are month-end format

### ✅ Step 2: Code Installation
- [ ] All 4 core files copied to correct locations
- [ ] `__init__.py` exists in `src\overlays\`
- [ ] Config filepath matches canonical CSV location
- [ ] Baseline portfolio file exists

### ✅ Step 3: Overlay Build
- [ ] Build runs without errors
- [ ] Output files created
- [ ] Sharpe improvement ~0.07 (±0.01)
- [ ] NEUTRAL regime validation passes
- [ ] Summary looks reasonable

---

## Next Steps After Installation

1. **Week 1:** Paper trade with live updates
2. **Month 1:** Validate performance vs backtest
3. **Month 3:** Consider scaling allocation
4. **Month 6:** Add other overlays (TightnessIndex, StimulusCore)

---

## Support & Documentation

**Start here:**
- [PROJECT_COMPLETE.md](computer:///mnt/user-data/outputs/PROJECT_COMPLETE.md) - Overall summary

**Data conversion:**
- [CANONICAL_CONVERSION_GUIDE.md](computer:///mnt/user-data/outputs/CANONICAL_CONVERSION_GUIDE.md) - Conversion details

**Installation:**
- [INSTALLATION_INSTRUCTIONS.md](computer:///mnt/user-data/outputs/INSTALLATION_INSTRUCTIONS.md) - Quick setup

**Usage:**
- [SETUP_GUIDE.md](computer:///mnt/user-data/outputs/SETUP_GUIDE.md) - Detailed usage guide

**Performance:**
- [VALIDATION_RESULTS.md](computer:///mnt/user-data/outputs/VALIDATION_RESULTS.md) - Test results

---

## Summary

**What you have:**
- ✅ Data conversion script (Excel → canonical CSV)
- ✅ Production overlay code (demand regime scaling)
- ✅ Build scripts (following your infrastructure)
- ✅ Complete documentation
- ✅ Validated performance (+0.07 Sharpe OOS)

**What to do:**
1. Run `run_make_canonical_copper_demand.bat` (convert data)
2. Copy overlay files to project (install code)
3. Run `run_chinese_demand.bat` (build overlay)
4. Verify ~0.07 Sharpe improvement ✅

**Time required:** ~10 minutes total

**Ready to deploy!** 🚀

---

**Status:** Complete workflow with data conversion ✅  
**Files:** 12 files ready to download  
**Performance:** +0.073 Sharpe validated  
**Infrastructure:** Follows your standards  
