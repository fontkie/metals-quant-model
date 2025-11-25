# VolPulse (Copper)

A compact volatility pulse used to gate entries, size risk, and tighten stops across sleeves.

## Quickstart
```python
from vol.vol_pulse import compute_vol_pulse
import pandas as pd
df = pd.read_csv("copper_prices.csv", parse_dates=["Date"]).sort_values("Date")
pulse = compute_vol_pulse(df, config_path="vol/vol_pulse.yaml")
pulse.to_csv("copper_vol_pulse.csv", index=False)
```
