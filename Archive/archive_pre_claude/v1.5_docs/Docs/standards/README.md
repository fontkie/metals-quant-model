README.md (v2.2)

Metals Model 3.0 — Core Standards

1) Repo layout (two-layer contract)
Metals/
├─ Config/
│  ├─ global.yaml
│  └─ Copper/
│     └─ crashandrecover.yaml
├─ Data/
│  └─ copper/pricing/
│     ├─ pricing_values.xlsx
│     └─ canonical/
│        └─ copper_lme_3mo.canonical.csv
├─ tools/
│  └─ make_canonical.py
├─ src/
│  ├─ core/
│  │  └─ contract.py         # Layer A engine
│  ├─ signals/
│  │  └─ crash_and_recover.py
│  └─ cli/
│     └─ build_crashandrecover_v2.py  # Layer B wrapper
└─ outputs/
   └─ Copper/CrashAndRecover/

2) Layer A (immutable)
- T→T+1 accrual, costs on Δpos, vol targeting, leverage cap.
- Standard output schema & metrics (see template).
- Writes only to outputs/<Asset>/<Sleeve>/.

3) Layer B (wrappers/features)
- Per-sleeve CLI scripts read: (a) canonical CSV (date,price), (b) YAML.
- Optional features: robust_vol, buffers, reporting; OFF by default.

4) Canonical data policy
- Builds never read Excel. Convert via tools/make_canonical.py first.
- Canonical schema is fixed: date,price (lowercase).
- Cleaning rules: drop NaNs/dupes, sort by date, no weekend forward-fills.

5) Running a build (example)
Windows:
python src\cli\build_crashandrecover_v2.py ^
  --csv Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv ^
  --outdir outputs\Copper\CrashAndRecover ^
  --config Config\Copper\crashandrecover.yaml
(macOS/Linux: replace backslashes with slashes.)

6) Outputs & validation
- daily_series.csv: price,ret,pos,pos_for_ret_t,trade,cost,pnl_gross,pnl_net.
- summary_metrics.json: annual_return,annual_vol,sharpe,max_drawdown,obs,cost_bps.
- Optional: run_config.json (provenance).

7) Contributor checklist
- Canonical input present ✅
- YAML has required policy blocks (including pnl.formula) ✅
- Leverage capped; T→T+1 enforced ✅
- Costs only on Δpos ✅
- Required columns & metrics written ✅
- No Excel references in builds ✅

Summary
Same core, same inputs, same outputs. Sleeves differ only by signal logic and YAML.
