import numpy as np
import pandas as pd
from pathlib import Path

TRADING_DAYS = 252

def read_table_auto(path, date_candidates=("dt","date","Date","datetime","DT")):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing: {p}")
    df = pd.read_csv(p) if p.suffix.lower() in (".csv",".txt") else pd.read_excel(p)
    for c in date_candidates:
        if c in df.columns:
            df["dt"] = pd.to_datetime(df[c]); break
    else:
        raise ValueError(f"No date col in {p}, columns={list(df.columns)}")
    return df.sort_values("dt").reset_index(drop=True)

def pick(df, candidates):
    for c in candidates:
        if c in df.columns: return c
    raise ValueError(f"None of {candidates} present. Columns={list(df.columns)}")

def ann_vol(x):
    return x.std(ddof=0) * np.sqrt(TRADING_DAYS)

def main():
    # Inputs (your existing sleeve outputs)
    hook_path   = Path("outputs/copper/pricing/daily_series.csv")
    stocks_path = Path("outputs/copper/stocks/daily_series.csv")
    out_dir = Path("outputs/copper/composite_ad_hoc"); out_dir.mkdir(parents=True, exist_ok=True)

    # Read sleeves
    hook_raw   = read_table_auto(hook_path)
    stocks_raw = read_table_auto(stocks_path)

    # Detect RETURN columns only (ignore positions/costs entirely)
    ret_hook_col = pick(hook_raw,  ["return_biweekly","ret_biweekly","return_weekly","ret_weekly","ret","return"])
    ret_stk_col  = pick(stocks_raw,["ret","return"])

    hook   = hook_raw.rename(columns={ret_hook_col:"ret_hook"})[["dt","ret_hook"]]
    stocks = stocks_raw.rename(columns={ret_stk_col:"ret_stocks"})[["dt","ret_stocks"]]

    # Align on dates (inner join)
    df = pd.merge(hook, stocks, on="dt", how="inner", validate="one_to_one").sort_values("dt").reset_index(drop=True)

    # Equal weights (0.5 / 0.5) on RETURNS
    df["ret_combo_raw"] = 0.5*df["ret_hook"] + 0.5*df["ret_stocks"]

    # === Single-scalar scaling to match OOS 10% vol ===
    OOS_START = pd.Timestamp("2018-01-01")
    oos_mask = df["dt"] >= OOS_START
    oos_vol = ann_vol(df.loc[oos_mask, "ret_combo_raw"])
    if oos_vol == 0 or np.isnan(oos_vol):
        raise ValueError("OOS vol is zero/NaN; check OOS data coverage.")
    scalar = 0.10 / oos_vol
    # (optional) cap like baseline if you want: scalar = min(scalar, 2.5)

    df["scalar"] = scalar
    df["ret_combo_net"] = df["ret_combo_raw"] * scalar

    # Equity & drawdown from net returns
    df["equity_net"] = (1 + df["ret_combo_net"].fillna(0.0)).cumprod()
    df["drawdown"]   = df["equity_net"]/df["equity_net"].cummax() - 1.0

    # Optional: join copper 3m price (doesn't affect returns)
    px_xlsx = Path(r"C:\Code\Metals\Data\copper\pricing\pricing_values.xlsx")
    if px_xlsx.exists():
        try:
            import openpyxl  # for xlsx engine
            pxd = pd.read_excel(px_xlsx, sheet_name=0, header=0)
            # Date = column A (0), 3m price = column D (3)
            pxd = pxd.iloc[:, [0, 3]].copy()
            pxd.columns = ["dt","copper_3m"]
            pxd["dt"] = pd.to_datetime(pxd["dt"])
            df = df.merge(pxd, on="dt", how="left")
        except Exception:
            pass

    # Write daily series (returns-only, single-scalar)
    daily_cols = ["dt",
                  "copper_3m" if "copper_3m" in df.columns else None,
                  "ret_hook","ret_stocks","ret_combo_raw","scalar","ret_combo_net",
                  "equity_net","drawdown"]
    daily_cols = [c for c in daily_cols if c is not None]
    (out_dir/"daily_series.csv").write_text(df[daily_cols].to_csv(index=False))

    # Legacy daily_combo (to keep other code happy)
    legacy = df[["dt"]].copy()
    legacy["hook"] = df["ret_hook"]
    legacy["stocks"] = df["ret_stocks"]
    legacy["combo_eqw"] = (df["ret_hook"] + df["ret_stocks"]) / 2.0
    legacy["combo_10vol"] = df["ret_combo_net"]
    (out_dir/"daily_combo.csv").write_text(legacy.to_csv(index=False))

    # Summary (computed on ALL data; your OOS is still scaled by construction)
    ann_vol_all = ann_vol(df["ret_combo_net"])
    ann_ret_all = df["ret_combo_net"].mean() * TRADING_DAYS
    sharpe  = ann_ret_all / (ann_vol_all + 1e-12)
    dd = (df["equity_net"]/df["equity_net"].cummax()-1).min()
    hit = (df["ret_combo_net"] > 0).mean()

    summary = pd.DataFrame([{
        "name":"Composite_net",
        "ann_return": ann_ret_all,
        "ann_vol": ann_vol_all,
        "sharpe": sharpe,
        "max_drawdown": dd,
        "hit_rate": hit,
        "turnover_ann": np.nan
    }])
    summary.to_csv(out_dir/"summary_metrics.csv", index=False)

    print("[OK] Wrote (returns-only, single-scalar OOS=10%):")
    print(f" - {out_dir/'daily_series.csv'}")
    print(f" - {out_dir/'daily_combo.csv'}")
    print(f" - {out_dir/'summary_metrics.csv'}")

if __name__ == "__main__":
    main()
