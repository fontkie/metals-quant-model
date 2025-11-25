# Copper — StocksCore CHANGELOG

## v0.1.1 — 2025-10-07
- **What changed:** Parameter tweak and execution fix.
  - Signal now uses **lb(20,20)** (equiv. to 20-day window) with **threshold = 1.0**.
  - Confirmed **T+1** accounting (positions trade the day *after* the signal is computed).
- **Construction:** z(Δ total LME stocks) with daily execution; discrete signal:
  - z ≤ −1.0 → **+1** (long), z ≥ +1.0 → **−1** (short), else 0.
- **Risk:** 10% vol target (21d), leverage cap 2.5×, 1.5 bps per one-way turnover.
- **Data:** Stocks from Excel (`pricing_stocks_values.xlsx`, sheet **Sheet1**). Price from DB symbol **`copper_lme_3mo`**.
- **Outputs:** daily series, equity curves, summary metrics, annual returns (CSV).
- **Why:** Grid search (IS/OOS) showed stronger and more stable OOS Sharpe at lb20/20 & thr=1.0 vs v0.1.0 defaults.

## v0.1.0 — 2025-10-07
- Initial release (rate-of-change sleeve): z of Δ total stocks with {5,20} components @ thr=0.75, daily exec, T+1.

# Copper — StocksCore — CHANGELOG

## v0.1.1 — 2025-10-20
- **Stable version freeze** for Copper StocksCore (inventory-driven sleeve).
- Rebuilt using Excel pricing input (`pricing_values.xlsx`) instead of SQLite.
- Code: `src/build_stockscore_v011.py`  
  Config: `Docs/Copper/stocks/stockscore_config.yaml`
- Generated outputs in `outputs/copper/stocks/stockscore_v0_1_1/`:
  - `daily_series.csv`
  - `equity_curves.csv`
  - `annual_returns.csv`
  - `summary_metrics.csv`
- Parameters:
  - Signal = z20(Δ LME total stocks), threshold ±1.0 → {+1, 0, –1}
  - Execution = daily, **T+1**
  - Vol target = 10 % annual (21 d lookback, cap 2.5×)
  - Cost = 1.5 bps per one-way turnover
- In-sample (2008-2017) and out-of-sample (2018-present) periods as per global baseline.
- HookCore + StocksCore composite (v0.1.0) delivers OOS Sharpe ≈ 0.60 (see `Docs/Copper/combined`).

### Notes
- Signal uses **only LME total stocks** data — no price information in the signal itself.  
- Price is used solely for volatility targeting and PnL conversion.  
- Next revision (v0.2.x) may:
  - Add multi-region stocks (LME + SHFE + Bonded)
  - Explore level-based sentiment or rate-of-change blending
  - Add optional smoothing and quiet-market filters
