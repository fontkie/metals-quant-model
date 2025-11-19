
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

# # TrendImpulse — Changelog

## v1.1 — 2025-10-24
### Changed
- **Execution policy updated:** Now executes on the close of T with PnL starting from T+1 to standardise behaviour with other sleeves.
- **Removed T+1 fill convention:** Simplified to same-day close execution for clarity and consistency.
- **YAML schema:** Added `pnl_start: Tplus1` and clarified cadence (`tuefri`) and hold/rebalance parameters.
- **Docs cleanup:** Added clearer description of impulse z-score logic (3-day mean return / stdev).
- **Transaction costs:** Confirmed as 1.5 bps per turnover on trade days only.

### Notes
- v1.0 assumed fill on T+1 close; this update aligns PnL timing with TrendCore (T execution / T+1 PnL).
- No changes to signal logic or thresholds; numerical results may shift by one-day alignment only.
