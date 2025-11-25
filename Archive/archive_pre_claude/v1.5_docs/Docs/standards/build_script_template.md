build_script_template.md (v2.3, Final)
# build_script_template.md (v2.3)

**Purpose**  
Defines the two-layer build contract and a reference CLI wrapper used across all sleeves.  
Layer A = immutable core; Layer B = adapters/features.  
New code must implement Layer A exactly.

---

## 1) Layer A — Core Build Contract

**Inputs (canonical CSV only; UTF-8, comma-delimited)**  


Data/<asset>/pricing/canonical/<series>.canonical.csv

schema (lowercase, exactly):

date,price

- `date`: ISO date, strictly increasing, business-day frequency; no duplicates, no NaNs.  
- `price`: float, may be negative; no NaNs.

---

**Outputs**  


outputs/<Asset>/<Sleeve>/
├─ daily_series.csv
└─ summary_metrics.json


**daily_series.csv — required columns & definitions**
| Column | Definition |
|---------|-------------|
| `price` | Input price aligned to trading days |
| `ret` | Simple daily return: `price.pct_change()`; first value = 0.0 |
| `pos` | End-of-day target position (signed leverage), bounded by [-leverage_cap, +leverage_cap] |
| `pos_for_ret_t` | `pos.shift(1)` → position that earns `ret_t` |
| `trade` | Signed turnover = `pos.diff().fillna(0.0)` |
| `cost` | `-abs(trade) * (one_way_bps/10_000)` |
| `pnl_gross` | `pos_for_ret_t * ret` |
| `pnl_net` | `pnl_gross + cost` |

**summary_metrics.json — required keys & definitions**
| Key | Definition |
|-----|-------------|
| `annual_return` | Compounded net return = (∏(1 + pnl_net))**(252/N) - 1 |
| `annual_vol` | Stdev of net daily return × √252 |
| `sharpe` | Mean(pnl_net)/Stdev(pnl_net) × √252 (rf=0) |
| `max_drawdown` | Max peak-to-trough drawdown of cumulative net equity |
| `obs` | Number of rows in `daily_series.csv` |
| `cost_bps` | Echo YAML `one_way_bps_default` |

---

## 2) Execution Policy (immutable in Layer A)
- Signal formed on T close; trade executed T close; PnL accrues T+1 (`pos_for_ret_t = pos.shift(1)`).
- Costs applied on Δpos only (one-way bps).
- Vol targeting (if enabled in YAML): realised vol = stdev(ret, lookback) × √252; target leverage clipped by leverage_cap.

---

## 3) Layer B — Adapters & Optional Features
- **Adapters:** Excel→canonical, DB readers, calendar resampling.  
- **Features (default OFF):** robust_vol, buffer_trades, drawdown_filter, reporting.  
- **Rule:** Feature toggles must not alter Layer-A semantics unless explicitly enabled in YAML.

---

## 4) Canonical Data Policy (single source of truth)
Source workbook: `Data/<asset>/pricing/pricing_values.xlsx` (sheet *Raw*).  
Convert via `tools/make_canonical.py` → `Data/<asset>/pricing/canonical/*.canonical.csv`.

**Cleaning rules (enforced by the tool):**
- Drop NaN dates/prices; keep negatives.  
- Sort by date; drop duplicates.  
- No weekend/holiday forward-fills; gaps appear as no rows.  
- Warn if >20% rows dropped (configurable).

---

## 5) Reference CLI Wrapper (Layer B)
```python
# Assumes core/contract.py defines build_core(df, cfg)
# src/cli/build_<sleeve>_v2.py
import argparse, json
from pathlib import Path
import pandas as pd, yaml
from core.contract import build_core  # Layer A

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True)
    p.add_argument("--outdir", required=True)
    p.add_argument("--config", required=True)
    args = p.parse_args()

    df = pd.read_csv(args.csv, parse_dates=["date"])  # lowercase 'date','price'
    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f)

    daily_df, metrics = build_core(df, cfg)
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    daily_df.to_csv(outdir/"daily_series.csv", index=False)
    (outdir/"summary_metrics.json").write_text(json.dumps(metrics, indent=2))


Run (Windows)

python src\cli\build_<sleeve>_v2.py ^
  --csv Data\<asset>\pricing\canonical\<series>.canonical.csv ^
  --outdir outputs\<Asset>\<Sleeve> ^
  --config Config\<Commodity>\<sleeve>.yaml


Run (macOS/Linux)

python src/cli/build_<sleeve>_v2.py \
  --csv Data/<asset>/pricing/canonical/<series>.canonical.csv \
  --outdir outputs/<Asset>/<Sleeve> \
  --config Config/<Commodity>/<sleeve>.yaml

6) What a Contributor Must Provide

Path to canonical CSV, sleeve YAML, and desired output directory.

No Excel paths. No hidden state.

Code must write exactly the columns/keys defined above.

Timing, costs, and PnL semantics all come from Layer A.

7) Checklist

✅ Canonical data present
✅ Required columns present
✅ T→T+1 accrual
✅ Costs on Δpos
✅ Leverage cap enforced
✅ Provenance logged (optional)


**Alignment check:**  
- `cost_bps` field and cost naming match the YAML template and execution guide.  
- Case, naming, and schema references consistent across all files.

---