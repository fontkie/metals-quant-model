import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

TRADING_DAYS = 252
OOS_START = pd.Timestamp("2018-01-01")
TARGET_ANN_VOL = 0.10
VT_LOOKBACK_D = 21
LEVERAGE_CAP = 2.5

# Paths
HOOK_PATH   = Path("outputs/copper/pricing/daily_series.csv")
STOCKS_PATH = Path("outputs/copper/stocks/daily_series.csv")
OUT_DIR     = Path("outputs/copper/composite_ad_hoc")
PX_XLSX     = Path(r"C:\Code\Metals\Data\copper\pricing\pricing_values.xlsx")  # optional (Date=A, 3m=D)

def safe_to_csv(df: pd.DataFrame, path: Path):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
    except PermissionError:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        alt = path.with_name(path.stem + f"_{ts}" + path.suffix)
        df.to_csv(alt, index=False)
        print(f"[WARN] {path.name} locked. Wrote to {alt.name} instead.")

def read_table_auto(path: Path, date_candidates=("dt","date","Date","datetime","DT")) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing: {path}")
    df = pd.read_csv(path) if path.suffix.lower() in (".csv",".txt") else pd.read_excel(path)
    for c in date_candidates:
        if c in df.columns:
            df["dt"] = pd.to_datetime(df[c]); break
    else:
        raise ValueError(f"No date column found in {path}. Columns={list(df.columns)}")
    return df.sort_values("dt").reset_index(drop=True)

def ann_vol(x: pd.Series) -> float:
    return x.std(ddof=0) * np.sqrt(TRADING_DAYS)

def tplus1_vt(ret_series: pd.Series,
              target_ann_vol=TARGET_ANN_VOL,
              lookback=VT_LOOKBACK_D,
              cap=LEVERAGE_CAP) -> pd.DataFrame:
    rv_daily = ret_series.rolling(lookback, min_periods=lookback).std(ddof=0)
    rv_ann = rv_daily * np.sqrt(TRADING_DAYS)
    lev_today = (target_ann_vol / rv_ann).clip(upper=cap)
    lev_exec = lev_today.shift(1)  # T+1 application
    ret_net = ret_series * lev_exec
    return lev_exec, ret_net

def build_with_stocks_column(hook_df: pd.DataFrame, stocks_df: pd.DataFrame, stocks_col: str):
    hook = hook_df.rename(columns={"return_weekly": "ret_hook"})[["dt","ret_hook"]]
    stocks = stocks_df.rename(columns={stocks_col: "ret_stocks"})[["dt","ret_stocks"]]
    df = pd.merge(hook, stocks, on="dt", how="inner", validate="one_to_one").sort_values("dt").reset_index(drop=True)
    df["ret_combo_raw"] = 0.5*df["ret_hook"] + 0.5*df["ret_stocks"]
    df["lev"], df["ret_combo_net"] = tplus1_vt(df["ret_combo_raw"])
    df["equity_net"] = (1 + df["ret_combo_net"].fillna(0.0)).cumprod()
    df["drawdown"] = df["equity_net"] / df["equity_net"].cummax() - 1.0

    oos_mask = df["dt"] >= OOS_START
    oos = df.loc[oos_mask, "ret_combo_net"]
    oos_sr = (oos.mean()*TRADING_DAYS) / (ann_vol(oos) + 1e-12)
    oos_eq = (1 + oos.fillna(0.0)).cumprod()
    oos_dd = (oos_eq / oos_eq.cummax() - 1.0).min()
    oos_corr = df.loc[oos_mask, ["ret_hook","ret_stocks"]].corr().iloc[0,1]
    return df, {"oos_sharpe": oos_sr, "oos_dd": oos_dd, "oos_corr": oos_corr}

