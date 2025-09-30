# Base Metals Quant Model

## Workflow Overview
Pipeline = **Excel → SQLite DB → Signals → Sanity Check → Backtest**

### Steps (one-button run)
1. Place your Excel file at `Copper/pricing_values.xlsx`  
   - Tab name: `Raw`  
   - Column A: `Date`  
   - Other columns: prices (e.g. `copper_lme_3mo`, `copper_lme_cash_3mo`)  
2. Double-click `Run_All.bat`  
3. Outputs appear in `outputs/Copper/...`

### What Run_All.bat does
1. **Loader**  
   - `load_data.py`  
   - Reads Excel (`Raw` sheet) → cleans headers → writes `prices` table into `Copper/quant.db`  

2. **Signals**  
   - `build_signals.py`  
   - Reads `prices` → creates `prices_std` view & `signals` table  
   - Exports CSV to `outputs/Copper/Copper/signals_export.csv`  

3. **Sanity Checks**  
   - `test_db.py`  
   - Confirms row counts and date ranges for `prices_std` and `signals`  

4. **Backtest**  
   - `backtest_prices.py`  
   - Reads from DB (`prices_std` + `signals`)  
   - Saves charts + summary into `outputs/Copper/...`

### Environment
- Python 3.x
- Virtual environment stored in `.venv/`
- Dependencies: pandas, numpy, matplotlib, openpyxl, sqlalchemy

### First-time Setup
Run `Setup_Once.bat` once to create the venv and install packages.

### Daily Run
Just double-click `Run_All.bat`.

---
