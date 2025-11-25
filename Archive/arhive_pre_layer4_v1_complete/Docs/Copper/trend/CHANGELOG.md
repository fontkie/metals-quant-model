# Changelog — TrendCore (Copper 3M)

## [0.1.0] — 2025-10-15
- Freeze production spec to 20/60/120-day log-momentum (MOM), majority-vote method.
- Execution cadence: Mon/Wed, T+1 fill.
- Risk management: 10% annual vol target (21-day), 3× leverage cap, 1.5 bps turnover cost.
- Optional quiet filter (`--quiet_q`), default off.
- Outputs aligned with repo structure:
  - `outputs/copper/trend/daily_series.csv`
  - `outputs/copper/trend/equity_curves.csv`
  - `outputs/copper/trend/summary_metrics.csv`


---

## `Docs/Copper/CHANGELOG.md` (append this entry)
```markdown
## [2025-10-17] TrendCore-Cu-v1-Tclose

- **Added** `src/build_trend.py` implementing **T-close** execution (Mon/Wed): signals from Fri/Tue, trade at same-day close, PnL starts next day.
- **Added** `Docs/Copper/trend/config.yaml` documenting static parameters: threshold=0.85, z_window=252, vol_lookback=28, cap=2.5×, costs=1.5 bps.
- **Updated** `Docs/standards/real_world_rules.md`: pricing sleeves default to **trade on T**; other sleeves may declare `close_Tplus1`.
- **Merged** execution policy into `Config/schema.yaml` and added `src/utils/policy.py` header check used by the builder.
- **Result (reference, 2008–2017 IS / 2018+ OOS)**: Sharpe ~0.33 / ~0.55 under T+1; ~0.35 / ~0.58 under **T-close**. (Exact values depend on data cut; see `summary.json`.)
