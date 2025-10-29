# Quick Reference Guide
## Metals Quant Infrastructure

---

## 🚀 BUILDING A SLEEVE

```bash
# Navigate to project root
cd C:\Code\Metals

# Run build
run_<sleeve>.bat

# If successful, outputs will be in:
outputs\<Commodity>\<Sleeve>\
```

---

## 📁 FILE LOCATIONS CHEAT SHEET

```
Signal Logic:       src\signals\<sleeve>.py
Build Script:       src\cli\build_<sleeve>.py
Config:             Config\<Commodity>\<sleeve>.yaml
Batch File:         run_<sleeve>.bat
Data:               Data\<commodity>\pricing\canonical\*.csv
Outputs:            outputs\<Commodity>\<Sleeve>\
Layer A Contract:   src\core\contract.py  ← DON'T TOUCH
Validator:          tools\validate_outputs.py
```

---

## 🔧 CREATING A NEW SLEEVE (5 FILES)

1. **Signal function:** `src\signals\newsleeve.py`
   ```python
   def generate_newsleeve_signal(df, **params):
       # Your logic here
       return pos_raw  # Series with {-1, 0, +1}
   ```

2. **Build script:** `src\cli\build_newsleeve.py`
   - Load CSVs → Generate signal → Call Layer A → Write outputs

3. **Config:** `Config\Copper\newsleeve.yaml`
   - Copy policy block from existing sleeve
   - Add your signal parameters

4. **Batch file:** `run_newsleeve.bat`
   - Copy from existing sleeve, update names

5. **Test:** Run and verify outputs pass validation

---

## 📊 REQUIRED CSV COLUMNS

```csv
Price:  date,price
Volume: date,volume
IV:     date,iv
```

**All lowercase, ISO dates (YYYY-MM-DD)**

---

## ✅ VALIDATION CHECKS

After build completes, validator checks:

- ✅ All required columns exist
- ✅ T→T+1 accrual correct (pos_for_ret_t = pos.shift(1))
- ✅ Turnover correct (trade = pos.diff())
- ✅ PnL correct (pnl_gross = pos_for_ret_t × ret)
- ✅ Costs negative or zero
- ✅ Metrics in valid ranges

**If validation fails → check the error message → fix → rebuild**

---

## 🎯 LAYER A vs LAYER B

**LAYER A (contract.py):**
- Vol targeting
- T→T+1 accrual
- Costs on Δpos
- Metrics calculation
- **IMMUTABLE** ← Never change

**LAYER B (your sleeve):**
- Signal generation
- Returns pos_raw ∈ {-1, 0, +1}
- All creativity happens here

---

## 🐛 COMMON ERRORS & FIXES

| Error | Cause | Fix |
|-------|-------|-----|
| `'int' object has no attribute 'days'` | Using df.index as dates | Use df['date'].values |
| `fillna(method='ffill') deprecated` | Old pandas | Use df.ffill() |
| `pos_for_ret_t validation fails` | Manual lag handling | Let Layer A handle it |
| `Missing 'policy' block` | YAML structure wrong | Copy from template |
| Negative Sharpe | Signal not working | Check triggers, parameters |

---

## 📝 YAML CONFIG STRUCTURE

```yaml
io:
  commodity: <Commodity>
  sleeve: <SleeveName>

policy:  # ← Layer A params (copy from template)
  calendar: {...}
  sizing: {...}
  costs: {...}
  pnl:
    t_plus_one_pnl: true  # ← REQUIRED

signal:  # ← Your sleeve params
  param1: value1
  param2: value2
```

---

## 🔍 CHECKING OUTPUTS

```bash
# View metrics
type outputs\Copper\CrashAndRecover\summary_metrics.json

# View first 10 rows of daily series
head -10 outputs\Copper\CrashAndRecover\daily_series.csv

# Or open in Excel
start outputs\Copper\CrashAndRecover\daily_series.csv
```

---

## 📈 INTERPRETING RESULTS

**Good sleeve characteristics:**
- ✅ Sharpe > 1.0 (risk-adjusted returns)
- ✅ Max drawdown < -20% (manageable losses)
- ✅ Consistent performance across regimes
- ✅ Turnover matches hypothesis

**Warning signs:**
- ⚠️ Negative Sharpe (losing money after risk adjustment)
- ⚠️ Max drawdown > -40% (severe losses)
- ⚠️ Very few trades (signal too restrictive)
- ⚠️ Extreme turnover (signal too noisy)

---

## 🎓 SIGNAL DESIGN PRINCIPLES

1. **No look-ahead bias**
   - Use `signal_shift=1` (only T-1 data)
   - Validate with forward testing

2. **Economic intuition**
   - Know WHY the signal should work
   - Test hypothesis explicitly

3. **Regime awareness**
   - Does it work in trends? Mean-reversion?
   - Consider market structure changes

4. **Parameter stability**
   - Test nearby parameter values
   - Avoid over-fitting

5. **Cost awareness**
   - Higher turnover → higher costs
   - Balance signal quality vs costs

---

## 🚨 CRITICAL RULES

1. **NEVER modify Layer A (contract.py)**
   - All sleeves share the same execution rules
   - Changes break comparability

2. **ALWAYS set t_plus_one_pnl: true**
   - This is the T→T+1 accrual requirement
   - Non-negotiable for all sleeves

3. **ALWAYS validate outputs**
   - Don't trust results until validation passes
   - Automated checks catch 95% of errors

4. **ALWAYS use lowercase column names in CSVs**
   - date, price, volume, iv (not Date, Price, etc.)

5. **ALWAYS document your hypothesis**
   - In YAML comments
   - In signal function docstring

---

## 📞 WHEN TO ASK FOR HELP

- ❌ Validation consistently fails
- ❌ Results don't match economic intuition
- ❌ Signal not generating any trades
- ❌ Sharpe extremely negative (< -1.0)
- ❌ Layer A seems wrong (it's not - check Layer B first!)

---

## 🎯 NEXT STEPS AFTER SUCCESSFUL BUILD

1. **Analyze signal triggers**
   - Plot pos_raw vs price
   - Count long/short/flat periods

2. **Review performance regimes**
   - When did it make money?
   - When did it lose money?
   - Why?

3. **Parameter sensitivity**
   - Test ±20% on key parameters
   - Check stability

4. **Compare to baseline**
   - Simple trend following
   - Buy and hold
   - Mean reversion

5. **Document findings**
   - What worked? What didn't?
   - Update hypothesis

---

**Remember:** Building good quant strategies is iterative. First build rarely works perfectly. Use validation failures and poor results as learning opportunities.

**Renaissance Wisdom:** *"The market doesn't care about your hypothesis. Test everything, trust nothing until proven."*
