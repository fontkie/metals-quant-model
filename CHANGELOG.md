here’s a starter CHANGELOG.md you can drop into your project root (C:\Code\Metals\CHANGELOG.md).
It follows Keep a Changelog
 style and semantic versioning.

# Changelog
All notable changes to this project will be documented in this file.  
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)  
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [0.1.0] – 2025-09-30
### Added
- Finalised **Excel → SQLite loader (`load_data.py`)**
  - Supports loading from any sheet (defaults to first).
  - Normalises column names, trims spaces.
  - Creates canonical `date` column, removes duplicates like `Date/DATE`.
  - Dedupes by `date` (keep last entry).
  - Writes clean `prices` table into `<Metal>\quant.db`.
- Established **folder structure**:


C:\Code\Metals
├─ src\ (scripts: load_data.py, build_signals.py, backtest_prices.py, test_db.py)
├─ Copper\ (quant.db, pricing_values.xlsx)
├─ outputs\Copper\ (signals, backtest outputs)

- Defined **workflow** (4-step process):
1. Load Excel → DB
2. Build signals (`prices_std` view + `signals` table)
3. Sanity check
4. Backtest

### Next
- Test `build_signals.py` end-to-end.
- Confirm `test_db.py` validates rows & ranges.
- Run `backtest_prices.py` to generate equity curves and performance metrics.

---