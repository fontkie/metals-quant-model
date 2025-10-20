import numpy as np
import pandas as pd
from pathlib import Path

TRADING_DAYS = 252
OOS_START = pd.Timestamp("2018-01-01")
TARGET_ANN_VOL = 0.10
VT_LOOKBACK_D = 21
LEVERAGE_CAP = 2.5

HOOK_PATH   = Path("outputs/copper/pricing/daily_series.csv")
STOCKS_PATH = Path("outputs/copper/stocks/daily_series.csv")

def read_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path) if path.suffix.lower() in (".csv", ".txt") else pd.read_excel(path)
    # standardize date column
    for c in ("dt","date","Date","datetime","DT"):
        if c in df.columns:
            df["dt"] = pd.to_datetime(df[c])
            break
    else:
        raise ValueError(f"No date column found in {path}. Columns={list(df.columns)}")
    return df.sort_values("dt").reset_index(drop=True)

def ann_vol(x: pd.Series) -> float:
    return x.std(ddof=0) * np.sqrt(TRADING_DAYS)

def tplus1_vt(ret_series: pd.Series,
              target_ann_vol=TARGET_ANN_VOL,
              lookback=VT_LOOKBACK_D,
              cap=LEVERAGE_CAP):
    rv_daily = ret_series.rolling(lookback, min_periods=lookback).std(ddof=0)
    rv_ann = rv_daily * np.sqrt(TRADING_DAYS)
    lev_today = (target_ann_vol / rv_ann).clip(upper=cap)
    lev_exec = lev_today.shift(1)  # T+1 application
    ret_net = ret_series * lev_exec
    return lev_exec, ret_net

def build_metrics(hook_df: pd.DataFrame, stocks_df: pd.DataFrame,
                  hook_ret_col: str, stocks_ret_col: str) -> dict:
    if hook_ret_col not in hook_df.columns:
        return {"ok": False, "reason": f"missing {hook_ret_col}"}
    if stocks_ret_col not in stocks_df.columns:
        return {"ok": False, "reason": f"missing {stocks_ret_col}"}

    h = hook_df.rename(columns={hook_ret_col:"ret_hook"})[["dt","ret_hook"]]
    s = stocks_df.rename(columns={stocks_ret_col:"ret_stocks"})[["dt","ret_stocks"]]
    df = pd.merge(h, s, on="dt", how="inner", validate="one_to_one").sort_values("dt").reset_index(drop=True)

    df["ret_combo_raw"] = 0.5*df["ret_hook"] + 0.5*df["ret_stocks"]
    df["lev"], df["ret_combo_net"] = tplus1_vt(df["ret_combo_raw"])
    df["equity_net"] = (1 + df["ret_combo_net"].fillna(0.0)).cumprod()

    oos_mask = df["dt"] >= OOS_START
    oos = df.loc[oos_mask, "ret_combo_net"]
    allr = df["ret_combo_net"]

    def stats(x: pd.Series):
        v = ann_vol(x); m = x.mean()*TRADING_DAYS
        s = m/(v+1e-12)
        return m, v, s

    m_all, v_all, s_all = stats(allr)
    m_oos, v_oos, s_oos = stats(oos)

    # drawdowns
    eq_all = (1 + allr.fillna(0.0)).cumprod()
    dd_all = (eq_all/eq_all.cummax() - 1.0).min()
    eq_oos = (1 + oos.fillna(0.0)).cumprod()
    dd_oos = (eq_oos/eq_oos.cummax() - 1.0).min()

    corr_oos = df.loc[oos_mask, ["ret_hook","ret_stocks"]].corr().iloc[0,1]

    return {
        "ok": True,
        "hook": hook_ret_col,
        "stocks": stocks_ret_col,
        "OOS_ann_ret": m_oos, "OOS_ann_vol": v_oos, "OOS_sharpe": s_oos,
        "OOS_maxDD": dd_oos, "OOS_corr": corr_oos,
        "ALL_ann_ret": m_all, "ALL_ann_vol": v_all, "ALL_sharpe": s_all, "ALL_maxDD": dd_all,
        "rows_OOS": int(oos_mask.sum())
    }

def main():
    hook = read_table(HOOK_PATH)
    stocks = read_table(STOCKS_PATH)

    combos = [
        ("return_weekly",   "ret"),
        ("return_weekly",   "pnl_net"),
        ("return_biweekly", "ret"),
        ("return_biweekly", "pnl_net"),
    ]
    results = []
    for hc, sc in combos:
        try:
            res = build_metrics(hook, stocks, hc, sc)
        except Exception as e:
            res = {"ok": False, "hook": hc, "stocks": sc, "reason": str(e)}
        results.append(res)

    # Print table to terminal (VS Code)
    print("\n=== CopperComposite — Weekly vs Bi-weekly × Stocks ret vs pnl_net (T+1 VT, 10%, 21d, cap 2.5x) ===")
    header = f"{'Hook':16} {'Stocks':10} | {'OOS_Sharpe':10} {'OOS_Vol':9} {'OOS_MaxDD':10} {'OOS_Corr':9} | {'ALL_Sharpe':10} {'ALL_Vol':9} {'ALL_MaxDD':10}"
    print(header)
    print("-"*len(header))
    for r in results:
        if not r.get("ok", False):
            print(f"{r.get('hook','?'):16} {r.get('stocks','?'):10} | {'ERR':10} {'-':9} {'-':10} {'-':9} | {'-':10} {'-':9} {'-':10}   ({r.get('reason','')})")
            continue
        print(f"{r['hook']:16} {r['stocks']:10} | "
              f"{r['OOS_sharpe']:10.3f} {r['OOS_ann_vol']:9.3%} {r['OOS_maxDD']:10.3%} {r['OOS_corr']:9.3f} | "
              f"{r['ALL_sharpe']:10.3f} {r['ALL_ann_vol']:9.3%} {r['ALL_maxDD']:10.3%}")
    print("\nNote: OOS window starts at", OOS_START.date(), " | T+1 VT params: target=10%, lookback=21d, cap=2.5x")

if __name__ == "__main__":
    main()
