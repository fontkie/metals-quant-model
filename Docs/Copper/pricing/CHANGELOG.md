# Copper — Pricing Sleeve: CHANGELOG

All dates in Europe/London (DD Mon YYYY).

## [0.3.0] — 06 Oct 2025
### Added
- **Finalist (candidate) parameters frozen** for day-to-day runs:
  - Trend: EMA(30, 120) → z-score(126) → tanh
  - Hook: τ=3 consecutive closes < EMA10, **hold 3 days**, re-entry when > EMA10, intensity scaled by (price−EMA10)/ATR_proxy, tanh
  - RSI: length=7 mapped to [−1, +1] by (RSI−50)/20 clipped
  - Base weights: 0.50·trend + 0.25·hook + 0.25·RSI
  - **Strength gates**: |trend| ≥ 0.20 AND |base| ≥ 0.35 (pre-curve)
  - Curve modulator: **cash–3m z-score**, multiplier (1 + 0.25·curve_z) clipped [0.5, 1.5]
  - Vol targeting: 10% annual, lookback=21d, cap=3×
  - Execution: T+1 close; Costs: 1.5 bps per unit daily turnover
- Dropped deeper curve modulators (3m–12m, 12m–24m) from combo (kept for research notes only).

### Notes
- OOS improved with slower trend + hook hold + short vol lookback + gates.
- Cash–3m modulation sometimes helps OOS; keep as a **toggle**.

## [0.2.0] — 02 Oct 2025
### Added
- First **combined** signal and IS/OOS evaluation.
- Initial parameter grid:
  - Trend EMA pairs: (20/100), (30/120), (50/200)
  - Hook τ ∈ {3,5}, hold ∈ {1,3,5}
  - RSI ∈ {7,14,21}
  - Vol LB ∈ {21,63}
  - Curve ∈ {none, cash3m, 3m12m, 12m24m}
  - Strength gates tested: trend_gate ∈ {0, 0.20}, abs_thresh ∈ {0.20, 0.35, 0.50}
- Costs model introduced (1.5 bps), positions T+1, vol target 10%.

## [0.1.0] — 02 Oct 2025
### Added
- Data ingestion from `pricing_values.xlsx` (sheet 0; Col A = Date).
- Built **continuous sleeves**: trend, hook, RSI; plus curve z-scores.
- Saved consolidated daily output with signals, position, PnL, equity.

---

## Roadmap
- [ ] Add optional **EMA(50/200)** trend sleeve and **RSI(21)** as extra sleeves for portfolio blending.
- [ ] Plot pack: equity, drawdown, rolling Sharpe/vol/turnover (IS/OOS).
- [ ] Quarterly stability check; update only on material degradation.
