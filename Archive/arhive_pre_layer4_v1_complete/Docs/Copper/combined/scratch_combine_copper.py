import os, sys
import pandas as pd
import numpy as np

# ---- YOUR PATHS (edit if different) ----
HOOK_PATH   = r"C:\Code\Metals\outputs\copper\pricing\daily_series.csv"     # HookCore (pricing)
STOCKS_PATH = r"C:\Code\Metals\outputs\copper\stocks\daily_series.csv"      # StocksCore v0.1.1
OUT_DIR     = r"C:\Code\Metals\outputs\copper\composite_ad_hoc"
# ----------------------------------------

def must_exist(path):
    if not os.path.exists(path):
        sys.exit(f"[ERROR] File not found:\n  {path}\n(CWD: {os.getcwd()})")

def load_hookcore(path):
    """Use return_biweekly as HookCore daily PnL."""
    df = pd.read_csv(path)
    # rename date -> dt, make sure the columns we need exist
    if "date" not in df.columns:
        sys.exit(f"[ERROR] 'date' column not found in HookCore file. Columns: {list(df.columns)}")
    # prefer biweekly; fallback to weekly if needed
    ret_col = "return_biweekly" if "return_biweekly" in df.columns else (
              "return_weekly"   if "return_weekly"   in df.columns else None)
    if ret_col is None:
        sys.exit(f"[ERROR] Could not find return_biweekly/return_weekly in HookCore file. Columns: {list(df.columns)}")
    df = df.rename(columns={"date":"dt"})[["dt", ret_col]].copy()
    df["dt"] = pd.to_datetime(df["dt"], errors="coerce")
    df = df.dropna(subset=["dt"]).sort_values("dt")
    df = df.rename(columns={ret_col:"hook"})
    return df

def find_date_col(cols):
    for cand in ["dt","Date","date","timestamp","Datetime","datetime"]:
        if cand in cols: return cand
    for c in cols:
        if "unnamed" in c.lower(): return c
    return None

def load_stockscore(path):
    """Use pnl_net as StocksCore daily PnL."""
    head = pd.read_csv(path, nrows=1)
    date_col = find_date_col(list(head.columns))
    if date_col is None:
        sys.exit(f"[ERROR] Could not find a date column in StocksCore file. Columns: {list(head.columns)}")
    # find pnl_net or any 'pnl' column
    pnl_col = "pnl_net" if "pnl_net" in head.columns else None
    if pnl_col is None:
        for c in head.columns:
            if "pnl" in c.lower():
                pnl_col = c; break
    if pnl_col is None:
        sys.exit(f"[ERROR] Could not find a PnL column in StocksCore file. Columns: {list(head.columns)}")
    df = pd.read_csv(path)
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col)
    df = df[[date_col, pnl_col]].rename(columns={date_col:"dt", pnl_col:"stocks"})
    return df

# sanity checks and load
must_exist(HOOK_PATH); must_exist(STOCKS_PATH)
os.makedirs(OUT_DIR, exist_ok=True)

hook   = load_hookcore(HOOK_PATH)
stocks = load_stockscore(STOCKS_PATH)

# inner-join by date
df = pd.merge(hook, stocks, on="dt", how="inner").sort_values("dt")
if df.empty:
    sys.exit("[ERROR] No overlapping dates between HookCore and StocksCore. Check the two input files.")

# equal-weight combo, then scale OOS to 10% vol
df["combo_eqw"] = 0.5*df["hook"] + 0.5*df["stocks"]
oos_start = pd.Timestamp("2018-01-01")
oos_mask = df["dt"] >= oos_start
vol_oos = df.loc[oos_mask, "combo_eqw"].std(ddof=0) * np.sqrt(252)
scale = 0.10/vol_oos if vol_oos and not np.isnan(vol_oos) else 1.0
df["combo_10vol"] = df["combo_eqw"] * scale

def metrics(x: pd.Series):
    ann_mu  = x.mean()*252
    ann_vol = x.std(ddof=0)*np.sqrt(252)
    sh = ann_mu/ann_vol if ann_vol else np.nan
    eq = x.cumsum()
    dd = eq - eq.cummax()
    mdd = -dd.min() if len(eq) else np.nan
    cum = eq.iloc[-1] if len(eq) else np.nan
    return ann_mu, ann_vol, sh, mdd, cum

rows = []
for name in ["hook","stocks","combo_eqw","combo_10vol"]:
    s = df[name]
    mu_all, vol_all, sh_all, dd_all, cum_all = metrics(s)
    s_is  = s[df["dt"] <  oos_start]
    s_oos = s[df["dt"] >= oos_start]
    mu_is, vol_is, sh_is, dd_is, cum_is = metrics(s_is)
    mu_oos, vol_oos2, sh_oos, dd_oos, cum_oos = metrics(s_oos)
    rows.append({
        "series": name,
        "ALL_ann_return": mu_all, "ALL_ann_vol": vol_all, "ALL_sharpe": sh_all, "ALL_maxDD": dd_all, "ALL_cumRet": cum_all,
        "IS_ann_return":  mu_is,  "IS_ann_vol":  vol_is,  "IS_sharpe":  sh_is,  "IS_maxDD":  dd_is,  "IS_cumRet":  cum_is,
        "OOS_ann_return": mu_oos, "OOS_ann_vol": vol_oos2,"OOS_sharpe": sh_oos, "OOS_maxDD": dd_oos, "OOS_cumRet": cum_oos,
    })

summary = pd.DataFrame(rows)

# save
daily_out   = os.path.join(OUT_DIR, "daily_combo.csv")
summary_out = os.path.join(OUT_DIR, "summary_metrics.csv")
df.to_csv(daily_out, index=False)
summary.to_csv(summary_out, index=False)

print(f"\n✅ Wrote:\n - {daily_out}\n - {summary_out}")
print(f"📏 OOS scale used (to 10% vol): {scale:.3f}")
print("\n🔎 Summary (key cols):")
print(summary[["series","IS_sharpe","OOS_sharpe","IS_ann_return","OOS_ann_return","IS_maxDD","OOS_maxDD"]].to_string(index=False))
