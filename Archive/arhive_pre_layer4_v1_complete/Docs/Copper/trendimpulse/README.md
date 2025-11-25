# TrendImpulse Sleeve (Copper)

**Version:** v1.0  
**Last Updated:** 2025-10-17  
**Author:** K. Fontaine + Quant Assistant  

---

### Overview
TrendImpulse is a short-horizon continuation sleeve that captures 2-4 day momentum bursts in copper.  
It runs twice weekly (Tuesday / Friday) and holds for a fixed 3-bar time stop.  
The model targets 10 % annualised volatility with a 2.5× leverage cap and applies 1.5 bps execution cost.

The sleeve complements **TrendCore** by reacting faster to new directional bursts while maintaining tight turnover discipline.

---

### Methodology
1. **Inputs:**  
   - Price: `copper_lme_3mo` (LME 3-month official)  
   - Data source: `Data/copper/pricing/pricing_values.xlsx`, sheet `Raw`  
2. **Feature construction:**  
   - 5-, 20-, 60-day EMAs  
   - 60-day rolling stdev for z-score normalisation  
   - Short momentum = (EMA5 − EMA20) / 20-day stdev  
3. **Signal logic:**  
   - Long → `z_dev > +1.0` and `mom_short > 0`  
   - Short → `z_dev < −1.0` and `mom_short < 0`  
   - Evaluated **Tuesdays / Fridays** only.  
4. **Position rules:**  
   - Time-stop exit after 3 bars  
   - Vol-target 10 % annualised (28-day look-back)  
   - Rebalance if leverage changes ≥ 10 %  
   - Max leverage = 2.5×  
   - Transaction cost = 1.5 bps per Δ-position  
5. **Outputs:**  
   - `daily_series.csv`  
   - `equity_curves.csv`  
   - `summary_metrics.json` / `run_lock.json`  

---

### Results (Copper, 2010–2025)

| Segment | Sharpe | Max DD | Turnover | Trades | Avg Hold (bars) | % Days in Pos | Hit Rate |
|:---------|:------:|:------:|:---------:|:------:|:----------------:|:--------------:|:---------:|
| **IS (< 2018)** | 0.31 | −20.4 % | 0.118 | 527 | 3.0 | 33.7 % | 50.9 % |
| **OOS (≥ 2018)** | **0.51** | **−11.6 %** | 0.117 | 195 | 3.0 | 28.9 % | 48.7 % |

**Annualised return:** ≈ 4 – 5 % @ 10 % vol  
**Cadence:** Tue/Fri  
**Vol target:** 10 %  
**Costs:** 1.5 bps per trade leg  

---

### How to Run

Short version – from repo root:
```bat
.\.venv\Scripts\python.exe src\build_trendimpulse.py ^
  --excel "C:\Code\Metals\Data\copper\pricing\pricing_values.xlsx" ^
  --sheet Raw ^
  --date-col Date ^
  --price-col copper_lme_3mo ^
  --symbol COPPER
