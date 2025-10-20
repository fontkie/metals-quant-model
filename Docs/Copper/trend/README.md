# TrendCore-Cu-v1-Tclose (Copper pricing sleeve)

**Type:** Directional trend using 3/5-day return z-scores (equal weight).  
**Exec cadence:** Monday & Wednesday (business-day aware).  
**Fill timing:** **Trade on T (same-day close)** using orders into the close (e.g., MOC/VWAP-to-close).  
**Signal origins:** Friday → Monday trade; Tuesday → Wednesday trade.  
**Sizing:** Vol-target to **10%** annualised using **21-day** realised **simple** returns, **info up to T** (inclusive).  
**Cap:** **2.5×** leverage at sizing, held between rebalances.  
**Costs:** **1.5 bps** per \|Δposition\| charged **only on trade days** (Mon/Wed).  
**PnL:** `position_{t-1} × simple_return_t` (ΔP/P).  
**z-window:** 252 trading days for the 3-day and 5-day log-return z-scores (equal weight).  
**Threshold:** 0.85 (z ≥ +0.85 → long; z ≤ −0.85 → short; else flat).

---

## Files & outputs
- Builder: `src/build_trend.py`  
- Config (static): `Docs/Copper/trend/config.yaml`  
- Policy reference: `Docs/standards/real_world_rules.md` and `Config/schema.yaml`  
- Outputs (single run):  

outputs/copper/pricing/trendcore_single_Tclose/
├─ signals.csv # signal_raw, signal_exec, position_vt
├─ pnl_daily.csv # ret, pos, pos_lag, turnover, cost, pnl_gross, pnl_net
└─ summary.json # IS/OOS Sharpe (252)


---

## Invariants (quick self-check)
1. **Turnover > 0 only on Mon/Wed.**  
2. **Position changes only on Mon/Wed;** held constant otherwise.  
3. **First PnL day is Tue/Thu** (day after the trade).  
4. **Vol series used for sizing includes T** (T-close convention).  
5. **No positions** before z-window (252) and vol lookback (21) warm-ups complete.

Use:
```bash
python tools/validate_realworld.py \
--pnl-csv outputs/copper/pricing/trendcore_single_Tclose/pnl_daily.csv \
--signals-csv outputs/copper/pricing/trendcore_single_Tclose/signals.csv \
--exec-weekdays "0,2"

Notes & rationale

T-close vs T+1: Trading on T with sizing that sees T’s data is realistic for close-algos and lifted OOS robustness in testing.

Cap at 2.5×: Safer tail profile; moving to 3× mainly scales risk without improving Sharpe.

Why trend (not hook): Under real-world timing/costs, the mean-revert mapping was loss-making; the trend mapping is credibly positive OOS.

WFV plan: When ready, run WFV with narrow grids around (threshold 0.75–0.95, z-window 200–300, vol LB 21–35).