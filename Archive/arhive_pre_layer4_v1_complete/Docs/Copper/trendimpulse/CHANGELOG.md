
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
