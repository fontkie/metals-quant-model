import argparse, sqlite3
from pathlib import Path
import pandas as pd
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--db", required=True)
parser.add_argument("--outdir", required=True)
args = parser.parse_args()

Path(args.outdir).mkdir(parents=True, exist_ok=True)

con = sqlite3.connect(args.db)
px = pd.read_sql_query("SELECT dt, symbol, px_settle FROM prices", con, parse_dates=["dt"])
con.close()

# Pivot to wide, compute simple signals, then melt back
wide = px.pivot(index="dt", columns="symbol", values="px_settle").sort_index()

def mom(series, lb=20):
    return series.pct_change(lb)

def hook(series, fast=5, slow=20):
    f = series.pct_change(fast)
    s = series.pct_change(slow)
    return f - s

signals = {}
for col in wide.columns:
    s = wide[col]
    signals[(col, "mom_20")] = mom(s, 20)
    signals[(col, "hook_5_20")] = hook(s, 5, 20)

# Build tidy frame
out = []
for (sym, name), ser in signals.items():
    tmp = ser.rename("value").to_frame()
    tmp["symbol"] = sym
    tmp["signal"] = name
    out.append(tmp.reset_index())

sig = pd.concat(out, ignore_index=True).dropna()
sig = sig.sort_values(["dt", "symbol", "signal"])

# Export
out_path = Path(args.outdir) / "signals_export.csv"
sig.to_csv(out_path, index=False)
print(f"Wrote {len(sig):,} signal rows → {out_path}")
