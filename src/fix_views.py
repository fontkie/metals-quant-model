# src/fix_views.py
import argparse
import sqlite3
import pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to SQLite DB (e.g., Copper/quant.db)")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    cur = con.cursor()

    # Recreate prices_long view to point at the new column names
    cur.execute("DROP VIEW IF EXISTS prices_long;")
    cur.execute("""
        CREATE VIEW prices_long AS
        SELECT date, symbol, price FROM prices
    """)
    con.commit()

    # Build prices_std (wide pivot)
    df = pd.read_sql_query("SELECT date, symbol, price FROM prices", con, parse_dates=["date"])
    df = df.sort_values("date").drop_duplicates(["date", "symbol"], keep="last")
    wide = df.pivot(index="date", columns="symbol", values="price").reset_index()

    # Make column names SQL-friendly
    wide.columns = [str(c).lower().replace(" ", "_").replace("-", "_") for c in wide.columns]

    wide.to_sql("prices_std", con, if_exists="replace", index=False)
    con.close()

    print("Created view: prices_long (date, symbol, price)")
    print(f"Created table: prices_std with columns: {list(wide.columns)}")

if __name__ == "__main__":
    main()
