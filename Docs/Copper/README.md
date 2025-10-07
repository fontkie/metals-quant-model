# 🧩 Copper Pricing — HookCore v0.4.0

**Type:** Mean-Reversion (Hook)  
**Version:** v0.4.0 – Final (Oct 2025)  
**Author:** Metals Quant Model  
**Purpose:** Short-term contrarian sleeve to complement slower trend and macro signals.

---

## 1️⃣ Concept

HookCore captures **short-term exhaustion** in copper prices — fading short bursts of momentum
when daily returns become statistically extreme.

- Long when recent returns are very negative (“oversold”)
- Short when recent returns are very positive (“overbought”)
- Flat otherwise

It is **pure price action** — no carry, RSI, or macro overlays.
Think of it as a *liquidity provision* sleeve, designed to earn small, repeatable alpha in choppy markets.

---

## 2️⃣ Model Specification

| Parameter | Value / Description |
|------------|---------------------|
| Base data | LME 3-month copper price (`copper_lme_3mo`) |
| Signal type | Discrete Hook: ±1 / 0 |
| Lookbacks | 3-day and 5-day (equal-weight blend) |
| Z-threshold | ±0.75 (bi-weekly) / ±0.85 (weekly) |
| Rebalance | **Bi-weekly** – Monday (using Fri signal) + Wednesday (using Tue signal) |
| Execution | **T+1** |
| Vol target | 10% annual (21d lookback, cap = 2.5×) |
| Transaction cost | 1.5 bps per unit turnover |
| IS period | 2008-01-01 → 2017-12-31 |
| OOS period | 2018-01-01 → present |

---

## 3️⃣ Behaviour Summary

| Metric | Weekly (z=0.85) | Bi-weekly (z=0.75) |
|--------|-----------------|--------------------|
| IS Sharpe | ~0.55 | ~0.60 |
| OOS Sharpe | ~0.40 | **~0.50** |
| Max Drawdown | ~-18% | **~-15%** |
| Turnover p.a. | ~5.5× | **~6.5×** |
| Participation | ~25% | **~30%** |
| Annual Vol (targeted) | 10% | 10% |
| Avg Trades / year | ~40 | ~60 |

- Bi-weekly version shows slightly higher OOS Sharpe and more consistent returns.
- Weekly version serves as a stability benchmark and sanity check.

---

## 4️⃣ Usage & Integration

HookCore is **not standalone** — it’s intended to be part of a multi-sleeve model.
It performs best when combined with:

- **TrendCore** – slower trend/tracking sleeve (e.g. MA-slope, 60–160d)
- **StocksCore** – supply-side LME stocks sentiment
- **PositioningCore** – fund/manager positioning contrarian sleeve

Each sleeve runs with the same 10% vol-target and 1.5bps cost assumptions to ensure fair comparison.

Portfolio combination should be based on:
- Equal risk weights or volatility targeting per sleeve
- Correlation cap (ρ < 0.5 between sleeves)
- Monthly sleeve rebalancing

---

## 5️⃣ Known Regime Bias

HookCore underperforms during:
- Persistent macro trends (e.g. 2020–2021 uptrends)
- Sharp volatility expansions (macro events)

It excels during:
- Range-bound markets
- Liquidity-driven short-term reversals
- Transitional phases between macro trends

---

## 6️⃣ Files

| File | Description |
|------|--------------|
| `daily_series.csv` | Raw signals, positions, and daily returns |
| `equity_curves.csv` | Cumulative returns (weekly & bi-weekly) |
| `summary_metrics.csv` | IS/OOS Sharpe, drawdown, turnover |
| `annual_returns.csv` | Annual returns table since inception |
| `README.md` | This document |

---

## 7️⃣ Next Steps

Future iterations:
- v0.4.1 — Add optional slow-trend veto (`|z₁₀₀| < 0.3`)  
- v0.5.x — Portfolio integration testing alongside trend, stocks, and positioning sleeves

---

**Status:** ✅ *Frozen (v0.4.0 — Bi-weekly, z=0.75)*  
**Confidence:** High (simple, interpretable, stable enough for integration)
