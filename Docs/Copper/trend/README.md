# TrendCore — Copper Pricing Momentum (Sleeve 3)

**Goal:** Add a robust, orthogonal **trend sleeve** to diversify **Hook** (mean-reversion) and **Stocks** (fundamental).

---

## 🔧 Specification (MVP)

| Parameter | Value |
|------------|--------|
| **Signals** | Majority vote across 20/60/120-day log-momentum (`MOM_N = sign(log return N)`) |
| **Execution** | Rebalance **Mon/Wed**, **T+1** application |
| **Risk Target** | 10% annual volatility (21-day rolling window) |
| **Leverage Cap** | 3× |
| **Transaction Cost** | 1.5 bps × daily turnover |
| **Output** | `outputs/copper/trend/daily_series.csv` |

**Note:** Early experiments also tested SMA families (`SMA_N = sign(price/SMA_N – 1)`), but production TrendCore uses pure MOM logic.

---

## 🧮 Columns (outputs)

`date, price, ret_log, mom_20, mom_60, mom_120, mom_sig_*, raw_signal, roll_vol21, leverage, desired_pos, rebalance_flag, position, turnover, cost, pnl_gross, pnl, cum_pnl`

---

## 📊 Diagnostics (non-production)

For research only, we sometimes compute **5/10/50/100/200-day** MAs and N-day momentum for cross-checks.  
If these outperform after costs at Mon/Wed cadence, they may inform future blends.

---

## 🚀 TrendCore v0.1 — Production Spec

**Spec:** 20/60/120-day log-momentum (MOM), majority vote, Mon/Wed execution, T+1, 10% vol (21d), 3× cap, 1.5 bps cost.

### Rationale
Adds a clean **directional/convex** sleeve to diversify Hook (mean-reversion) and Stocks (fundamental).  
Not expected to generate steady standalone alpha; pays off during persistent price trends.

### How to build
```bash
python src/build_trend.py \
  --file Data/copper/pricing/pricing_values.xlsx \
  --sheet Raw \
  --price_col copper_lme_3mo \
  --date_col date \
  --mode MOM \
  --cadence MON_WED \
  --quiet_q 0 \
  --out outputs/copper/trend/daily_series.csv
