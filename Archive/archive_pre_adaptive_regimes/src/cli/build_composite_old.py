import argparse
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import yaml

TRADING_DAYS = 252

# ============= helpers =============
def ann_vol(x: pd.Series) -> float:
    return x.std(ddof=0) * np.sqrt(TRADING_DAYS)

def sharpe(x: pd.Series) -> float:
    v = ann_vol(x)
    return float(x.mean() * TRADING_DAYS / v) if v > 0 else np.nan

def max_drawdown(eq: pd.Series) -> float:
    peak = eq.cummax()
    dd = eq / peak - 1.0
    return float(dd.min())

def hit_rate(x: pd.Series) -> float:
    n = (x > 0).sum()
    d = x.notna().sum()
    return float(n / d) if d else np.nan

def turnover_series(pos: pd.Series) -> pd.Series:
    return pos.diff().abs().fillna(0.0)

def read_yaml(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}

def read_table_auto(path: str, date_col_candidates=("dt","date","Date","datetime","DT")) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing file: {p}")
    if p.suffix.lower() in (".csv", ".txt"):
        df = pd.read_csv(p)
    elif p.suffix.lower() in (".xlsx", ".xls"):
        try:
            import openpyxl  # noqa: F401
        except Exception:
            pass
        df = pd.read_excel(p)
    else:
        raise ValueError(f"Unsupported file extension for {p.name}")
    date_col = None
    for c in date_col_candidates:
        if c in df.columns:
            date_col = c
            break
    if date_col is None:
        raise ValueError(f"Could not find a date column in {p}. Columns: {list(df.columns)}")
    df["dt"] = pd.to_datetime(df[date_col])
    return df.sort_values("dt").reset_index(drop=True)

def read_price_from_excel(xlsx_path: str, sheet: str | None, date_col_idx: int, px_col_idx: int) -> pd.DataFrame:
    """
    Read price from Excel by zero-based column indices.
    date_col_idx: 0 for column A, 3 for column D, etc.
    """
    try:
        import openpyxl  # ensure engine for .xlsx
    except Exception:
        pass

    # If sheet is None, read the FIRST sheet; otherwise read that named sheet.
    sheet_name = 0 if sheet is None else sheet
    df = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=0)

    # If for any reason we still got a dict (older pandas), take the first sheet
    if isinstance(df, dict):
        df = next(iter(df.values()))

    # Select columns by position (zero-based)
    df = df.iloc[:, [date_col_idx, px_col_idx]].copy()
    df.columns = ["dt", "copper_3m"]
    df["dt"] = pd.to_datetime(df["dt"])
    df = df.sort_values("dt").dropna(subset=["dt"]).reset_index(drop=True)
    return df


def inverse_vol_weights(r1: pd.Series, r2: pd.Series, lookback: int) -> pd.DataFrame:
    v1 = r1.rolling(lookback).std(ddof=0)
    v2 = r2.rolling(lookback).std(ddof=0)
    w1 = 1.0 / v1.replace(0, np.nan)
    w2 = 1.0 / v2.replace(0, np.nan)
    ws = w1 + w2
    return pd.DataFrame({"w_hook": w1/ws, "w_stocks": w2/ws})

def vol_target_tplus1(ret_raw: pd.Series, target_ann_vol: float, lookback_days: int, cap: float) -> pd.DataFrame:
    rv_daily = ret_raw.rolling(lookback_days).std(ddof=0)
    rv_ann = rv_daily * np.sqrt(TRADING_DAYS)
    lev = (target_ann_vol / rv_ann).clip(upper=cap)
    lev_t1 = lev.shift(1)  # T+1 execution
    ret_scaled = ret_raw * lev_t1
    return pd.DataFrame({"lev": lev_t1, "ret_scaled": ret_scaled})