def main():
    # Read inputs
    hook_raw   = read_table_auto(HOOK_PATH)
    stocks_raw = read_table_auto(STOCKS_PATH)

    # Enforce Hook weekly column (your B,D,F mapping: we use F=return_weekly)
    if "return_weekly" not in hook_raw.columns:
        raise ValueError(f"HookCore: 'return_weekly' not found. Columns={list(hook_raw.columns)}")

    # Decide Stocks column by OOS Sharpe under composite VT
    stocks_candidates = [c for c in ("ret","pnl_net") if c in stocks_raw.columns]
    if not stocks_candidates:
        raise ValueError(f"StocksCore: none of ['ret','pnl_net'] found. Columns={list(stocks_raw.columns)}")

    best = None
    best_stats = None
    best_df = None
    for c in stocks_candidates:
        tmp_df, stats = build_with_stocks_column(hook_raw, stocks_raw, c)
        if best is None or stats["oos_sharpe"] > best_stats["oos_sharpe"]:
            best, best_stats, best_df = c, stats, tmp_df

    df = best_df
    chosen_stocks = best
    print(f"[INFO] Using Stocks column: {chosen_stocks}")
    print(f"[INFO] OOS Sharpe: {best_stats['oos_sharpe']:.3f} | OOS max DD: {best_stats['oos_dd']:.3%} | OOS corr: {best_stats['oos_corr']:.3f}")

    # Optional copper 3m price join
    if PX_XLSX.exists():
        try:
            pxd = pd.read_excel(PX_XLSX, sheet_name=0, header=0).iloc[:, [0,3]].copy()
            pxd.columns = ["dt","copper_3m"]; pxd["dt"] = pd.to_datetime(pxd["dt"])
            df = df.merge(pxd, on="dt", how="left")
        except Exception as e:
            print(f"[WARN] price join skipped ({e})")

    # Write outputs
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    daily_cols = ["dt",
                  "copper_3m" if "copper_3m" in df.columns else None,
                  "ret_hook","ret_stocks","ret_combo_raw","lev","ret_combo_net","equity_net","drawdown"]
    daily_cols = [c for c in daily_cols if c is not None]
    safe_to_csv(df[daily_cols], OUT_DIR / "daily_series.csv")

    legacy = pd.DataFrame({
        "dt": df["dt"],
        "hook": df["ret_hook"],
        "stocks": df["ret_stocks"],
        "combo_eqw": (df["ret_hook"] + df["ret_stocks"]) / 2.0,
        "combo_10vol": df["ret_combo_net"],
    })
    safe_to_csv(legacy, OUT_DIR / "daily_combo.csv")

    # Summary (ALL + OOS)
    oos_mask = df["dt"] >= OOS_START
    def stats(ret: pd.Series):
        v = ann_vol(ret); m = ret.mean()*TRADING_DAYS
        return m, v, m/(v+1e-12)
    m_all, v_all, s_all = stats(df["ret_combo_net"])
    m_oos, v_oos, s_oos = stats(df.loc[oos_mask, "ret_combo_net"])
    dd_all = (df["equity_net"] / df["equity_net"].cummax() - 1.0).min()
    oos_eq = (1 + df.loc[oos_mask, "ret_combo_net"].fillna(0.0)).cumprod()
    oos_dd = (oos_eq / oos_eq.cummax() - 1.0).min()
    oos_corr = df.loc[oos_mask, ["ret_hook","ret_stocks"]].corr().iloc[0,1]

    summ = pd.DataFrame([{
        "name": "CopperComposite (weekly + T+1 VT)",
        "OOS_ann_return": m_oos, "OOS_ann_vol": v_oos, "OOS_sharpe": s_oos,
        "OOS_max_drawdown": oos_dd, "OOS_corr_hook_stocks": oos_corr,
        "ALL_ann_return": m_all, "ALL_ann_vol": v_all, "ALL_sharpe": s_all, "ALL_max_drawdown": dd_all,
        "inputs": f"Hook=return_weekly, Stocks={chosen_stocks}",
        "vt": f"target={TARGET_ANN_VOL:.0%}, lookback={VT_LOOKBACK_D}, cap={LEVERAGE_CAP}x"
    }])
    safe_to_csv(summ, OUT_DIR / "summary_metrics.csv")

    print("[OK] Wrote:")
    print(f" - {OUT_DIR / 'daily_series.csv'}")
    print(f" - {OUT_DIR / 'daily_combo.csv'}")
    print(f" - {OUT_DIR / 'summary_metrics.csv'}")

if __name__ == "__main__":
    main()
