## 🧱 FILE 2 — **Execution_Policy_Guide.md (v2.2, Final)**

```markdown
# Execution_Policy_Guide.md (v2.2)

**Purpose**  
Unified, live-safe execution rules. Applies to every sleeve built under Metals Model 3.0.

---

## 1) Timing & PnL
**Signal timestamp:** close of day **T**  
**Execution:** close of **T** (end-of-day rebalance)  
**Accrual:** PnL starts **T+1** using `pos_for_ret_t = pos.shift(1)`

Return definition:
```python
ret_t = price_t / price_{t-1} - 1
All builds must use canonical CSV inputs with lowercase columns:

bash
Copy code
date,price
(case-sensitive)

2) Costs
Apply one-way transaction costs only on turnover:

python
Copy code
trade_t = pos_t - pos_{t-1}
cost_t = -abs(trade_t) * (one_way_bps / 10_000)
Costs apply only on changes in position (Δpos).

Expressed as one-way bps (e.g. 1.5 bps per side).

3) Sizing & Vol Target
yaml
Copy code
sizing:
  ann_target: 0.10
  vol_lookback_days_default: 21
  leverage_cap_default: 2.5
Realised vol estimate:

python
Copy code
realized_vol = stdev(ret, lookback) * sqrt(252)
Target leverage:

python
Copy code
target_leverage = (ann_target / realized_vol).clip(upper=leverage_cap)
pos = pos_raw * target_leverage
4) Calendar
Default (Mon–Fri) with explicit origins:

yaml
Copy code
calendar:
  exec_weekdays: [0,1,2,3,4]
  origin_for_exec: {"0":"-1B","1":"-1B","2":"-1B","3":"-1B","4":"-1B"}
  fill_default: close_T
origin_for_exec maps weekday to data-origin offset (e.g. Monday uses Friday data).

Sleeves may override exec_weekdays (e.g. [0,2,4] for Mon/Wed/Fri execution).

5) Required YAML Blocks (no exceptions)
yaml
Copy code
policy:
  calendar: { exec_weekdays: [...], origin_for_exec: {...}, fill_default: close_T }
  sizing:   { ann_target: 0.10, vol_lookback_days_default: 21, leverage_cap_default: 2.5 }
  costs:    { one_way_bps_default: 1.5 }
  pnl:      { t_plus_one_pnl: true, formula: pos_lag_times_simple_return }
These blocks are mandatory for any valid sleeve configuration.

6) Metrics (standardised output schema)
Metric	Definition
annual_return	Compounded net return = (∏(1 + pnl_net))**(252/N) - 1
annual_vol	Stdev of net daily return × √252
sharpe	Mean(pnl_net)/Stdev(pnl_net) × √252 (rf = 0)
max_drawdown	Max peak-to-trough drawdown of cumulative net equity
obs	Row count in daily_series.csv
cost_bps	Echo of YAML one_way_bps_default

7) Validation Checklist
✅ Uses canonical CSV (date,price), not Excel
✅ T→T+1 accrual enforced
✅ Costs on Δpos only
✅ Vol target and leverage cap enforced
✅ Outputs written under outputs/<Asset>/<Sleeve>/
✅ No look-ahead (origins respected)
✅ YAML includes all required policy blocks
✅ Standard output schema (daily_series.csv, summary_metrics.json)

yaml
Copy code

**Alignment check:**  
- All YAML field names and metric names match the other three files precisely.  
- Case-sensitive input schema consistently reinforced.

---