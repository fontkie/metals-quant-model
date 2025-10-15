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
