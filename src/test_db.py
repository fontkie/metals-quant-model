# test_db.py
# -----------
# Quick sanity checks for your DB:
#   - prices_std view exists and is well-formed
#   - signals table exists (after you run build_signals)
#
# Usage:
#   python src\test_db.py --db .\Copper\quant.db
#
import argparse
import sqlite3
from pathlib import Path
import pandas as pd

def check_view(con, view: str):
    try:
        df = pd.read_sql(f"SELECT * FROM {view} ORDER BY date LIMIT 5", con, parse_dates=["date"])
        assert {"date","px_3m","px_cash"}.issubset(df.columns), f"{view} missing standard columns."
        rng = pd.read_sql(f"SELECT MIN(date) AS min_d, MAX(date) AS max_d, COUNT(*) AS n FROM {view}", con)
        print(f"[OK] {view}: rows≈{int(rng['n'][0]):,} | {rng['min_d'][0]} → {rng['max_d'][0]}")
    except Exception as e:
        print(f"[ERR] {view} check failed: {e}")

def check_signals(con, table: str):
    try:
        df = pd.read_sql(f"SELECT * FROM {table} ORDER BY date DESC LIMIT 5", con, parse_dates=["date"])
        assert "trend_signal" in df.columns and "hook_signal" in df.columns, "signals missing required columns."
        rng = pd.read_sql(f"SELECT MIN(date) AS min_d, MAX(date) AS max_d, COUNT(*) AS n FROM {table}", con)
        print(f"[OK] {table}: rows≈{int(rng['n'][0]):,} | {rng['min_d'][0]} → {rng['max_d'][0]}")
    except Exception as e:
        print(f"[ERR] {table} check failed: {e}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to SQLite DB (e.g. .\\Copper\\quant.db)")
    ap.add_argument("--prices-view", default="prices_std")
    ap.add_argument("--signals-table", default="signals")
    args = ap.parse_args()

    db_path = Path(args.db).resolve()
    with sqlite3.connect(db_path) as con:
        check_view(con, args.prices_view)
        check_signals(con, args.signals_table)

if __name__ == "__main__":
    main()
