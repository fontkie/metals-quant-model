# src/load_data.py
import argparse
import sqlite3
import pandas as pd
from pathlib import Path

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True, help="Path to Excel (e.g., Copper/pricing_values.xlsx)")
    ap.add_argument("--db", required=True, help="Path to SQLite DB (e.g., Copper/quant.db)")
    ap.add_argument("--sheet", default="Raw", help="Sheet name containing prices (default: Raw)")
    ap.add_argument("--date_col", default="Date", help="Date column name (default: Date)")
    ap.add_argument("--mode", choices=["replace","append"], default="replace",
                    help="Write mode for prices table (default: replace)")
    return ap.parse_args()

def main():
    args = parse_args()
    xlsx_path = Path(args.xlsx)
    if not xlsx_path.exists():
        raise FileNotFoundError(f"Excel not found: {xlsx_path}")

    # 1) Read Excel
    df = pd.read_excel(xlsx_path, sheet_name=args.sheet)
    if args.date_col not in df.columns:
        raise ValueError(f"Expected date column '{args.date_col}' in sheet '{args.sheet}'")

    # 2) Tidy: ensure datetime + sort + melt to long (date, symbol, price)
    df[args.date_col] = pd.to_datetime(df[args.date_col])
    df = df.sort_values(args.date_col)
    value_cols = [c for c in df.columns if c != args.date_col]
    long_df = df.melt(id_vars=[args.date_col], value_vars=value_cols,
                      var_name="symbol", value_name="price").dropna(subset=["price"])

    long_df = long_df.rename(columns={args.date_col: "date"})
    # Optional: enforce types
    long_df["symbol"] = long_df["symbol"].astype(str)

    # 3) Write to DB
    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    # Always write to a staging table first (safer)
    cur.execute("DROP TABLE IF EXISTS _stage_prices;")
    conn.commit()
    long_df.to_sql("_stage_prices", conn, if_exists="replace", index=False)

    if args.mode == "replace":
        # Drop old tables so nothing lingers
        for tbl in ["prices_close", "prices", "signals"]:
            cur.execute(f"DROP TABLE IF EXISTS {tbl};")
        # Recreate prices fresh from staging
        cur.execute("CREATE TABLE prices AS SELECT * FROM _stage_prices;")
        cur.execute("DROP TABLE _stage_prices;")
        conn.commit()
        print("Loaded prices with REPLACE mode: rebuilt 'prices' table.")
    else:
        # Append staging into existing prices (create if not exists)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS prices(
                date TEXT,
                symbol TEXT,
                price REAL
            );
        """)
        cur.execute("INSERT INTO prices SELECT * FROM _stage_prices;")
        cur.execute("DROP TABLE _stage_prices;")
        conn.commit()
        print("Loaded prices with APPEND mode: appended into 'prices' table.")

    conn.close()

if __name__ == "__main__":
    main()
