# src/load_data.py
import argparse
from pathlib import Path
import pandas as pd
from db import get_conn

def find_raw_sheet(xlsx: str) -> str:
    xl = pd.ExcelFile(xlsx)
    for name in xl.sheet_names:
        if str(name).strip().lower() == "raw":
            return name
    return xl.sheet_names[0]

def find_date_column(df: pd.DataFrame) -> str:
    lower = {c: str(c).strip().lower() for c in df.columns}
    for orig, low in lower.items():
        if low in {"date", "dt"}:
            return orig
    for c in df.columns:
        parsed = pd.to_datetime(df[c], errors="coerce")
        if parsed.notna().sum() >= max(5, int(0.5 * len(parsed))):
            return c
    raise ValueError("Could not find a date column. Put dates in the first column or name it 'Date'/'dt'.")

def normalise(name: str) -> str:
    s = str(name).strip().lower().replace("\\", "_").replace("/", "_").replace(" ", "_").replace("-", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--xlsx", required=True)
    p.add_argument("--db", required=True)
    args = p.parse_args()

    xlsx = Path(args.xlsx)
    assert xlsx.exists(), f"Missing Excel: {xlsx}"

    sheet = find_raw_sheet(str(xlsx))
    df = pd.read_excel(xlsx, sheet_name=sheet, header=0)
    df = df.dropna(how="all").dropna(axis=1, how="all")

    date_col = find_date_column(df)
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df[df[date_col].notna()].copy()
    df[date_col] = df[date_col].dt.strftime("%Y-%m-%d")

    longs = []
    for col in df.columns:
        if col == date_col:
            continue
        ser = df[[date_col, col]].copy()
        ser[col] = pd.to_numeric(ser[col], errors="coerce")
        ser = ser.dropna(subset=[col])
        if ser.empty:
            continue
        ser.columns = ["dt", "px_settle"]
        ser["symbol"] = normalise(col)
        longs.append(ser[["dt", "symbol", "px_settle"]])

    if not longs:
        raise ValueError("No usable price columns found. Check your 'Raw' sheet has numeric series.")

    out = pd.concat(longs, ignore_index=True)

    con = get_conn(args.db)
    with con:
        out.to_sql("prices", con, if_exists="replace", index=False)

    print(f"Loaded {len(out):,} rows into prices from sheet '{sheet}'.")

if __name__ == "__main__":
    main()
