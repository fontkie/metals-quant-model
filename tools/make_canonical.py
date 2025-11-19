from pathlib import Path
import pandas as pd


def make_canonical_from_raw(df, date_col, series_col, out_csv, max_drop_frac=0.05):
    """
    Convert raw Excel data to canonical CSV format.

    Auto-detects series type from column name:
    - 'impliedvol' or 'iv' → column named 'iv'
    - 'volume' → column named 'volume'
    - everything else → column named 'price'
    """
    cols = {c.lower(): c for c in df.columns}
    dcol = cols.get(date_col.lower(), date_col)
    scol = cols.get(series_col.lower(), series_col)

    # Determine output column name based on series type
    series_lower = series_col.lower()
    if "impliedvol" in series_lower or series_lower.endswith("_iv"):
        value_col = "iv"
    elif "volume" in series_lower:
        value_col = "volume"
    elif "stocks" in series_lower:
        value_col = "stocks"
    else:
        value_col = "price"

    out = df[[dcol, scol]].rename(columns={dcol: "date", scol: value_col})
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out[value_col] = pd.to_numeric(out[value_col], errors="coerce")

    before = len(out)
    out = out.dropna(subset=["date", value_col])
    out = out.sort_values("date").drop_duplicates(subset=["date"])
    after = len(out)
    drop_frac = 0 if before == 0 else (before - after) / before

    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    if drop_frac > max_drop_frac:
        print(
            f"[WARN] Dropped {before-after} rows ({drop_frac:.1%}) for {series_col}. Check mapping/units."
        )

    out.to_csv(out_csv, index=False)
    print(f"[OK] {series_col}: wrote {after} rows -> {out_csv} (column: '{value_col}')")


def excel_to_canonical(excel_path, sheet, date_col, fields, out_dir):
    out_dir = Path(out_dir)
    df = pd.read_excel(
        excel_path,
        sheet_name=sheet,
        na_values=["#N/A", "N/A", "#N/A N/A", "#VALUE!", "NA", "-", ""],
    )
    for field in fields:
        out_csv = out_dir / f"{field}.canonical.csv"
        make_canonical_from_raw(df, date_col, field, out_csv, max_drop_frac=0.20)


if __name__ == "__main__":
    excel_to_canonical(
        excel_path=r"C:\Code\Metals\Data\copper\pricing\pricing_values.xlsx",
        sheet="Raw",
        date_col="Date",
        fields=[
            "copper_lme_3mo",
            "copper_lme_cash_3mo",
            "copper_lme_cash",
            "copper_lme_3mo_fut",
            "copper_lme_12mo_fut",
            "copper_lme_24mo_fut",
            "copper_lme_3mo_volume",
            "copper_lme_1mo_impliedvol",
            "copper_lme_3mo_impliedvol",
            "copper_lme_total_stocks",
            "copper_lme_cancelled_stocks",
        ],
        out_dir=r"Data\copper\pricing\canonical",
    )
