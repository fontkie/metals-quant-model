# Changelog

## 2025-10-01
- Stabilised project pipeline:
  - `setup_once.bat` creates venv and installs requirements.
  - `run_all.bat` runs the full pipeline (load → fix_views → signals → checks → backtest).
  - Added robust `load_data.py` (auto-detects Raw sheet, flexible date col).
  - Added `fix_views.py` to produce:
    - `prices_long(date, symbol, price)` for checks
    - `prices_std(date, px_*)` wide table for backtest
  - Updated `test_db.py` to auto-detect `dt` vs `date` in signals.
  - Backtest runs successfully and saves outputs.
- Confirmed working run with 27,875 price rows and 51,412 signal rows.
- All steps green.

## 2025-09-30
- Initial repo setup with Copper pricing data, SQLite database, and early scripts.
