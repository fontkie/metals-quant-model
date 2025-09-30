# build_signals.py
# -----------------
# Standardises input via a SQL VIEW 'prices_std' (date, px_3m, px_cash),
# builds daily Trend & Hook signals that trade next day (shift(1)),
# and writes outputs into outputs/<Metal>/signals_export.csv plus a 'signals' table in the DB.
#
# Usage (from project root):
#   python src\build_signals.py --db .\Copper\quant.db --source-table prices
# Optional:
#   --mom-lb 60 --hook-enter 1.5 --hook-exit 0.75 --gate-abs-curve-z 1.0
#   --outdir .\outputs    (default auto: <project_root>\outputs\<Metal>)
#
import argparse
import sqlite3
from pathlib import Path
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------- Alias candidates (keeps things robust to small naming drifts) ----------
DATE_CANDS = ["date", "Date", "DATE", "trade_date", "timestamp", "ts"]
PX3M_CANDS = ["copper_lme_3mo", "copper_lme_3m", "lme_cu_3m", "copper_comex_3mo"]
PXCASH_CANDS = ["copper_lme_cash_3mo", "copper_lme_cash", "lme_cu_cash", "copper_cash"]

# ---------- Helpers ----------
def detect_col(existing_cols, candidates, friendly):
    lower_map = {c.lower(): c for c in existing_cols}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    raise KeyError(f"Could not find a column for {friendly}. Looked for: {candidates}. "
                   f"Available: {list(existing_cols)}")

def ensure_prices_std_view(con, source_table: str):
    """Create or replace prices_std(date, px_3m, px_cash) VIEW from source_table."""
    cols_df = pd.read_sql(f"PRAGMA table_info({source_table});", con)
    if cols_df.empty:
        raise ValueError(f"Source table '{source_table}' not found in DB.")
    cols = cols_df["name"].tolist()

    col_date = detect_col(cols, DATE_CANDS, "date")
    col_3m   = detect_col(cols, PX3M_CANDS, "3M price")
    col_cash = detect_col(cols, PXCASH_CANDS, "Cash price")

    sql = f"""
    DROP VIEW IF EXISTS prices_std;
    CREATE VIEW prices_std AS
    SELECT
      {col_date} AS date,
      {col_3m}   AS px_3m,
      {col_cash} AS px_cash
    FROM {source_table};
    """
    con.executescript(sql)
    return col_date, col_3m, col_cash

def read_prices_std(con):
    df = pd.read_sql("SELECT * FROM prices_std ORDER BY date", con)
    # Parse date robustly (strings, Excel serials, UNIX)
    d = pd.to_datetime(df["date"], errors="coerce")
    if d.isna().all():
        ser = pd.to_numeric(df["date"], errors="coerce")
        if ser.notna().any():
            if ser.median() > 1e11:      # UNIX ms
                d = pd.to_datetime(ser, unit="ms", errors="coerce")
            elif ser.median() > 1e9:     # UNIX s
                d = pd.to_datetime(ser, unit="s", errors="coerce")
            else:                        # Excel serial
                origin = pd.Timestamp("1899-12-30")
                d = origin + pd.to_timedelta(ser, unit="D")
    df["date"] = pd.to_datetime(d)
    df = df.dropna(subset=["date"]).sort_values("date")
    df["px_3m"] = pd.to_numeric(df["px_3m"], errors="coerce")
    df["px_cash"] = pd.to_numeric(df["px_cash"], errors="coerce")
    df = df.dropna(subset=["px_3m", "px_cash"])
    return df

def clamp_2008_indexed(df):
    df = df[df["date"] >= pd.Timestamp("2008-01-01")].copy()
    df = df.drop_duplicates(subset=["date"], keep="last")
    return df.set_index("date").sort_index()

def build_features(df_idx):
    out = pd.DataFrame(index=df_idx.index)
    out["px_3m"] = df_idx["px_3m"]
    out["px_cash"] = df_idx["px_cash"]
    out["curve_cash_minus_3m"] = out["px_cash"] - out["px_3m"]  # backwardation > 0
    win, minp = 120, 60
    ma = out["curve_cash_minus_3m"].rolling(win, min_periods=minp).mean()
    sd = out["curve_cash_minus_3m"].rolling(win, min_periods=minp).std()
    out["curve_z120"] = (out["curve_cash_minus_3m"] - ma) / sd
    return out

def trend_signal(feats, mom_lb=60, gate_abs_curve_z=1.0):
    log_mom = np.log(feats["px_3m"] / feats["px_3m"].shift(mom_lb))
    raw = np.sign(log_mom).replace(0, np.nan)
    gate = (feats["curve_z120"].abs() <= gate_abs_curve_z).astype(float)
    sig = (raw * gate).fillna(0.0)
    return sig.clip(-1, 1)

