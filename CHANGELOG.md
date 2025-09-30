## v0.2 — 2025-09-30
- Standardised all scripts to use named arguments (`--db`, `--sheet`, `--outdir`, etc.)
- Loader confirmed working with Excel tab `Raw`
- Signals script writes `prices_std` view and `signals` table, CSV export nested under outputs/Copper/Copper
- Test script now called with `--db` and validates `prices_std` + `signals`
- Backtest script now runs from DB (`--prices-table prices_std --signals-table signals`)
- Run_All.bat orchestrates all four steps end-to-end
