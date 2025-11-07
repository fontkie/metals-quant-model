# Metals Quant Model - Change Log

---

## [v3.0] HookCore Optimization - 2025-10-29

### Added
- **HookCore v3.0**: Regime-aware mean-reversion strategy
  - Longs-only mode (shorts eliminated - no edge)
  - Tier 1 safety filters (IV shutdown at 30%, contango penalty at -2%)
  - Relaxed autocorr filter (-0.05 vs -0.1 in v2)
  - Extended hold period (5 days vs 3 days)
  - Regime data integration (stocks, IV, curve)

### Performance Improvements
- Sharpe ratio: 0.34 → 0.55 (+62%)
- Turnover: 42x → 11-21x (-50% to -75%)
- Disaster year mitigation:
  - 2007: -21% → +2% ✅
  - 2016: -18% → -6% ✅
  - 2024: -26% → -2% ✅

### Files Added
- `src/signals/hookcore_v3.py`
- `src/cli/build_hookcore_v3.py`
- `Config/Copper/hookcore_v3.yaml`
- `run_hookcore_v3.bat`

### Documentation Added
- `docs/HOOKCORE_V3_GUIDE.md` - Implementation guide
- `docs/REGIME_ANALYSIS.md` - Regime structure findings
- `docs/TIER1_SAFETY_SPEC.md` - Safety filter specification

### Analysis
- Diagnosed v1.0/v2.0 performance issues
- Validated regime thresholds against 25 years of data
- Optimized parameters through systematic testing
- Fixed asymmetric alpha problem (longs +9.6bps vs shorts +0.5bps)

---

## [v2.0] HookCore Base Implementation - 2025-10-XX

### Added
- HookCore v2.0 mean-reversion strategy
- Bollinger band logic (5d/1.5σ)
- Regime filters (trend, vol, autocorr)
- 3-day hold period
- Long/short signals

### Performance
- Sharpe ratio: 0.34
- Annual return: 3.67%
- Annual vol: 10.72%
- Max drawdown: -26.3%
- Turnover: 42x

### Known Issues
- Shorts have no edge (+0.5 bps vs longs +9.6 bps)
- Excessive turnover (42x)
- Disaster years: 2000, 2007, 2016, 2024
- Autocorr filter too restrictive (-0.1 threshold)

---

## [v1.0] Initial Infrastructure - 2025-10-XX

### Added
- Two-layer architecture (Layer A: execution, Layer B: signals)
- Immutable execution contract (`src/core/contract.py`)
- Vol targeting (10% annual target)
- T→T+1 PnL accrual
- Cost model (1.5 bps one-way)
- Validation framework (`tools/validate_outputs.py`)

### Sleeves Implemented
- CrashAndRecover (Sharpe -0.40)
- HookCore v1.0 (baseline)
- MomentumTail (Sharpe -0.02)

### Documentation
- `INFRASTRUCTURE_STANDARDS.md`
- `QUICK_REFERENCE.md`
- `README.md`

---

## Version Naming Convention

- **Major versions** (v1.0, v2.0, v3.0): Significant strategy changes
- **Minor versions** (v3.1, v3.2): Parameter tuning, bug fixes
- **Dated snapshots** (v20251029): Production snapshots for auditing

---

## Upcoming

### Short-term (Next 2 weeks)
- [ ] Paper trade HookCore v3.0 vs v2.0
- [ ] Build TrendCore sleeve (capture trending moves)
- [ ] Add volume-based regime filters

### Medium-term (Next 1-2 months)
- [ ] Implement adaptive parameter calibration
- [ ] Build ensemble portfolio (combine all sleeves)
- [ ] Add stop-loss/profit-take logic
- [ ] Expand to Aluminum and Zinc

### Long-term (3-6 months)
- [ ] Machine learning signal enhancement
- [ ] High-frequency microstructure signals
- [ ] Options-based hedging overlay
- [ ] Live trading integration

---

## Notes

**Performance Targets by Sleeve Type:**
- Mean-reversion (HookCore): Sharpe 0.5-0.8
- Trend-following: Sharpe 0.6-1.0
- Crash hedging: Sharpe 0.3-0.5 (insurance, not profit)
- Ensemble portfolio: Sharpe 1.0+ (diversification benefit)

**Turnover Benchmarks:**
- World-class: 5-10x
- Good: 10-20x
- Acceptable: 20-30x
- Problematic: >30x

**Risk Limits:**
- Max single-sleeve vol: 10% annual
- Max portfolio vol: 20-25% annual
- Max single-sleeve DD: -30%
- Max portfolio DD: -25%
