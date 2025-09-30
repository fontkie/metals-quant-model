# load_data.py (hardened: single-sheet read + date dedupe for SQLite)
import argparse
import sqlite3
from pathlib import Path
import pandas as pd
import numpy as np

DATE_CANDS = ["date", "Date", "DATE", "trade_date", "TradeDate", "timestamp", "ts"]

def detect_date_col(cols):
    # Case-insensitive match over trimmed names
    name_map = {c: c.strip() for c in cols}
    cols_trim = [c.strip() for c in cols]
    lower_to_orig = {}
    for orig, trimmed in name_map.items():
        lower_to_orig.setdefault(trimmed.lower(), orig)
    for cand in DATE_CANDS:
        if cand.lower() in lower_to_orig:
            return lower_to_orig[cand.lower()]
    # Fallback common names
    for c in cols:
        if c.strip().lower().startswith("date"):
            return c
    raise KeyError(f"No date-like column found. Looked for {DATE_CANDS} or columns starting with 'date'.")

def parse_dates(s: pd.Series) -> pd.Series:
    d = pd.to_datetime(s, errors="coerce")
    if d.isna().all() and pd.api.types.is_numeric_dtype(s):
        ser = s.astype("float64")
        if ser.median() > 1e11:   # UNIX ms
            d = pd.to_datetime(ser, unit="ms", errors="coerce")
        elif ser.median() > 1e9:  # UNIX s
            d = pd.to_datetime(ser, unit="s", errors="coerce")
        else:                     # Excel serial
            origin = pd.Timestamp("1899-12-30")
            d = origin + pd.to_timedelta(ser, unit="D")
    return pd.to_datetime(d)

def read_single_sheet(excel_path: Path, sheet: str | None) -> tuple[pd.DataFrame, str]:
    if sheet:
        df = pd.read_excel(excel_path, sheet_name=sheet)
        used_sheet = sheet
    else:
        # Robust way: inspect workbook, take first sheet name
        xls = pd.ExcelFile(excel_path)
        if not xls.sheet_names:
            raise ValueError("No sheets found in Excel workbook.")
        used_sheet = xls.sheet_names[0]
        df = pd.read_excel(xls, sheet_name=used_sheet)
    return df, used_sheet

def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    # Trim column whitespace
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    # Find a date-like column
    date_col = detect_date_col(df.columns)

    # Create canonical 'date'
    df["date"] = parse_dates(df[date_col])

    # Drop any other column that SQLite would treat as the same name as 'date' (case-insensitive)
    to_drop = [c for c in df.columns if c != "date" and c.strip().lower() == "date"]
    if date_col != "date" and date_col in df.columns and date_col in to_drop:
        # Ensure original source date col is dropped
        pass
    # Drop duplicates of 'date' (e.g., 'Date', 'DATE')
    df.drop(columns=to_drop, inplace=True, errors="ignore")

    # Remove any generic 'index' column brought in from CSV/Excel exports
    if "index" in df.columns:
        df.drop(columns=["index"], inplace=True, errors="ignore")

    # Final clean
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return df

def append_update(con, df: pd.DataFrame, table: str):
    # Merge with existing (if present)
    try:
        existing = pd.read_sql(f"SELECT * FROM {table}", con)
        if not existing.empty:
            # Normalise existing
            if "date" not in existing.columns:
                # Try to locate a date-like column and normalise
                existing.columns = [c.strip() for c in existing.columns]
                ex_date_col = detect_date_col(existing.columns)
                existing["date"] = parse_dates(existing[ex_date_col])
                # drop case-insensitive duplicates of 'date'
                dup = [c for c in existing.columns if c != "date" and c.strip().lower() == "date"]
                existing.drop(columns=dup, inplace=True, errors="ignore")
            else:
                existing["date"] = parse_dates(existing["date"])
            merged = pd.concat([existing, df], ignore_index=True, sort=False)
        else:
            merged = df.copy()
    except Exception:
        merged = df.copy()

    # Deduplicate by date (keep last), sort
    merged = merged.dropna(subset=["date"])
    merged = merged.drop_duplicates(subset=["date"], keep="last")
    merged = merged.sort_values("date").reset_index(drop=True)

    # Make sure no case-insensitive duplicate of 'date' remains
    merged = merged.loc[:, ~merged.columns.str.lower().duplicated()]

    # Write
    merged.to_sql(table, con, if_exists="replace", index=False)
    return merged

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True, help="Path to Excel (e.g. .\\Copper\\pricing_values.xlsx)")
    ap.add_argument("--db", required=True, help="Path to SQLite DB (e.g. .\\Copper\\quant.db)")
    ap.add_argument("--table", default="prices", help="Target table name (default: prices)")
    ap.add_argument("--sheet", default=None, help="Excel sheet name (default: first sheet)")
    ap.add_argument("--mode", default="append_update", choices=["append_update","replace"], help="Write mode")
    args = ap.parse_args()

    excel_path = Path(args.excel).resolve()
    db_path = Path(args.db).resolve()

    df_raw, used_sheet = read_single_sheet(excel_path, args.sheet)
    df = clean_dataframe(df_raw)

    with sqlite3.connect(db_path) as con:
        if args.mode == "replace":
            df.to_sql(args.table, con, if_exists="replace", index=False)
            final = df
        else:
            final = append_update(con, df, args.table)

    print(f"[OK] Loaded sheet: '{used_sheet}'")
    print(f"[OK] Wrote table '{args.table}' → {db_path}")
    print(f"[OK] Rows: {len(final):,} | Range: {final['date'].min().date()} → {final['date'].max().date()}")

if __name__ == "__main__":
    main()
