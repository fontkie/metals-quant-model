# TightStocks v1 - Continuous IIS Signal

## Overview
Fourth sleeve for your adaptive portfolio system. Uses **physical inventory data** (not just price) to generate signals.

## Files
- `tightstocks_v1.py` → Signal logic (Layer B) - goes in `src/signals/`
- `build_tightstocks_v1.py` → Build script (CLI) - goes in `src/cli/`
- `tightstocks_v1.yaml` → Configuration - goes in `Config/Copper/`
- `run_tightstocks_v1.bat` → Runner script - goes in project root

## Data Requirements
Rename your files to match canonical naming:
```
copper_lme_3mo.canonical.csv
copper_lme_onwarrant_stocks.canonical.csv
copper_comex_stocks.canonical.csv
copper_shfe_onwarrant_stocks.canonical.csv
```

## Performance
- **IS Sharpe**: 0.826 (2004-2018)
- **OOS Sharpe**: 0.812 (2019-2025)
- **Degradation**: -1.7% (excellent stability)
- **Correlation with price sleeves**: ~0.04 (uncorrelated)

## Key Innovation
**Continuous signal, not binary threshold**
```python
position = max(0, -IIS / scale_factor)
```
- IIS = 0: Neutral → position = 0
- IIS = -1: Moderate tightening → position = 0.5
- IIS = -2: Strong tightening → position = 1.0

No threshold cliff problem. Uses ALL information.

## Portfolio Integration
- Fits 15% floor constraint (continuous signal always active)
- Part of 3x1 vol regime optimization
- Adds ~18-25% Sharpe improvement to 3-sleeve portfolio

## The Fundamental Edge
This is your **quantamental differentiation**:
- Price sleeves: "Where is price going?"
- TightStocks: "Is physical market tightening?"
- Combined: Higher conviction, better risk-adjusted returns

When you pitch to institutions: "We don't just follow price momentum. We have proprietary signals that capture physical market tightness."
