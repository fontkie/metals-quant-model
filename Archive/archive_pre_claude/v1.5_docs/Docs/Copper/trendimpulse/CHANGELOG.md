
---

## 🧾 `Docs/Copper/trendimpulse/CHANGELOG.md`

```markdown
# CHANGELOG — TrendImpulse Sleeve (Copper)

### v1.0 — 2025-10-17
- Added full build script `src/build_trendimpulse.py`  
  - Supports cadences: `monwed`, `tuethu`, `tuefri`, `daily`  
  - Optional `--cooldown` parameter after exit  
  - Automatic timestamped output folders + `latest/` sync  
  - Logs `effective_params` and `price_sha1` for reproducibility
- Tuned copper implementation to **Tue/Fri** cadence (best OOS performance)
- **Metrics:**  
  - IS Sharpe = 0.31, Max DD = −20.4 %  
  - OOS Sharpe = 0.51, Max DD = −11.6 %  
  - Avg Hold = 3 bars, Turnover ≈ 0.12, Hit ≈ 49 %  
- Added minimal CLI defaults → only file path + symbol required to run

# TrendCore — Changelog

## v1.1 — 2025-10-24
### Changed
- **Execution policy updated:** Now executes on the close of T with PnL beginning from T+1, aligning with live-safe execution logic across sleeves.
- **YAML schema:** Added `pnl_start: Tplus1` field for clarity and reproducibility.
- **Docs cleanup:** Simplified descriptions and added explicit cadence (`monwed`), vol parameters, and path placeholders.
- **Standardised cost convention:** Explicit 1.5 bps per turnover only on trade days.
- **Readability:** Improved `notes` section for replication by external quants.

### Notes
- v1.0 used implicit T-day execution and was ambiguous on PnL accrual timing.
- No logic changes to signal generation (`z >= 0.85 / z <= -0.85`); results unaffected except for improved timestamp alignment.
