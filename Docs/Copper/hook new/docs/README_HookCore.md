
# HookCore (RSI3 Cross + Volatility Gate)

**Version:** v1.1  
**Last Updated:** 2025-10-17  
**Author:** K. Fontaine + Quant Assistant

---

## Overview
HookCore is a short-horizon **mean-reversion** sleeve for copper. It fades small price extremes **only when the market is quiet**, using a simple RSI(3) cross and a realised-volatility filter. Signals are checked on **Tuesdays and Fridays**, executed **same day (T)** by default, and held for a fixed **2 bars**. The sleeve targets **10% annualised volatility** with a **2.5× leverage cap** and **1.5 bps** per |Δposition| transaction cost.

This sleeve is designed to complement TrendCore/TrendImpulse by earning in **range-bound** regimes, where trend sleeves often bleed.

---

## Methodology (v1.1)
1. **Inputs**
   - Price: `copper_lme_3mo` (LME 3-month official)
   - Data: `Data/copper/pricing/pricing_values.xlsx`, sheet `Raw`

2. **Signal**
   - Compute RSI(3) on close.
   - **Long** when RSI crosses **up through 35** (recovery from oversold).
   - **Short** when RSI crosses **down through 65** (rollover from overbought).
   - **Volatility gate:** trade only if **10-day realised vol / 60-day realised vol < 1.0**.

3. **Execution & holding**
   - **Cadence:** evaluate **Tuesdays / Fridays**.
   - **Execution:** **on T** (same-day) or `--exec next` (T+1) via CLI.
   - **Hold:** fixed **2 bars** (time stop).

4. **Risk & costs**
   - **Vol target:** 10% (28-day look-back).
   - **Leverage cap:** 2.5×.
   - **Transaction cost:** **1.5 bps per |Δposition|**.

5. **Outputs**
   - `daily_series.csv`, `equity_curves.csv`, `summary_metrics.json`

---

## Results (2010–2025, Copper)

The v1.1 (35/65, vol-gate 1.0) configuration delivered:
- **OOS Sharpe (≥ 2018):** typically **~0.8–1.2** after costs depending on execution (T vs next)
- **Max DD:** ~4–6 %
- **Trades:** ~10–20 per year (biweekly cadence; varies by regime)
- **% Days in position:** ~10–20%

*(Exact figures depend on execution choice and refresh date; see `summary_metrics.json` from the latest run.)*

---

## How to run

From repo root:

```bash
python src/build_signals.py \
  --excel "Data/copper/pricing/pricing_values.xlsx" \
  --sheet Raw \
  --date-col Date \
  --price-col copper_lme_3mo \
  --symbol COPPER \
  --low 35 --high 65 \
  --volratio 1.0 \
  --cadence biweekly \
  --exec T \
  --hold 2 \
  --vol-target 0.10 \
  --vol-lb 28 \
  --lev-cap 2.5 \
  --cost-bps 1.5
```

Outputs will be written under:

```
outputs/hookcore/COPPER/RSI3_35_65_vr1.0_biweekly_T_hold2/
```

---

## Change log
- **v1.1 (2025-10-17):** Introduced **RSI(3) 35/65** thresholds with **vol gate < 1.0**. Added `--exec` switch (T vs next). Standardised outputs and JSON summary.  
- **v1.0:** Prototype RSI(3) cross 30/70 with strict filters and exploratory settings.
