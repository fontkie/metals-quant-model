# Metals Quant Infrastructure - Standards & Protocols
## Version 2.0 | October 2025

---

## TABLE OF CONTENTS

1. [Architecture Overview](#architecture-overview)
2. [Layer A: Immutable Execution Contract](#layer-a-immutable-execution-contract)
3. [Layer B: Sleeve-Specific Logic](#layer-b-sleeve-specific-logic)
4. [File Structure Standards](#file-structure-standards)
5. [Data Standards](#data-standards)
6. [Config Standards (YAML)](#config-standards-yaml)
7. [Output Standards](#output-standards)
8. [Build Process](#build-process)
9. [Validation Protocol](#validation-protocol)
10. [Naming Conventions](#naming-conventions)
---

## ARCHITECTURE OVERVIEW

### Two-Layer Design

```
┌─────────────────────────────────────────────────────────┐
│                    LAYER B (Sleeves)                    │
│  - Signal generation logic (sleeve-specific)            │
│  - Returns pos_raw ∈ {-1, 0, +1}                       │
│  - Examples: CrashAndRecover, MomentumTail              │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│              LAYER A (Execution Contract)               │
│  - Vol targeting, leverage caps                         │
│  - T→T+1 PnL accrual (immutable)                       │
│  - Cost model (bps on Δpos)                            │
│  - Metrics calculation                                  │
│  - SHARED BY ALL SLEEVES                               │
└─────────────────────────────────────────────────────────┘
```

**Critical Rule:** Layer A is **immutable** across all sleeves. No exceptions.

---

## LAYER A: IMMUTABLE EXECUTION CONTRACT

### Location
```
src/core/contract.py
```

### Responsibilities

1. **Vol Targeting**
   - Calculate realized vol using T-1 returns
   - Target leverage = ann_target / realized_vol
   - Apply leverage cap

2. **T→T+1 PnL Accrual**
   - Position at T-1 earns return at T
   - `pos_for_ret_t = pos.shift(1)`
   - **This is non-negotiable**

3. **Cost Model**
   - Costs applied to `|Δpos|` only
   - `cost = -|trade| * (one_way_bps / 10,000)`
   - Costs are always negative or zero

4. **Metrics Calculation**
   - Annual return (compounded)
   - Annual vol (√252 scaling)
   - Sharpe ratio
   - Max drawdown (peak-to-trough)

### Input Schema
```python
df: pd.DataFrame with columns:
    - date (datetime)
    - price (float)
    - ret (float)  # calculated internally if not provided
    - pos_raw (float)  # from Layer B signal

cfg: dict from YAML with structure:
    - policy.sizing.ann_target
    - policy.sizing.vol_lookback_days_default
    - policy.sizing.leverage_cap_default
    - policy.costs.one_way_bps_default
    - policy.pnl.t_plus_one_pnl (must be true)
```

### Output Schema
```python
Returns tuple[pd.DataFrame, dict]:
    daily_df: columns = [
        'date', 'price', 'ret', 'pos', 'pos_for_ret_t',
        'trade', 'cost', 'pnl_gross', 'pnl_net'
    ]
    
    metrics: dict = {
        'annual_return': float,
        'annual_vol': float,
        'sharpe': float,
        'max_drawdown': float,
        'obs': int,
        'cost_bps': float
    }
```

---

## LAYER B: SLEEVE-SPECIFIC LOGIC

### Location Pattern
```
src/signals/<sleeve_name>.py
src/cli/build_<sleeve_name>.py
```

### Signal Function Contract

**Every sleeve must provide a function:**
```python
def generate_<sleeve>_signal(
    df: pd.DataFrame,
    **signal_params
) -> pd.Series:
    """
    Generate position signal.
    
    Args:
        df: DataFrame with required columns (varies by sleeve)
        **signal_params: Sleeve-specific parameters from YAML
    
    Returns:
        pd.Series with values in {-1, 0, +1}
        - Index matches df.index
        - +1 = LONG
        -1 = SHORT
         0 = FLAT
    """
    ...
    return pos_raw
```

### Build Script Contract

**Every sleeve must provide a CLI wrapper:**
```python
# src/cli/build_<sleeve>_v2.py

def main():
    # 1. Parse arguments (--csv-price, --config, --outdir, etc.)
    # 2. Load canonical CSV(s)
    # 3. Load YAML config
    # 4. Generate signal (call signal function)
    # 5. Call Layer A: build_core(df, cfg)
    # 6. Write outputs (daily_series.csv, summary_metrics.json)
    # 7. Print summary
```

---

## FILE STRUCTURE STANDARDS

### Required Directory Layout
```
C:\Code\Metals\
├── src\
│   ├── __init__.py
│   ├── core\
│   │   ├── __init__.py
│   │   └── contract.py              # Layer A (immutable)
│   ├── signals\
│   │   ├── __init__.py
│   │   ├── crashandrecover.py       # Sleeve 1
│   │   └── momentumtail.py          # Sleeve 2
│   └── cli\
│       ├── __init__.py
│       ├── build_crashandrecover.py
│       └── build_momentumtail_v2.py
├── Config\
│   ├── Copper\
│   │   ├── crashandrecover.yaml
│   │   └── momentumtail.yaml
│   ├── Aluminum\
│   └── Zinc\
├── Data\
│   ├── copper\
│   │   └── pricing\
│   │       └── canonical\
│   │           ├── copper_lme_3mo.canonical.csv
│   │           ├── copper_lme_3mo_volume.canonical.csv
│   │           └── copper_lme_1mo_impliedvol.canonical.csv
│   └── ...
├── outputs\                         # lowercase!
│   ├── Copper\
│   │   ├── CrashAndRecover\
│   │   │   ├── daily_series.csv
│   │   │   └── summary_metrics.json
│   │   └── MomentumTail\
│   └── ...
├── tools\
│   └── validate_outputs.py
├── run_crashandrecover.bat
├── run_momentumtail.bat
└── README.md
```

---

## DATA STANDARDS

### Canonical CSV Format

**Price Data:**
```csv
date,price
2000-01-03,1888.5
2000-01-04,1865.0
...
```

**Volume Data:**
```csv
date,volume
2003-12-11,724.0
2003-12-12,777.0
...
```

**Implied Vol Data:**
```csv
date,iv
2010-01-04,0.235
2010-01-05,0.241
...
```

### Requirements
- ✅ Column names: **lowercase** (`date`, `price`, `volume`, `iv`)
- ✅ Date format: `YYYY-MM-DD` (ISO 8601)
- ✅ Sorted by date (ascending)
- ✅ No duplicate dates
- ✅ Missing data: forward-fill or drop (document in sleeve logic)

### File Naming Convention
```
<commodity>_<exchange>_<tenor>_<datatype>.canonical.csv

Examples:
- copper_lme_3mo.canonical.csv
- copper_lme_3mo_volume.canonical.csv
- copper_lme_1mo_impliedvol.canonical.csv
- aluminum_lme_3mo.canonical.csv
```

---

## CONFIG STANDARDS (YAML)

### Required Structure

Every YAML config must have two top-level blocks:

1. **`policy`** - Layer A parameters (immutable structure)
2. **`signal`** - Layer B parameters (sleeve-specific)

### Template

```yaml
# Config/<Commodity>/<sleeve>.yaml

io:
  commodity: <Commodity>
  sleeve: <SleeveName>

policy:
  calendar:
    exec_weekdays: [0, 1, 2, 3, 4]  # Mon-Fri
    origin_for_exec:
      "0": "-1B"
      "1": "-1B"
      "2": "-1B"
      "3": "-1B"
      "4": "-1B"
    fill_default: close_T

  sizing:
    ann_target: 0.10                      # 10% target vol
    vol_lookback_days_default: 63         # ~3 months
    leverage_cap_default: 2.0             # Max 2x leverage

  costs:
    one_way_bps_default: 1.5              # 1.5 bps per trade

  pnl:
    formula: pos_lag_times_simple_return
    t_plus_one_pnl: true                  # REQUIRED: T→T+1

# Sleeve-specific parameters
signal:
  # ... sleeve params here ...
```

### Policy Block Requirements

**Must have:**
- `calendar` (weekdays and execution timing)
- `sizing` (ann_target, vol_lookback, leverage_cap)
- `costs` (one_way_bps)
- `pnl` with `t_plus_one_pnl: true`

**Never change:**
- The structure of the `policy` block
- The requirement for `t_plus_one_pnl: true`

---

## OUTPUT STANDARDS

### daily_series.csv

**Required columns (exact names):**
```csv
date,price,ret,pos,pos_for_ret_t,trade,cost,pnl_gross,pnl_net
```

**Column Definitions:**
- `date`: Trading date (YYYY-MM-DD)
- `price`: Underlying price
- `ret`: Simple return (price.pct_change())
- `pos`: Target position after vol scaling & leverage cap
- `pos_for_ret_t`: Position that earned today's return (pos.shift(1))
- `trade`: Position change (pos.diff())
- `cost`: Trading cost in return units (≤ 0)
- `pnl_gross`: pos_for_ret_t × ret
- `pnl_net`: pnl_gross + cost

**Invariants (validated):**
1. `pos_for_ret_t[t] == pos[t-1]`
2. `trade[t] == pos[t] - pos[t-1]`
3. `pnl_gross[t] == pos_for_ret_t[t] × ret[t]`
4. `cost[t] ≤ 0`

### summary_metrics.json

**Required keys:**
```json
{
  "annual_return": <float>,    // Compounded annual return
  "annual_vol": <float>,       // Annualized volatility (√252)
  "sharpe": <float>,           // Risk-adjusted return
  "max_drawdown": <float>,     // Peak-to-trough (≤ 0)
  "obs": <int>,                // Number of observations
  "cost_bps": <float>          // One-way cost in bps
}
```

---

## BUILD PROCESS

### Standard Build Flow

```bash
# 1. Run build script
run_<sleeve>.bat

# 2. Script calls Python CLI
python src\cli\build_<sleeve>.py \
    --csv-price <path> \
    --csv-volume <path> \  # if needed
    --csv-iv <path> \      # if needed
    --config Config\<Commodity>\<sleeve>.yaml \
    --outdir outputs\<Commodity>\<Sleeve>

# 3. Python script:
#    a. Loads CSVs
#    b. Loads YAML
#    c. Generates signal (Layer B)
#    d. Calls build_core() (Layer A)
#    e. Writes outputs

# 4. Validation runs automatically
python tools\validate_outputs.py \
    --outdir outputs\<Commodity>\<Sleeve>
```

### Batch File Template

```batch
@echo off
echo ========================================
echo Building <Sleeve> (<Commodity>)
echo ========================================
python src\cli\build_<sleeve>.py --csv-price Data\<commodity>\pricing\canonical\<file>.csv --config Config\<Commodity>\<sleeve>.yaml --outdir outputs\<Commodity>\<Sleeve>

if %errorlevel% neq 0 (
    echo.
    echo ❌ Build failed!
    pause
    exit /b 1
)

echo.
echo ✅ Build complete! Validating outputs...
echo.
python tools\validate_outputs.py --outdir outputs\<Commodity>\<Sleeve>

pause
```

---

## VALIDATION PROTOCOL

### Automated Checks

The `validate_outputs.py` script verifies:

**Schema Checks:**
- ✅ All required columns present
- ✅ All required metrics present
- ✅ Correct data types

**Integrity Checks:**
- ✅ pos_for_ret_t = pos.shift(1) (T→T+1 accrual)
- ✅ trade = pos.diff() (turnover calculation)
- ✅ pnl_gross = pos_for_ret_t × ret (PnL calculation)
- ✅ cost ≤ 0 (costs never positive)
- ✅ max_drawdown ∈ [-1, 0] (valid range)
- ✅ annual_vol ≥ 0 (volatility positive)

**Data Quality:**
- ⚠️ Minimal NaNs (< 1% allowance for edge effects)
- ⚠️ No infinite values
- ⚠️ Reasonable metric ranges

### Manual Review Checklist

After automated validation passes, manually verify:

1. **Signal Logic**
   - [ ] Does pos_raw make economic sense?
   - [ ] Are entry/exit triggers firing correctly?
   - [ ] Is the signal shift implemented (no look-ahead)?

2. **Performance**
   - [ ] Does Sharpe match expectations for this strategy type?
   - [ ] Is turnover reasonable?
   - [ ] Are drawdowns concentrated in expected regimes?

3. **Config Alignment**
   - [ ] Do parameters match the strategy hypothesis?
   - [ ] Is leverage cap appropriate for the sleeve?
   - [ ] Are costs realistic for the market?

---

## NAMING CONVENTIONS

### File Names
- **Python modules:** `lowercase_with_underscores.py`
- **Classes:** `PascalCase`
- **Functions:** `lowercase_with_underscores()`
- **Constants:** `UPPERCASE_WITH_UNDERSCORES`

### Sleeve Names
- **In code:** `lowercase` (e.g., `crashandrecover.py`)
- **In output dirs:** `PascalCase` (e.g., `CrashAndRecover/`)
- **In YAML:** `PascalCase` (e.g., `sleeve: CrashAndRecover`)

### Commodity Names
- **In directories:** `lowercase` (e.g., `copper/`, `aluminum/`)
- **In YAML:** `PascalCase` (e.g., `commodity: Copper`)
- **In file names:** `lowercase` (e.g., `copper_lme_3mo.canonical.csv`)

### Variable Names (Standard Conventions)
```python
# Time series
price       # Raw price
ret         # Simple return
pos_raw     # Signal before vol scaling (∈ {-1, 0, +1})
pos         # Position after vol scaling
trade       # Position change (Δpos)
cost        # Trading costs
pnl_gross   # Gross PnL (before costs)
pnl_net     # Net PnL (after costs)

# Parameters
ann_target          # Annual volatility target
vol_lookback        # Lookback for realized vol
leverage_cap        # Maximum absolute leverage
one_way_bps         # One-way trading cost (basis points)

# Metadata
df          # DataFrame
cfg         # Config dict
metrics     # Summary metrics dict
```

---

## SLEEVE DEVELOPMENT CHECKLIST

When creating a new sleeve:

### 1. Signal Logic (`src/signals/<sleeve>.py`)
- [ ] Create `generate_<sleeve>_signal()` function
- [ ] Returns `pd.Series` with values in {-1, 0, +1}
- [ ] Implement signal_shift (no look-ahead bias)
- [ ] Document signal logic in docstring
- [ ] Add inline comments for complex logic

### 2. Build Script (`src/cli/build_<sleeve>.py`)
- [ ] Parse CLI arguments
- [ ] Load canonical CSV(s)
- [ ] Validate CSV schemas
- [ ] Load YAML config
- [ ] Validate YAML structure
- [ ] Generate signal (call signal function)
- [ ] Call `build_core(df, cfg)` from Layer A
- [ ] Write outputs to `--outdir`
- [ ] Print summary metrics

### 3. Config File (`Config/<Commodity>/<sleeve>.yaml`)
- [ ] Include full `policy` block (copy from template)
- [ ] Set `t_plus_one_pnl: true`
- [ ] Add sleeve-specific `signal` block
- [ ] Document parameter choices in comments
- [ ] Include expected behavior description

### 4. Batch File (`run_<sleeve>.bat`)
- [ ] Use standard template format
- [ ] Include error checking (`if %errorlevel% neq 0`)
- [ ] Call validation script
- [ ] Use relative paths from project root

### 5. Testing
- [ ] Run on historical data (3+ years)
- [ ] Verify outputs pass validation
- [ ] Check signal triggers visually
- [ ] Review PnL attribution
- [ ] Compare vs simple baseline

### 6. Documentation
- [ ] Add docstrings to all functions
- [ ] Document signal hypothesis
- [ ] Note any known issues/limitations
- [ ] Add example usage

---

## DEBUGGING GUIDE

### Common Errors

**1. "AttributeError: 'int' object has no attribute 'days'"**
- **Cause:** Using `df.index[i]` as dates when index is integers
- **Fix:** Use `df['date'].values` or set date as index

**2. "pos_for_ret_t ≠ pos.shift(1) validation failure"**
- **Cause:** Manual position lag not matching Layer A expectations
- **Fix:** Let Layer A handle the lag - just return `pos_raw`

**3. "FutureWarning: fillna(method='ffill') is deprecated"**
- **Cause:** Old pandas syntax
- **Fix:** Use `df.ffill()` instead

**4. "YAML must have 'policy' block"**
- **Cause:** Missing or misnamed policy section
- **Fix:** Copy policy block from template exactly

**5. Negative Sharpe / Large Drawdown**
- **Cause:** Signal logic may not match market dynamics
- **Fix:** 
  - Check signal triggers (plot pos_raw vs price)
  - Verify parameters (are lookbacks too long/short?)
  - Test regime dependence (does it only work in trends?)

### Debugging Workflow

```bash
# 1. Enable verbose output
python src\cli\build_<sleeve>.py <args> --verbose  # if implemented

# 2. Check intermediate outputs
# Add print statements in signal function:
print(f"Signal triggers: {pos_raw.sum()}")
print(f"Long: {(pos_raw > 0).sum()}, Short: {(pos_raw < 0).sum()}")

# 3. Validate each step
python -c "
import pandas as pd
df = pd.read_csv('outputs/.../daily_series.csv')
print(df[['date', 'pos', 'pos_for_ret_t', 'trade']].head(10))
"

# 4. Visual inspection
# Export to Excel, plot pos vs price
```

---

## VERSION HISTORY

**v2.0 (October 2025)**
- Initial standardization of two-layer architecture
- CrashAndRecover sleeve implemented
- MomentumTail sleeve implemented
- Validation framework established

---

## CONTACTS & SUPPORT

**PM:** [Your name]
**Senior Quant:** Claude (ex-Renaissance)
**Code Repository:** `C:\Code\Metals`

---

**Remember:** The Layer A contract is sacred. All sleeves follow the same execution rules. Signal logic is where creativity lives - execution is where discipline lives.

**Renaissance Principle:** *"Measure twice, trade once. Every strategy must survive contact with validation before it touches capital."*
