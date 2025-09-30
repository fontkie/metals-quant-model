import sqlite3, sys, pandas as pd
from datetime import date

DB, TABLE = sys.argv[1], sys.argv[2]  # e.g. db/copper/quant.db prices_std

with sqlite3.connect(DB) as con:
    df = pd.read_sql(f"SELECT * FROM {TABLE} ORDER BY 1", con, parse_dates=["date"])

assert {"date","px_3m","px_cash"}.issubset(df.columns), "Standard cols missing."
assert df["date"].is_monotonic_increasing, "Dates not sorted."
assert df["date"].min() <= pd.Timestamp("2008-01-01"), "History does not go back to 2008."
assert not df["date"].duplicated().any(), "Duplicate dates exist."
print(f"[OK] {TABLE}: {df['date'].min().date()} → {df['date'].max().date()} | rows={len(df):,}")
print("[OK] Preflight passed.")
