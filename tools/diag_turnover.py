import argparse, os, pandas as pd, numpy as np
ap = argparse.ArgumentParser()
ap.add_argument("--pnl", required=True)
a = ap.parse_args()
p = a.pnl
if not os.path.exists(p): raise SystemExit(f"Missing file: {p}")
df = pd.read_csv(p, parse_dates=[0]); df.columns = [c.lower() for c in df.columns]
df = df.set_index(df.columns[0]).sort_index()
idx = df.index
exec_days = (idx.weekday == 0) | (idx.weekday == 2)  # Mon/Wed execution (positions change next day)
turn = (df["turnover"] > 1e-12).fillna(False)
non_exec_turn = (turn & ~exec_days).mean()
exec_turn     = (turn &  exec_days).mean()
print("Non-exec turnover days (%):", round(100*non_exec_turn, 3))
print("Exec-day  turnover days (%):", round(100*exec_turn, 3))
print("Sample:", idx.min().date(), "->", idx.max().date(), "N=", len(idx))
