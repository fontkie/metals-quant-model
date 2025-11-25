# 🧩 Copper Stocks — StocksCore v0.1.1

**Type:** Supply-side / Inventory Sentiment  
**Version:** v0.1.1 — Final (Oct 2025)  
**Author:** Metals Quant Model  
**Purpose:** Capture physical-flow sentiment from LME copper inventory changes.

---

## 1️⃣ Concept

StocksCore measures **the rate of change in total LME warehouse stocks**.  
- Rapid draws → bullish (long)  
- Rapid builds → bearish (short)  
- Quiet periods → flat  

It’s designed as a **slow, directional supply-signal** that complements price-action sleeves such as HookCore.

---

## 2️⃣ Model Specification

| Parameter | Value / Description |
|------------|---------------------|
| Base data | LME total copper stocks (Excel input) |
| Signal type | z-score of 20 d Δstocks |
| Thresholds | ±1.0 (discrete ±1/0) |
| Execution | **Daily**, **T+1** |
| Vol target | 10 % annual (21 d lookback, cap 2.5×) |
| Transaction cost | 1.5 bps (one-way) |
| IS period | 2008-01-01 → 2017-12-31 |
| OOS period | 2018-01-01 → present |

---

## 3️⃣ Behaviour Summary (approx.)

| Metric | In-Sample | Out-of-Sample |
|--------|------------|---------------|
| Annual Return | ~6 % | ~6 % |
| Annual Vol | 10 % | 10 % |
| Sharpe | ~0.55 | **~0.59** |
| Max Drawdown | ~15 % | **~13 %** |
| Participation | ~60 % of days | — |

The sleeve produces steady medium-term alpha and low correlation (~0.25) to HookCore.

---

## 4️⃣ Files

| File | Description |
|------|--------------|
| `stockscore_config.yaml` | Model configuration / parameters |
| `CHANGELOG.md` | Version history |
| `daily_series.csv` | Raw signals, positions, and PnL |
| `equity_curves.csv` | Cumulative returns (All / IS / OOS) |
| `annual_returns.csv` | Calendar-year performance |
| `summary_metrics.csv` | Key statistics |

---

## 5️⃣ Integration

StocksCore pairs best with:
- **HookCore v0.4.0** (short-term price mean-reversion)  
- **TrendCore** (once developed) for macro momentum exposure  

In the equal-risk composite (v0.1.0), StocksCore provides most of the stability uplift (composite OOS Sharpe ≈ 0.60).

---

**Status:** ✅ *Frozen (v0.1.1 — Daily Exec T+1)*  
**Confidence:** High (simple, intuitive, repeatable)
