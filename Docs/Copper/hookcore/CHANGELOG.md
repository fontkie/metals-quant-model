## 2025-10-07 — HookCore v0.4.0 (Frozen)

# 📈 Copper Pricing — CHANGELOG

Tracks all updates to copper pricing sleeves (HookCore, TrendCore, and future variants).  
For global project changes, see `docs/CHANGELOG.md`.

---

## 2025-10-07 — HookCore v0.4.0 (Frozen)

**Type:** Mean-reversion (Hook)  
**Status:** ✅ *Frozen*  
**Purpose:** Establish clean, standalone short-term contrarian sleeve.

**Summary:**
- Introduced **HookCore v0.4.0** using discrete ±1/0 hook signals.
- Based on **3-day** and **5-day** return z-scores (equal-weighted).
- Optimal config: **z = 0.75**, **bi-weekly rebalance** (Mon + Wed, T+1).
- Added documentation:
  - `hookcore_config.yaml` (parameter spec)
  - `summary_metrics.csv` (IS/OOS results)
  - `README.md` (overview and behaviour)
- Outputs stored under `outputs/copper/hookcore/`.

**Performance snapshot:**
| Period | Sharpe | Return p.a. | Max DD | Turnover p.a. | Participation |
|:-------|-------:|------------:|-------:|---------------:|---------------:|
| IS (2008-2017) | 0.60 | 10.5% | -15% | 6.5× | 30% |
| OOS (2018-2025) | 0.50 | 8.0% | -15% | 6.5× | 30% |

**Next planned version:**  
v0.4.1 – optional slow-trend veto (`|z₁₀₀| < 0.3`).

---

## Placeholder — TrendCore v0.x.x

*To be added once TrendCore sleeve (slow trend/tracking model) is developed.*

Expected components:
- Moving-average slope / return-t-stat based trend signal.
- Weekly or bi-weekly rebalance, 10% vol target.
- Complementary to HookCore (low correlation, longer horizon).

---

## Placeholder — Carry / Spread extensions

*Future exploratory versions may include:*
- Cash–3M carry bias integration (conditional mean-reversion)
- Volatility-adjusted hooks or hybrid “trend-hook” blending

---

_Last updated: 2025-10-07_

