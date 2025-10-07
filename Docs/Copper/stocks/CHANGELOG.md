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
