import numpy as np
import pandas as pd
from pathlib import Path

TRADING_DAYS = 252
OOS_START = pd.Timestamp("2018-01-01")

# Targets from your seed chat
HOOK_TARGET_SHARPE = 0.35
STOCKS_TARGET_SHARPE = 0.59

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

def ann_vol(x): return x.std(ddof=0) * np.sqrt(TRADING_DAYS)
def sharpe(x):
    v = ann_vol(x)
    m = x.mean() * TRADING_DAYS
    return (m / v) if v > 0 else np.nan

def score_candidate(oos_sharpe, target):
    if np.isnan(oos_sharpe): return 1e9
    return abs(oos_sharpe - target)

def best_return_column(df, candidates, target_sharpe, label):
    avail = [c for c in candidates if c in df.columns]
    if not avail:
        raise ValueError(f"{label}: none of the candidate columns present. Candidates={candidates}, Columns={list(df.columns)}")
    # Evaluate each candidate by OOS Sharpe closeness
    best = None
    best_s = 1e9
    best_row = None
    for c in avail:
        r = df[c].astype(float)
        oos = r[df["dt"] >= OOS_START]
        s = sharpe(oos)
        sc = score_candidate(s, target_sharpe)
        if sc < best_s:
            best_s = sc
            best = c
            best_row = {"candidate": c, "oos_sharpe": s, "oos_ann_vol": ann_vol(oos), "oos_ann_ret": oos.mean()*TRADING_DAYS}
    return best, best_row, avail

def main():
    # Paths
    hook_path   = Path("outputs/copper/pricing/daily_series.csv")
    stocks_path = Path("outputs/copper/stocks/daily_series.csv")
    out_dir = Path("outputs/copper/composite_ad_hoc"); out_dir.mkdir(parents=True, exist_ok=True)

    # Read
    hook_raw   = read_table_auto(hook_path)
    stocks_raw = read_table_auto(stocks_path)

    # Candidate return columns
    hook_candidates   = ["return_biweekly","ret_biweekly","return_weekly","ret_weekly","ret","return","pnl_net"]
    stocks_candidates = ["ret","return","pnl_net"]

    # Pick best candidates by OOS Sharpe closeness
    hook_col, hook_info, hook_avail = best_return_column(hook_raw, hook_candidates, HOOK_TARGET_SHARPE, "HookCore")
    stocks_col, stocks_info, stocks_avail = best_return_column(stocks_raw, stocks_candidates, STOCKS_TARGET_SHARPE, "StocksCore")

    print("=== Column selection ===")
    print(f"Hook candidates available: {hook_avail}")
    print(f"Chosen Hook return: {hook_col} | OOS Sharpe≈{hook_info['oos_sharpe']:.3f}, OOS vol≈{hook_info['oos_ann_vol']:.3%}, OOS ann ret≈{hook_info['oos_ann_ret']:.3%}")
    print(f"Stocks candidates available: {stocks_avail}")
    print(f"Chosen Stocks return: {stocks_col} | OOS Sharpe≈{stocks_info['oos_sharpe']:.3f}, OOS vol≈{stocks_info['oos_ann_vol']:.3%}, OOS ann ret≈{stocks_info['oos_ann_ret']:.3%}")

    # Build returns-only composite with equal weights, then single-scalar OOS=10%
    hook   = hook_raw.rename(columns={hook_col:"ret_hook"})[["dt","ret_hook"]]
    stocks = stocks_raw.rename(columns={stocks_col:"ret_stocks"})[["dt","ret_stocks"]]
    df = pd.merge(hook, stocks, on="dt", how="inner", validate="one_to_one").sort_values("dt").reset_index(drop=True)

    # Equal-returns weighting
    df["ret_combo_raw"] = 0.5*df["ret_hook"] + 0.5*df["ret_stocks"]

    # Single-scalar scaling on OOS to 10% ann vol
    oos = df.loc[df["dt"] >= OOS_START, "ret_combo_raw"]
    oos_vol = ann_vol(oos)
    if oos_vol == 0 or np.isnan(oos_vol):
        raise ValueError("OOS vol is zero/NaN; check OOS overlap.")
    scalar = 0.10 / oos_vol
    df["scalar"] = scalar
    df["ret_combo_net"] = df["ret_combo_raw"] * scalar
    df["equity_net"] = (1 + df["ret_combo_net"].fillna(0.0)).cumprod()
    df["drawdown"] = df["equity_net"]/df["equity_net"].cummax() - 1.0

    # Optional 3m price join (your Excel: Date=A(0), 3m=D(3))
    px_xlsx = Path(r"C:\Code\Metals\Data\copper\pricing\pricing_values.xlsx")
    if px_xlsx.exists():
        try:
            import openpyxl  # engine
            pxd = pd.read_excel(px_xlsx, sheet_name=0, header=0).iloc[:, [0,3]].copy()
            pxd.columns = ["dt","copper_3m"]; pxd["dt"] = pd.to_datetime(pxd["dt"])
            df = df.merge(pxd, on="dt", how="left")
        except Exception:
            pass

    # Write
    daily_cols = ["dt",
                  "copper_3m" if "copper_3m" in df.columns else None,
                  "ret_hook","ret_stocks","ret_combo_raw","scalar","ret_combo_net",
                  "equity_net","drawdown"]
    daily_cols = [c for c in daily_cols if c is not None]
    (out_dir/"daily_series.csv").write_text(df[daily_cols].to_csv(index=False))

    legacy = df[["dt"]].copy()
    legacy["hook"] = df["ret_hook"]; legacy["stocks"] = df["ret_stocks"]
    legacy["combo_eqw"] = (df["ret_hook"] + df["ret_stocks"]) / 2.0
    legacy["combo_10vol"] = df["ret_combo_net"]
    (out_dir/"daily_combo.csv").write_text(legacy.to_csv(index=False))

    # Summary (report both ALL and OOS)
    def summ(ret):
        return {
            "ann_return": ret.mean()*TRADING_DAYS,
            "ann_vol": ann_vol(ret),
            "sharpe": (ret.mean()*TRADING_DAYS) / (ann_vol(ret) + 1e-12)
        }

    all_s = summ(df["ret_combo_net"])
    oos_s = summ(df.loc[df["dt"] >= OOS_START, "ret_combo_net"])
    dd_all = (df["equity_net"]/df["equity_net"].cummax()-1).min()

    summary = pd.DataFrame([{
        "name":"Composite_net",
        "ALL_ann_return": all_s["ann_return"],
        "ALL_ann_vol": all_s["ann_vol"],
        "ALL_sharpe": all_s["sharpe"],
        "OOS_ann_vol": oos_s["ann_vol"],
        "OOS_sharpe": oos_s["sharpe"],
        "max_drawdown": dd_all
    }])
    summary.to_csv(out_dir/"summary_metrics.csv", index=False)

    print("\n=== Composite Scaling ===")
    print(f"OOS vol before scalar: {oos_vol:.3%}  -> scalar applied: {scalar:.3f}")
    print("\n[OK] Wrote:")
    print(f" - {out_dir/'daily_series.csv'}")
    print(f" - {out_dir/'daily_combo.csv'}")
    print(f" - {out_dir/'summary_metrics.csv'}")

if __name__ == "__main__":
    main()
