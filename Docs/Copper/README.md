docs/copper/README.md
# 🧱 Copper Quant Strategy – Master README

**Objective:**  
Develop a modular framework of complementary copper trading sleeves — each capturing different drivers of market behaviour — to be combined into a single, risk-balanced copper portfolio.

---

## 📂 Folder structure


docs/
copper/
README.md ← you’re here (master for copper)
pricing/
params.yaml
CHANGELOG.md
stocks/
params.yaml
CHANGELOG.md
positioning/
params.yaml
CHANGELOG.md


### Supporting folders


data/raw/Copper/ # input data (Excel or CSV)
outputs/Copper/ # generated sleeves, backtests, portfolios
src/ # shared Python scripts
config/ # global settings (vol target, costs, IS/OOS)


---

## ⚙️ Active sleeves

| Sleeve | Description | Key Inputs | Status | Params | Changelog |
|:--------|:-------------|:------------|:--------|:----------|:-------------|
| **Pricing** | Trend + Hook + RSI on `copper_lme_3mo`, optional cash–3m modulation | `pricing_values.xlsx` | ✅ Frozen v0.3.0 | [params.yaml](pricing/params.yaml) | [CHANGELOG.md](pricing/CHANGELOG.md) |
| **Stocks** | LME on-warrant, cancelled, and total stocks (NLECA, NLFCA, NLSCA) as supply-side sentiment indicators | `copper_stocks.xlsx` | 🧪 Under calibration | [params.yaml](stocks/params.yaml) | [CHANGELOG.md](stocks/CHANGELOG.md) |
| **Positioning** | Managed-money and fund positioning (CFTC, SHFE) as crowding / mean-reversion signals | `copper_positioning.xlsx` | 🧪 Early-stage build | [params.yaml](positioning/params.yaml) | [CHANGELOG.md](positioning/CHANGELOG.md) |

---

## 🪜 Overall workflow

Each sleeve goes through the same 3-stage pipeline using shared code in `src/`:

| Step | Script | Purpose |
|:--|:--|:--|
| **1️⃣ Build sleeves** | `build_sleeves.py` | Generate daily signals (trend, hook, RSI, etc.), vol-targeted positions, and backtest results |
| **2️⃣ Optimise parameters** | `grid_optimize_combo.py` | Run coarse grid to rank Top 10 IS/OOS parameter combinations |
| **3️⃣ Combine & weight** | `optimise_weights.py` | Blend sleeves (non-negative, sum=1) based on IS Sharpe, check OOS stability |

Each sleeve outputs its own CSV(s) in `outputs/Copper/<sleeve_name>/`.

Example:


outputs/Copper/pricing/
copper_sleeves_combined.csv
copper_grid_top10.csv
copper_weighted_portfolio.csv


---

## 🧩 Current configuration summary (Oct 2025)

| Sleeve | Core Logic | Key Params | Vol Target | Cost Model | IS/OOS Split |
|:--|:--|:--|:--:|:--:|:--:|
| **Pricing** | EMA(30/120) trend + hook τ=3 hold=3 + RSI(7); cash–3m modulator | trend_gate=0.20, abs_thresh=0.35 | 10% | 1.5 bps / turnover | IS: 2008–2017 / OOS: 2018– |
| **Stocks** | Δ(LME on-warrant / total) z-score → sentiment reversal | rolling_z(63 d) | 10% | 1.5 bps | same |
| **Positioning** | Managed money long–short diff → contrarian mean reversion | 26 w MA deviation | 10% | 1.5 bps | same |

---

## 📈 Current status

| Metric | Pricing (v0.3.0) | Stocks | Positioning |
|:--|:--:|:--:|:--:|
| **Sharpe IS** | 0.95 | 0.61 | 0.58 |
| **Sharpe OOS** | 0.46 | 0.32 | 0.41 |
| **CAGR (OOS)** | 4.2% | 3.0% | 2.7% |
| **Ann Vol** | 9.1% | 9.7% | 9.8% |
| **Max DD** | −18% | −16% | −17% |

> *Notes:*  
> – Pricing sleeve frozen as core component.  
> – Stocks and Positioning in calibration; early signals promising but not frozen.  
> – Next milestone: evaluate correlations and static weighting across all three.

---

## 🧠 Portfolio logic (future phase)
- Each sleeve vol-targeted to 10% with a 21-day estimator, 3× leverage cap.  
- Static weights (`w_pricing`, `w_stocks`, `w_positioning`) optimised on IS Sharpe with non-neg constraints, sum = 1.  
- OOS performance checked for degradation.  
- Combined book saved to `outputs/Copper/copper_portfolio_static.csv`.

---

## 🔧 Shared configuration (from `config/global.yaml`)
```yaml
execution:
  t_plus: 1
risk:
  vol_target_ann: 0.10
  vol_lookback_days: 21
  leverage_cap: 3.0
costs:
  turnover_bps: 1.5
split:
  is_start: 2008-01-01
  is_end: 2017-12-31
  oos_start: 2018-01-01

🚀 Roadmap

 Freeze Pricing sleeve v0.3.0

 Finalise Stocks sleeve (signal validation + IS/OOS test)

 Finalise Positioning sleeve (contrarian filter calibration)

 Optimise cross-sleeve weights for static Copper portfolio

 Extend structure to other metals (Zinc, Nickel, Aluminium)


✅ **Stop copying at the line of stars.**  
Everything after (Governance, References, etc.) is optional for later once your copper framework is mature.