def hook_signal(feats, enter_thr=1.5, exit_thr=0.75):
    z = feats["curve_z120"]
    sig = pd.Series(0.0, index=z.index)
    sig[z >  enter_thr] = -1.0  # fade extreme backwardation
    sig[z < -enter_thr] = +1.0  # fade extreme contango
    # flatten when normalised
    sig = sig.where(z.abs() >= exit_thr, 0.0)
    return sig.clip(-1, 1)

def save_signals_to_db(con, out_df):
    out_df.reset_index().to_sql("signals", con, if_exists="replace", index=False)

def compute_default_outdir(db_path: Path, explicit_outdir: Path | None) -> Path:
    """
    Default: <project_root>\outputs\<Metal>\
    - project_root is parent of this file's folder (.. from src)
    - <Metal> = parent folder name of the DB (e.g., Copper if ...\Copper\quant.db)
    """
    if explicit_outdir:
        base = explicit_outdir
    else:
        project_root = Path(__file__).resolve().parent.parent  # ...\Metals
        base = project_root / "outputs"

    metal = db_path.parent.name or "default"
    outdir = base / metal
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir

def export_csv(outdir: Path, out_df: pd.DataFrame):
    csv_path = outdir / "signals_export.csv"
    out_df.reset_index().to_csv(csv_path, index=False)
    print(f"[OK] CSV exported → {csv_path}")

# ---------- Main ----------
def main():
    ap = argparse.ArgumentParser(description="Build daily signals from prices_std and export to outputs/<Metal>.")
    ap.add_argument("--db", required=True, help="Path to quant.db (e.g. .\\Copper\\quant.db)")
    ap.add_argument("--source-table", default="prices", help="Raw prices table to map into prices_std (default: prices)")
    ap.add_argument("--mom-lb", type=int, default=60, help="Trend lookback (days)")
    ap.add_argument("--gate-abs-curve-z", type=float, default=1.0, help="Trend gate: trade only if |curve_z| <= this")
    ap.add_argument("--hook-enter", type=float, default=1.5, help="Hook enter |z| threshold")
    ap.add_argument("--hook-exit", type=float, default=0.75, help="Hook exit |z| threshold")
    ap.add_argument("--outdir", type=str, default=None, help="Optional base output dir (default auto: outputs/<Metal>)")
    args = ap.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    outdir = compute_default_outdir(db_path, Path(args.outdir).resolve() if args.outdir else None)

    with sqlite3.connect(db_path) as con:
        # 1) Standardise inputs via a VIEW
        col_date, col_3m, col_cash = ensure_prices_std_view(con, args.source_table)
        print(f"[INFO] View prices_std ← {args.source_table} "
              f"(date:{col_date}, px_3m:{col_3m}, px_cash:{col_cash})")

        # 2) Read, clamp, feature-engineer
        df_raw = read_prices_std(con)
        print(f"[INFO] prices_std rows={len(df_raw):,} | range {df_raw['date'].min().date()} → {df_raw['date'].max().date()}")

        df = clamp_2008_indexed(df_raw)
        feats = build_features(df)

        # 3) Signals (raw) → trade next day
        sig_trend_raw = trend_signal(feats, mom_lb=args.mom_lb, gate_abs_curve_z=args.gate_abs_curve_z)
        sig_hook_raw  = hook_signal(feats, enter_thr=args.hook_enter, exit_thr=args.hook_exit)

        out = feats.copy()
        out["trend_signal"] = sig_trend_raw.shift(1).fillna(0.0)
        out["hook_signal"]  = sig_hook_raw.shift(1).fillna(0.0)
        out["ret_1d"]       = out["px_3m"].pct_change()
        out["position_trend"] = out["trend_signal"]
        out["position_hook"]  = out["hook_signal"]

        # Optional diagnostics
        for lb in (20, 60, 120):
            out[f"log_mom_{lb}d"] = np.log(out["px_3m"] / out["px_3m"].shift(lb))

        # 4) Persist
        save_signals_to_db(con, out)
        export_csv(outdir, out)

        start, end = out.index.min().date(), out.index.max().date()
        ft = out["position_trend"].ne(0).idxmax().date() if out["position_trend"].any() else "N/A"
        fh = out["position_hook"].ne(0).idxmax().date()  if out["position_hook"].any()  else "N/A"
        print(f"[OK] signals written to DB ({start} → {end})")
        print(f"[OK] First non-zero positions (Trend/Hook): {ft} / {fh}")
        print(f"[OK] Outputs folder: {outdir}")

if __name__ == "__main__":
    main()
