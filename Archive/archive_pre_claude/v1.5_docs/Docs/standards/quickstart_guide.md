## 🧱 FILE 3 — **quickstart_guide.md (v2.3, Final)**

```markdown
# quickstart_guide.md (v2.3)

**Goal**  
Run any sleeve end-to-end using canonical data + the Layer-A core. Takes five minutes.

---

## 1) Environment Setup

**Windows**
```bash
cd C:\Code\Metals
.venv\Scripts\activate
pip install -r requirements.txt
macOS / Linux

bash
Copy code
cd ~/Code/Metals
source .venv/bin/activate
pip install -r requirements.txt
2) Create Canonical Data (one-time per update)
Update Excel: Data/<asset>/pricing/pricing_values.xlsx (sheet Raw)

Convert to canonical CSVs:

bash
Copy code
python tools\make_canonical.py            # Windows
python tools/make_canonical.py            # macOS/Linux
Output:

bash
Copy code
Data/<asset>/pricing/canonical/<series>.canonical.csv
# columns (lowercase, exact): date,price
⚠️ Columns are case-sensitive and must be lowercase (date, price).

3) Configure the Sleeve
Example YAML:

yaml
Copy code
io: { commodity: Copper, sleeve: CrashAndRecover }

policy:
  calendar:
    exec_weekdays: [0,1,2,3,4]
    origin_for_exec: {"0":"-1B","1":"-1B","2":"-1B","3":"-1B","4":"-1B"}
    fill_default: close_T

  sizing:  { ann_target: 0.10, vol_lookback_days_default: 21, leverage_cap_default: 2.5 }
  costs:   { one_way_bps_default: 1.5 }
  pnl:     { t_plus_one_pnl: true, formula: pos_lag_times_simple_return }  # REQUIRED

signal:
  # sleeve-specific parameters...
4) Run the Build
Windows

bash
Copy code
python src\cli\build_<sleeve>_v2.py ^
  --csv Data\<asset>\pricing\canonical\<series>.canonical.csv ^
  --outdir outputs\<Asset>\<Sleeve> ^
  --config Config\<Commodity>\<sleeve>.yaml
macOS / Linux

bash
Copy code
python src/cli/build_<sleeve>_v2.py \
  --csv Data/<asset>/pricing/canonical/<series>.canonical.csv \
  --outdir outputs/<Asset>/<Sleeve> \
  --config Config/<Commodity>/<sleeve>.yaml
5) Outputs (always produced)
php-template
Copy code
outputs/<Asset>/<Sleeve>/
  ├─ daily_series.csv
  └─ summary_metrics.json
daily_series.csv columns:
price,ret,pos,pos_for_ret_t,trade,cost,pnl_gross,pnl_net

summary_metrics.json keys:
annual_return, annual_vol, sharpe, max_drawdown, obs, cost_bps

6) Verify Quickly
Check	Expected
Annual vol	≈ target (e.g. 10%)
pos_for_ret_t	equals pos.shift(1)
NaNs	None in pnl_net
Trades	Reasonable; no leverage > cap
Output path	outputs/<Asset>/<Sleeve>/ created

7) What to Hand to Another Quant or AI
Canonical CSV path (.../canonical/<series>.canonical.csv)

YAML config path (Config/<Commodity>/<sleeve>.yaml)

Desired output directory

No Excel paths. No hidden parameters. No external dependencies.

8) Troubleshooting
Symptom	Likely Cause	Fix
Empty PnL	Missing T→T+1	Ensure t_plus_one_pnl: true
Wrong path	Non-canonical input	Point --csv to /canonical/*.canonical.csv
Weird leverage	Missing cap	Set leverage_cap_default in YAML
Vol off-target	Lookback mismatch	Confirm vol_lookback_days_default = 21
Missing metrics	Wrong output path	Verify --outdir outputs/<Asset>/<Sleeve>

yaml
Copy code

**Alignment check:**  
- Perfect alignment with YAML example and Execution Policy.  
- Formatting corrected for readability and code-fence compliance.

---

## 🧱 FILE 4 — **yaml_example_template.md (v2.2, Final)**

```markdown
# yaml_example_template.md (v2.2)

**Purpose**  
Authoritative YAML template for sleeves. Fields marked *required* must be present.

---

# Config/<Commodity>/<sleeve>.yaml

io:
  commodity: Copper           # required
  sleeve: CrashAndRecover     # required

policy:
  calendar:                   # required
    exec_weekdays: [0,1,2,3,4]
    origin_for_exec: {"0":"-1B","1":"-1B","2":"-1B","3":"-1B","4":"-1B"}
    fill_default: close_T

  sizing:                     # required
    ann_target: 0.10
    vol_lookback_days_default: 21
    leverage_cap_default: 2.5

  costs:                      # required
    one_way_bps_default: 1.5

  pnl:                        # required
    formula: pos_lag_times_simple_return
    t_plus_one_pnl: true

signal:
  # examples (delete/edit for your sleeve)
  trend_window: 63
  vol_window: 21
  entry_z: 0.5
  exit_z: 0.0
  exit_timeout_days: 63
  volume_lookback: 21
  volume_threshold_multiple: 1.5

---

## Notes
- No Excel paths/columns here; builds read canonical CSV (`date,price`) only.  
- Columns in canonical input files must be **lowercase** (`date,price`) — *case-sensitive*.  
- `pnl.formula` must be `pos_lag_times_simple_return` for live-safe T→T+1.  
- Add any sleeve-specific keys under `signal:` — the core will pass them to your signal.

---

## Validation checklist
✅ `io.commodity` & `io.sleeve` present  
✅ All policy blocks present  
✅ `pnl.t_plus_one_pnl: true`  
✅ Signal parameters defined (as needed)
Alignment check:

Fully synchronized with Execution Policy and Quickstart YAML.

Added lowercase note for canonical schema consistency.