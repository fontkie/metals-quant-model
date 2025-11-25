# Chinese Demand Data - Canonical Conversion Guide

**Date:** November 18, 2025  
**Purpose:** Convert Bloomberg Chinese demand Excel to canonical CSV format

---

## Quick Start

### Step 1: Place Files
Copy the scripts to your tools directory:
```batch
copy make_canonical_copper_demand.py C:\Code\Metals\tools\
copy run_make_canonical_copper_demand.bat C:\Code\Metals\
```

### Step 2: Verify Excel File
Make sure your Excel file exists at:
```
C:\Code\Metals\Data\copper\fundamentals\china_demand_values.xlsx
```

### Step 3: Run Conversion
```batch
cd C:\Code\Metals
run_make_canonical_copper_demand.bat
```

### Step 4: Verify Output
Check that canonical file was created:
```
C:\Code\Metals\Data\copper\fundamentals\canonical\chinese_demand_proxy.canonical.csv
```

Expected format:
```csv
date,demand_index
2012-04-30,7.4
2012-05-31,7.7
2012-06-30,5.9
...
```

---

## Configuration

### Excel File Structure

**Expected structure:**
- Sheet name: `Raw` (default)
- Date column: `Date`
- Demand column: `chinese_demand_proxy`

**If your Excel has different names:**

Edit `make_canonical_copper_demand.py` line 82-86:

```python
excel_to_canonical(
    excel_path=r"C:\Code\Metals\Data\copper\fundamentals\china_demand_values.xlsx",
    sheet="Raw",              # ← Change sheet name here
    date_col="Date",          # ← Change date column name here
    fields=[
        "chinese_demand_proxy",  # ← Change demand column name here
    ],
    out_dir=r"C:\Code\Metals\Data\copper\fundamentals\canonical",
)
```

### Common Sheet Names

Bloomberg exports typically use:
- `Raw` (most common)
- `Sheet1` (default)
- `Data`
- `Bloomberg`

Check your Excel file to see which sheet contains the data.

### Common Column Names

Date columns are usually:
- `Date` (most common)
- `date`
- `Dates`
- `DATE`

Demand columns might be:
- `chinese_demand_proxy`
- `China Demand`
- `Demand Index`
- `BBG_DEMAND_PROXY`

---

## Adding Multiple Series

If you have multiple demand-related series in the same Excel file, add them to the `fields` list:

```python
fields=[
    "chinese_demand_proxy",
    "chinese_pmi",
    "chinese_industrial_production",
    "chinese_copper_consumption",
],
```

Each will be converted to its own canonical CSV:
- `chinese_demand_proxy.canonical.csv`
- `chinese_pmi.canonical.csv`
- `chinese_industrial_production.canonical.csv`
- `chinese_copper_consumption.canonical.csv`

---

## Output Format

The canonical CSV will have exactly 2 columns:

```csv
date,demand_index
2012-04-30,7.4
2012-05-31,7.7
...
```

**Key features:**
- `date` column: ISO format (YYYY-MM-DD)
- `demand_index` column: Numeric values only
- Sorted by date (ascending)
- No duplicate dates
- No missing values (rows with NAs are dropped)

---

## Validation Checklist

After conversion, verify:

### ✅ File Created
- [ ] File exists at: `Data\copper\fundamentals\canonical\chinese_demand_proxy.canonical.csv`
- [ ] File is not empty (>10 KB for ~160 months of data)

### ✅ Format Correct
- [ ] Two columns: `date` and `demand_index`
- [ ] Dates are month-end (e.g., 2012-04-30, not 2012-04-01)
- [ ] Values are numeric (no text/errors)
- [ ] No missing values

### ✅ Data Quality
- [ ] At least 100+ rows (ideally 150+)
- [ ] Date range covers recent years (should go to 2025)
- [ ] Values seem reasonable (typically -10 to +20 range)
- [ ] No obvious gaps or errors

### ✅ Integration Ready
- [ ] File path matches `chinese_demand.yaml` configuration
- [ ] Can run `run_chinese_demand.bat` without errors

---

## Troubleshooting

### Issue: "FileNotFoundError: Excel file not found"

**Fix:**
1. Check Excel file exists at: `C:\Code\Metals\Data\copper\fundamentals\china_demand_values.xlsx`
2. If file is elsewhere, update path in `make_canonical_copper_demand.py` line 82

### Issue: "KeyError: 'Date'"

**Fix:**
1. Open Excel file and check date column name
2. Update `date_col` parameter in script (line 84)

### Issue: "KeyError: 'chinese_demand_proxy'"

**Fix:**
1. Open Excel file and check demand column name
2. Update field name in script (line 86)

### Issue: "No module named 'openpyxl'"

**Fix:**
```batch
pip install openpyxl --break-system-packages
```

### Issue: "Sheet 'Raw' not found"

**Fix:**
1. Open Excel file and check sheet names
2. Update `sheet` parameter in script (line 83)

### Issue: "[WARN] Dropped many rows"

**Causes:**
- Date column has text values (e.g., "N/A", "TBD")
- Demand values have errors (e.g., "#DIV/0!", "#N/A")
- Column mapping is wrong

**Fix:**
1. Check Excel file data quality
2. Verify column names are correct
3. Clean up source data in Excel if needed

### Issue: Canonical CSV has wrong column name

**If you see `price` instead of `demand_index`:**

The script auto-detects the column name based on the series name. Make sure your series contains "demand" or "proxy" in the name.

Edit `make_canonical_copper_demand.py` line 26-27:
```python
if "demand" in series_lower or "proxy" in series_lower:
    value_col = "demand_index"
```

---

## Integration with Overlay

After creating the canonical file, update your overlay config:

### Option 1: Already Correct (Default)

If you used the default paths, `chinese_demand.yaml` should already point to:
```yaml
data:
  demand_proxy:
    filepath: "Data/copper/fundamentals/canonical/chinese_demand_proxy.canonical.csv"
```

### Option 2: Update Config

If you need to change the path, edit `Config\copper\chinese_demand.yaml` line 53.

---

## Manual Conversion (Alternative)

If you prefer to convert manually:

1. Open `china_demand_values.xlsx`
2. Copy the Date and Demand columns
3. Create new CSV with headers: `date,demand_index`
4. Paste data
5. Save as: `chinese_demand_proxy.canonical.csv`

---

## Example: Checking Your Conversion

```batch
REM After running conversion, check the file:
head Data\copper\fundamentals\canonical\chinese_demand_proxy.canonical.csv
```

Expected output:
```
date,demand_index
2012-04-30,7.4
2012-05-31,7.7
2012-06-30,5.9
2012-07-31,7.0
...
```

If you see this format, you're good to go! ✅

---

## Next Steps

1. ✅ Run `run_make_canonical_copper_demand.bat`
2. ✅ Verify output looks correct
3. ✅ Run `run_chinese_demand.bat` to apply overlay
4. ✅ Check that overlay build succeeds

---

## File Locations Summary

| File | Location |
|------|----------|
| **Input:** Excel file | `C:\Code\Metals\Data\copper\fundamentals\china_demand_values.xlsx` |
| **Script:** Python | `C:\Code\Metals\tools\make_canonical_copper_demand.py` |
| **Script:** Batch | `C:\Code\Metals\run_make_canonical_copper_demand.bat` |
| **Output:** Canonical CSV | `C:\Code\Metals\Data\copper\fundamentals\canonical\chinese_demand_proxy.canonical.csv` |
| **Config:** YAML | `C:\Code\Metals\Config\copper\chinese_demand.yaml` |

---

**Ready to convert? Run `run_make_canonical_copper_demand.bat`** 🚀
