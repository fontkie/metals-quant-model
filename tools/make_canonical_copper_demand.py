"""
Make Canonical - Copper Demand Data
Converts copper demand data from Excel to canonical CSV format.

Author: Kieran
Date: November 18, 2025
"""

from pathlib import Path
import pandas as pd


def make_canonical_from_raw(df, date_col, series_col, out_csv, max_drop_frac=0.05):
    """
    Convert raw Excel data to canonical CSV format.

    For demand data, auto-detects series type from column name:
    - 'demand' or 'balance' or 'proxy' → column named 'demand_index'
    - 'impliedvol' or 'iv' → column named 'iv'
    - 'volume' → column named 'volume'
    - 'stocks' → column named 'stocks'
    - everything else → column named 'price'
    
    Args:
        df: DataFrame with raw data
        date_col: Name of date column
        series_col: Name of series column
        out_csv: Output path for canonical CSV
        max_drop_frac: Max fraction of rows that can be dropped (warning threshold)
    """
    cols = {c.lower(): c for c in df.columns}
    dcol = cols.get(date_col.lower(), date_col)
    scol = cols.get(series_col.lower(), series_col)

    # Determine output column name based on series type
    series_lower = series_col.lower()
    if "demand" in series_lower or "balance" in series_lower or "proxy" in series_lower:
        value_col = "demand_index"
    elif "impliedvol" in series_lower or series_lower.endswith("_iv"):
        value_col = "iv"
    elif "volume" in series_lower:
        value_col = "volume"
    elif "stocks" in series_lower:
        value_col = "stocks"
    else:
        value_col = "price"

    # Create output dataframe with canonical column names
    out = df[[dcol, scol]].rename(columns={dcol: "date", scol: value_col})
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out[value_col] = pd.to_numeric(out[value_col], errors="coerce")

    # Clean data
    before = len(out)
    out = out.dropna(subset=["date", value_col])
    out = out.sort_values("date").drop_duplicates(subset=["date"])
    after = len(out)
    drop_frac = 0 if before == 0 else (before - after) / before

    # Create output directory if needed
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    # Warn if too many rows dropped
    if drop_frac > max_drop_frac:
        print(
            f"[WARN] Dropped {before-after} rows ({drop_frac:.1%}) for {series_col}. "
            f"Check mapping/units."
        )

    # Write canonical CSV
    out.to_csv(out_csv, index=False)
    print(f"[OK] {series_col}: wrote {after} rows -> {out_csv} (column: '{value_col}')")


def excel_to_canonical(excel_path, sheet, date_col, fields, out_dir):
    """
    Convert Excel file with multiple series to canonical CSV files.
    
    Args:
        excel_path: Path to Excel file
        sheet: Sheet name to read
        date_col: Name of date column
        fields: List of series column names to convert
        out_dir: Output directory for canonical CSVs
    """
    out_dir = Path(out_dir)
    
    # Read Excel with NA handling
    df = pd.read_excel(
        excel_path,
        sheet_name=sheet,
        na_values=["#N/A", "N/A", "#N/A N/A", "#VALUE!", "NA", "-", ""],
    )
    
    print(f"\n[INFO] Loaded sheet '{sheet}' with {len(df)} rows")
    print(f"[INFO] Available columns: {list(df.columns)}")
    print()
    
    # Convert each field to canonical format
    for field in fields:
        out_csv = out_dir / f"{field}.canonical.csv"
        make_canonical_from_raw(df, date_col, field, out_csv, max_drop_frac=0.20)


if __name__ == "__main__":
    print("="*80)
    print("CONVERTING COPPER DEMAND DATA TO CANONICAL FORMAT")
    print("="*80)
    print()
    
    # Convert copper demand/balance data
    excel_to_canonical(
        excel_path=r"C:\Code\Metals\Data\copper\fundamentals\copper_demand.xlsx",
        sheet="Raw",  # Adjust if your sheet has a different name
        date_col="Date",
        fields=[
            "copper_demand",  # This will create copper_demand_balance.canonical.csv
            # Add other demand-related fields here if you have them:
            # "copper_demand_proxy",
            # "copper_supply_balance",
            # "chinese_pmi",
        ],
        out_dir=r"C:\Code\Metals\Data\copper\fundamentals\canonical",
    )
    
    print()
    print("="*80)
    print("CONVERSION COMPLETE")
    print("="*80)
    print()
    print("Output location: C:\\Code\\Metals\\Data\\copper\\fundamentals\\canonical")
    print()
    print("Files created:")
    print("  - copper_demand.canonical.csv")
    print()
    print("Next steps:")
    print("  1. Verify the canonical CSV looks correct")
    print("  2. Update copper_demand.yaml filepath to point to copper_demand_balance.canonical.csv")
    print("  3. Run: scripts\\run_copper_demand.bat")