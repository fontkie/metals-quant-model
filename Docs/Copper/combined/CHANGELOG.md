# Copper — Composite (HookCore + StocksCore) — CHANGELOG

## v0.1.0 — 2025-10-07
- **Initial composite** of two frozen sleeves:
  - **HookCore v0.4.0** (price hook, bi-weekly, z-thr 0.75, 10% VT, T+1)
  - **StocksCore v0.1.1** (LME Δstocks z20, thr 1.0, daily, 10% VT, T+1)
- **Construction:** equal-risk combine (0.5 * Hook PnL + 0.5 * Stocks PnL), then **single scalar** to target **10% annual vol** (scalar estimated on OOS window starting 2018-01-01).
- **Costs:** both sleeves include **1.5 bps** per one-way turnover; leverage cap **2.5×** inside sleeves.
- **Accounting:** both sleeves **T+1**; composite inherits T+1 from components.
- **Headline (user run):** Hook OOS Sharpe ≈ **0.35**; Stocks OOS Sharpe ≈ **0.59**; **Composite OOS Sharpe ≈ 0.60** (scaled to 10% vol).
- **Files (ad-hoc, not versioned code):**
  - `outputs/copper/composite_ad_hoc/daily_combo.csv`
  - `outputs/copper/composite_ad_hoc/summary_metrics.csv`

### Notes
- This composite is a **bookkeeping freeze**: weights and methodology are fixed; implementation was run ad-hoc. We can later add a small reproducible script/target once we finish the sleeves set (Trend, Positioning, LevelStocks).

## 2025-10-10 — CopperComposite v0.2.1 (Frozen: bi-weekly + pnl_net, T+1 VT)
- **Hook stream:** `return_biweekly`
- **Stocks return:** `pnl_net`
- **Combine:** equal weight (0.5 / 0.5) on returns
- **Scaling (default):** rolling **T+1 vol targeting** (10% annual, 21d lookback, cap 2.5×)
- **OOS window:** 2018-01-01 → present
- **Outputs:** `outputs/copper/composite_ad_hoc/daily_series.csv`, `daily_combo.csv`, `summary_metrics.csv`
- **Note:** Weekly stream retained as an alternate for diagnostics; current freeze uses bi-weekly per latest OOS assessment.