# ============= main =============
def main():
    ap = argparse.ArgumentParser(description="Build Copper composite daily series (PM view) with optional price join.")
    ap.add_argument("--config", required=True, help="Path to docs/Copper/combined/composite_config.yaml")
    ap.add_argument("--weight_lookback", type=int, default=63, help="Lookback for inverse-vol weights (default 63)")
    # Price join options (your Excel defaults baked in; can override)
    ap.add_argument("--price_xlsx", type=str, default=r"C:\Code\Metals\Data\copper\pricing\pricing_values.xlsx")
    ap.add_argument("--price_sheet", type=str, default=None, help="Sheet name if needed (None = first sheet)")
    ap.add_argument("--price_date_col_idx", type=int, default=0, help="0-based index (A=0) — you said Date is col A")
    ap.add_argument("--price_px_col_idx", type=int, default=3, help="0-based index (D=3) — you said 3-mo is col D")
    ap.add_argument("--no_price", action="store_true", help="Skip joining price even if Excel path exists")
    args = ap.parse_args()

    # ---------- Load configs, tolerate missing bits ----------
    cfg = read_yaml(args.config)
    def _load_global_defaults():
        gpath = Path("config/global.yaml")
        return read_yaml(str(gpath)) if gpath.exists() else {}
    global_cfg = _load_global_defaults()

    ass = cfg.get("assumptions", {})
    vol_cfg = ass.get("vol_target") or ass.get("vol") or {}
    g_vol = (global_cfg.get("vol_target") if isinstance(global_cfg, dict) else {}) or {}

    target_vol   = float(vol_cfg.get("ann_pct",       g_vol.get("ann_pct",       10.0))) / 100.0
    lookback_vol = int(  vol_cfg.get("lookback_days", g_vol.get("lookback_days", 21)))
    cap          = float(vol_cfg.get("leverage_cap",  g_vol.get("leverage_cap",  2.5)))
    costs_bps    = float(ass.get("cost_bps_per_turnover", global_cfg.get("cost_bps_per_turnover", 1.5)))

    exec_cfg = cfg.get("execution", {})
    rebalance_days = set(exec_cfg.get("rebalance_days", ["Mon","Wed"]))
    t_plus = int(exec_cfg.get("t_plus", 1))

    reporting = cfg.get("reporting", {}).get("write", {})
    out_combo   = Path(reporting.get("combo_path",   "outputs/copper/composite_ad_hoc/daily_combo.csv"))
    out_summary = Path(reporting.get("summary_path", "outputs/copper/composite_ad_hoc/summary_metrics.csv"))
    out_dir = out_combo.parent; out_dir.mkdir(parents=True, exist_ok=True)

    # ---------- Inputs ----------
    hook_cfg   = cfg.get("inputs", {}).get("hookcore", {})
    stocks_cfg = cfg.get("inputs", {}).get("stockscore", {})
    if not hook_cfg or not stocks_cfg:
        raise ValueError("Missing inputs.hookcore / inputs.stockscore in YAML.")

    use_stream = str(hook_cfg.get("use_stream", "biweekly")).lower()
    hook_path   = hook_cfg.get("path");  stocks_path = stocks_cfg.get("path")
    if not hook_path or not stocks_path:
        raise ValueError("inputs.hookcore.path and inputs.stockscore.path must be set.")
    hook_raw   = read_table_auto(hook_path)
    stocks_raw = read_table_auto(stocks_path)

    # Map Hook fields
    hf = hook_cfg.get("fields", {})
    ret_hook_col = hf.get("ret_biweekly") if use_stream == "biweekly" else hf.get("ret_weekly")
    pos_hook_col = hf.get("pos_biweekly") if use_stream == "biweekly" else hf.get("pos_weekly")
    if not ret_hook_col or not pos_hook_col:
        raise ValueError("HookCore fields missing: ret_weekly/ret_biweekly and pos_weekly/pos_biweekly required.")
    missing_hook = [c for c in [ret_hook_col, pos_hook_col] if c not in hook_raw.columns]
    if missing_hook:
        raise ValueError(f"HookCore missing columns {missing_hook}. Found: {list(hook_raw.columns)}")
    hook = hook_raw.rename(columns={ret_hook_col:"ret_hook", pos_hook_col:"pos_hook"})[["dt","ret_hook","pos_hook"]]

    # Map Stocks fields
    sf = stocks_cfg.get("fields", {})
    ret_stocks_col = sf.get("ret");  pos_stocks_col = sf.get("pos")
    if not ret_stocks_col or not pos_stocks_col:
        raise ValueError("StocksCore fields missing: need 'ret' and 'pos'.")
    missing_stocks = [c for c in [ret_stocks_col, pos_stocks_col] if c not in stocks_raw.columns]
    if missing_stocks:
        raise ValueError(f"StocksCore missing columns {missing_stocks}. Found: {list(stocks_raw.columns)}")
    stocks = stocks_raw.rename(columns={ret_stocks_col:"ret_stocks", pos_stocks_col:"pos_stocks"})[["dt","ret_stocks","pos_stocks"]]

    # Align & weights
    df = pd.merge(hook, stocks, on="dt", how="inner", validate="one_to_one").sort_values("dt").reset_index(drop=True)
    w = inverse_vol_weights(df["ret_hook"], df["ret_stocks"], lookback=args.weight_lookback)
    df = pd.concat([df, w], axis=1)

    weekdays = df["dt"].dt.day_name().str[:3]  # Mon, Tue, ...
    is_rebal = weekdays.isin(rebalance_days)
    df.loc[~is_rebal, ["w_hook","w_stocks"]] = np.nan
    df[["w_hook","w_stocks"]] = df[["w_hook","w_stocks"]].ffill()
    s = df["w_hook"] + df["w_stocks"]; df["w_hook"] /= s; df["w_stocks"] /= s

    # Composite pre-cost + positions (unlevered)
    df["ret_combo_raw"] = df["w_hook"]*df["ret_hook"] + df["w_stocks"]*df["ret_stocks"]
    df["pos_target"]    = df["w_hook"]*df["pos_hook"] + df["w_stocks"]*df["pos_stocks"]

    # Executed (T+1), costs, after-cost
    df["pos_exec"]  = df["pos_target"].shift(t_plus)
    df["turnover"]  = turnover_series(df["pos_exec"])
    df["cost"]      = (costs_bps / 10000.0) * df["turnover"]
    df["ret_after_cost"] = df["ret_combo_raw"] - df["cost"].fillna(0.0)

    # Vol target (T+1)
    vt = vol_target_tplus1(df["ret_after_cost"], target_vol, lookback_vol, cap)
    df["lev"] = vt["lev"]
    df["ret_combo_net"] = vt["ret_scaled"]

    # Levered positions, equity, drawdown
    df["pos_target_lev_T"] = df["pos_target"] * df["lev"]
    df["pos_exec_lev_T"]   = df["pos_exec"]   * df["lev"]
    df["equity_net"] = (1.0 + df["ret_combo_net"].fillna(0.0)).cumprod()
    df["drawdown"]   = df["equity_net"]/df["equity_net"].cummax() - 1.0

    # Join Copper 3m price from Excel (your path/cols)
    if not args.no_price and Path(args.price_xlsx).exists():
        p = read_price_from_excel(args.price_xlsx, args.price_sheet, args.price_date_col_idx, args.price_px_col_idx)
        df = df.merge(p, on="dt", how="left")

    # Write rich daily series
    daily_cols = [
        "dt",
        "copper_3m" if "copper_3m" in df.columns else None,
        "w_hook","w_stocks",
        "pos_hook","pos_stocks",
        "pos_target","pos_target_lev_T",
        "pos_exec","pos_exec_lev_T",
        "turnover","cost","lev",
        "ret_hook","ret_stocks","ret_combo_raw","ret_after_cost","ret_combo_net",
        "equity_net","drawdown"
    ]
    daily_cols = [c for c in daily_cols if c is not None]
    rich_path = out_dir / "daily_series.csv"
    df[daily_cols].to_csv(rich_path, index=False)

    # Legacy daily_combo
    legacy = pd.DataFrame({
        "dt": df["dt"],
        "hook": df["ret_hook"],
        "stocks": df["ret_stocks"],
        "combo_eqw": (df["ret_hook"] + df["ret_stocks"]) / 2.0,
        "combo_10vol": df["ret_combo_net"],
    })
    legacy_path = out_dir / "daily_combo.csv"
    legacy.to_csv(legacy_path, index=False)

    # Summary
    summary = pd.DataFrame([{
        "name": "Composite_net",
        "ann_return": df["ret_combo_net"].mean() * TRADING_DAYS,
        "ann_vol": ann_vol(df["ret_combo_net"]),
        "sharpe": sharpe(df["ret_combo_net"]),
        "max_drawdown": max_drawdown(df["equity_net"]),
        "hit_rate": hit_rate(df["ret_combo_net"]),
        "turnover_ann": float(df["turnover"].sum() / (len(df) / TRADING_DAYS)),
    }])
    out_summary.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_summary, index=False)

    print("[OK] Wrote:")
    print(f" - {rich_path}")
    print(f" - {legacy_path}")
    print(f" - {out_summary}")

if __name__ == "__main__":
    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 80)
    try:
        main()
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
