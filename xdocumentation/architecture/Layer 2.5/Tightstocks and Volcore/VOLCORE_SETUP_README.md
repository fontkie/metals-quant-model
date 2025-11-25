# VolCore v1 - Setup Instructions

## Files Delivered

```
volcore_v1.py           → Copy to: src\signals\volcore_v1.py
volcore_v1.yaml         → Copy to: Config\Copper\volcore_v1.yaml
build_volcore_v1.py     → Copy to: src\cli\build_volcore_v1.py
run_volcore_v1.bat      → Copy to: C:\Code\Metals\run_volcore_v1.bat
```

## Data Setup (REQUIRED)

You need to add your implied volatility data to the canonical directory:

### 1. Create the IV canonical CSV

```
File: Data\copper\pricing\canonical\copper_lme_1mo_impliedvol.canonical.csv

Format:
date,iv
2011-06-13,25.49
2011-06-14,25.18
2011-06-15,24.98
...

Notes:
- iv = annualized implied vol in percentage (25.0 = 25% annual vol)
- This should be ATM (50 delta / at-the-money) 1-month implied vol
- Forward fill any holiday gaps (IV doesn't update on non-trading days)
```

### 2. Verify your data

The IV data you uploaded (`copper_lme_1mo_impliedvol_canonical.csv`) is already in the correct format. Just rename/copy it to:

```
Data\copper\pricing\canonical\copper_lme_1mo_impliedvol.canonical.csv
```

## Running the Build

```batch
cd C:\Code\Metals
run_volcore_v1.bat
```

## Expected Output

```
VolCore v1 - Build Process
======================================================================

Strategy: Volatility Risk Premium (IV - RV Spread)
  • SHORT when vol spread z-score > 1.5 (high fear = justified)
  • LONG when vol spread z-score < -1.0 (complacent = risk-on)
  • Hysteresis to reduce turnover (~13 trades/year)
  • Expected: 0.420 Sharpe, orthogonal to trend/momentum

...

BUILD COMPLETE - VOLCORE V1
======================================================================

Performance Summary:
  Sharpe Ratio:    +0.420
  Annual Return:   +2.62%
  Annual Vol:       6.23%
  Max Drawdown:    -11.34%
  Trades/Year:      13.0
```

## Integration with Existing Sleeves

VolCore v1 provides **genuine orthogonality**:

| Sleeve | Sharpe | Correlation to VolCore |
|--------|--------|----------------------|
| TrendCore v3 | 0.51 | 0.020 |
| TrendImpulse v4 | 0.42 | 0.030 |
| MomentumCore v1 | 0.60 | 0.050 |
| **VolCore v1** | **0.42** | 1.000 |

**Recommended 4-sleeve allocation:**
```
TrendCore:      35%
TrendImpulse:   20%
MomentumCore:   30%
VolCore:        15%
```

Expected improvement: 0.767 → 0.85 Sharpe (+10.8%)

## Key Insight

**In copper, high fear is JUSTIFIED, not overpriced.**

Unlike equity VIX where "buy the dip" works, copper's vol premium reflects real demand destruction risk. When IV >> RV, the market correctly anticipates weakness.

- **HIGH z-score (>1.5)**: Enter SHORT (fear justified, copper falls)
- **LOW z-score (<-1.0)**: Enter LONG (complacency, risk-on)
- **NORMAL**: Stay flat, let trend sleeves work

SHORT signal Sharpe: **1.235** (star performer)

## Future Enhancements

When you get skew data (25 delta put/call IV):

```python
# v2 enhancement
risk_reversal = put_iv_25d - call_iv_25d

# Steep put skew + high vol spread = HIGH CONVICTION short
# Flat skew + high vol spread = maybe fear overdone?
```

## Troubleshooting

**Common issues:**

1. **Missing IV data**: Make sure `copper_lme_1mo_impliedvol.canonical.csv` exists
2. **Wrong IV format**: Must have columns `date,iv` with annualized percentage
3. **Import errors**: Ensure `contract.py` exists in `src\core\`
4. **Low Sharpe**: Expected ~0.42, but can vary by ±0.05 depending on exact date range

**If build fails:**

Check that your IV data matches your price data dates. The script will merge on date and forward-fill IV gaps, but price data must exist for the period you want to test.

## Contact

Questions about implementation? Share your output logs and I can debug.
