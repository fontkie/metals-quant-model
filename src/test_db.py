# src/test_db.py
import argparse, sqlite3, sys, pandas as pd

p = argparse.ArgumentParser()
p.add_argument("--db", required=True)
p.add_argument("--prices-view", default="prices_long")
p.add_argument("--signals-table", default="signals")
a = p.parse_args()

con = sqlite3.connect(a.db)

# --- Check prices view ---
try:
    dfp = pd.read_sql(f"SELECT * FROM {a.prices_view} LIMIT 5", con)
except Exception as e:
    print(f"[ERR] Could not read {a.prices_view}: {e}")
    sys.exit(1)

expected_prices = {"date", "symbol", "price"}
if not expected_prices.issubset({c.lower() for c in dfp.columns}):
    print("[ERR] prices_long check failed: prices_long missing standard columns.")
    print("     Found columns:", list(dfp.columns))
    sys.exit(1)

# --- Check signals table (detect date col name) ---
# Get column names
cols = [r[1] for r in con.execute(f"PRAGMA table_info({a.signals_table})").fetchall()]
if not cols:
    print(f"[ERR] Could not read {a.signals_table}: table not found.")
    sys.exit(1)

lower = {c.lower(): c for c in cols}
date_col = lower.get("dt") or lower.get("date")
if not date_col:
    print(f"[ERR] {a.signals_table} missing a date column named 'dt' or 'date'. Found: {cols}")
    sys.exit(1)

try:
    dfs = pd.read_sql(
        f'SELECT COUNT(*) AS n, MIN("{date_col}") AS dt_min, MAX("{date_col}") AS dt_max FROM {a.signals_table}',
        con,
    )
    n = int(dfs["n"].iloc[0])
    print(f"[OK] signals: rows≈{n:,} | {dfs['dt_min'].iloc[0]} → {dfs['dt_max'].iloc[0]}")
except Exception as e:
    print(f"[ERR] Could not scan {a.signals_table}: {e}")
    sys.exit(1)

print("[OK] prices_long and signals look sane.")
