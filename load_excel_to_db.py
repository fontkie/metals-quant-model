# load_excel_to_db.py
# Reads wide Excel (Date + columns) -> writes SQLite DB (prices_close)

import os, sys, sqlite3
import pandas as pd

TARGET_DIR  = r"C:\Code\Metals\Copper"   # folder containing Excel
EXCEL_NAME  = "pricing_values.xlsx"      # <-- your actual file name
DB_NAME     = "quant.db"
DATE_IS_DAYFIRST = True

if len(sys.argv) >= 2:
    TARGET_DIR = sys.argv[1]

EXCEL_PATH = os.path.join(TARGET_DIR, EXCEL_NAME)
DB_PATH    = os.path.join(TARGET_DIR, DB_NAME)

def read_wide_prices(path: str) -> pd.DataFrame:
    print(f"Reading Excel: {path}")
    df = pd.read_excel(
        path,
        engine="openpyxl",
        na_values=["#N/A", "#N/A N/A", "N/A", "NA", ""]
    )
    date_col = next((c for c in df.columns if str(c).strip().lower() == "date"), None)
    if not date_col:
        raise ValueError("Couldn't find a 'Date' column.")

    df[date_col] = pd.to_datetime(df[date_col], dayfirst=DATE_IS_DAYFIRST, errors="coerce")
    df = df.dropna(subset=[date_col])

    value_cols = [c for c in df.columns if c != date_col]
    for c in value_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    long_df = df.melt(id_vars=[date_col], value_vars=value_cols,
                      var_name="asset", value_name="close").dropna(subset=["close"])
    long_df = long_df.rename(columns={date_col: "date"})
    long_df["date"]  = long_df["date"].dt.strftime("%Y-%m-%d")
    long_df["asset"] = long_df["asset"].astype(str).str.strip().str.lower()
    print(f"Rows after melt: {len(long_df):,}")
    return long_df[["date", "asset", "close"]]

def write_sqlite(df: pd.DataFrame, db_path: str):
    print(f"Writing SQLite DB: {db_path}")
    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prices_close (
                date  TEXT NOT NULL,
                asset TEXT NOT NULL,
                close REAL,
                PRIMARY KEY (date, asset)
            )
        """)
        conn.execute("DELETE FROM prices_close;")
        df.to_sql("prices_close", conn, if_exists="append", index=False)
    conn.close()
    print("Done writing prices_close.")

def main():
    print("=== Excel -> SQLite loader starting ===")
    if not os.path.exists(EXCEL_PATH):
        raise FileNotFoundError(f"Excel not found: {EXCEL_PATH}")
    df = read_wide_prices(EXCEL_PATH)
    write_sqlite(df, DB_PATH)
    print("=== All done ===")

if __name__ == "__main__":
    main()
