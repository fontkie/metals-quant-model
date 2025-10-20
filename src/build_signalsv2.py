# build_signals.py
# Backwards-compatible:
#   Old usage: python build_signals.py --db path/to/quant.db --outdir outputs/legacy/
# New usage (config-driven):
#   Single sleeve:
#       python build_signals.py --global config/global.yaml \
#           --sleeve-config docs/copper/pricing/hookcore_config.yaml \
#           --db data/price_db/quant.db --outdir outputs
#   All sleeves from registry:
#       python build_signals.py --global config/global.yaml \
#           --params docs/copper/params.yaml \
#           --db data/price_db/quant.db --outdir outputs
#
# Notes:
# - For HookCore v0.4.0 we assume prices come from SQLite table 'prices(dt, symbol, px_settle)'.
# - Positions: T+1 execution, bi-weekly schedule (Mon uses Fri signal; Wed uses Tue).
# - Vol target 10% (21d), leverage cap 2.5x, costs 1.5 bps per turnover (one-way).

import argparse
import os
import sys
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

# Optional deps for config-run
try:
    import yaml
except Exception:
    yaml = None


# ----------------------------
# Utilities
# ----------------------------
def load_prices_sqlite(db_path: str) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(
            "SELECT dt, symbol, px_settle FROM prices",
            con,
            parse_dates=["dt"]
        )
    finally:
        con.close()
    if df.empty:
        raise ValueError("No rows found in prices table.")
    df = df.sort_values(["dt", "symbol"])
    wide = df.pivot(index="dt", columns="symbol", values="px_settle").sort_index()
    return wide


def daily_log_returns(px: pd.Series) -> pd.Series:
    return np.log(px).diff()


def hday_log_return(px: pd.Series, h: int) -> pd.Series:
    return np.log(px / px.shift(h))


def zscore(series: pd.Series, lookback: int) -> pd.Series:
    mu = series.rolling(lookback, min_periods=lookback).mean()
    sd = series.rolling(lookback, min_periods=lookback).std(ddof=0)
    return (series - mu) / sd


def z_of_hday_return(px: pd.Series, h: int) -> pd.Series:
    """z of h-day return, using rolling std of h-day returns."""
    r_h = hday_log_return(px, h)
    sd_h = r_h.rolling(window=252, min_periods=60).std(ddof=0)  # longish stdev to stabilise
    # if you prefer 'pure' z over r_h's own rolling window, swap 252 for h or a config value
    return r_h / sd_h


def discrete_hook_from_z(z: pd.Series, threshold: float) -> pd.Series:
    """
    Mean-reversion hook: positive z (overbought) -> -1; negative z (oversold) -> +1
    0 inside the threshold band.
    """
    s = pd.Series(0.0, index=z.index)
    s[z >= threshold] = -1.0
    s[z <= -threshold] = +1.0
    return s


def biweekly_exec_map(dates: pd.DatetimeIndex) -> pd.Series:
    """
    Map each trading date to the 'signal origin' date implementing:
      - Monday uses the previous Friday's signal
      - Wednesday uses Tuesday's signal
    Positions only change on Mon and Wed; otherwise hold.
    """
    idx = pd.DatetimeIndex(dates)
    weekday = idx.weekday  # Mon=0, Tue=1, Wed=2, Thu=3, Fri=4
    origin = pd.Series(idx, index=idx)

    # Monday -> previous Friday
    is_mon = (weekday == 0)
    origin[is_mon] = origin[is_mon] - pd.Timedelta(days=3)  # assume continuous business days in index

    # Wednesday -> Tuesday
    is_wed = (weekday == 2)
    origin[is_wed] = origin[is_wed] - pd.Timedelta(days=1)

    # Other days: set to NaT to indicate "no new signal" (carry forward)
    mask_other = ~(is_mon | is_wed)
    origin[mask_other] = pd.NaT
    return origin


def apply_trade_calendar(raw_signal: pd.Series) -> pd.Series:
    """
    Take a daily raw signal and only 'activate' it on Mon/Wed according to the mapping,
    then forward-fill between executions.
    """
    idx = raw_signal.index
    origin_map = biweekly_exec_map(idx)

    activated = pd.Series(index=idx, dtype=float)
    activated[:] = np.nan

    # Assign only on execution days
    exec_days = origin_map.dropna().index
    for d in exec_days:
        origin_day = origin_map.loc[d]
        if origin_day in raw_signal.index:
            activated.loc[d] = raw_signal.loc[origin_day]

    # Forward-fill to hold between execs
    activated = activated.ffill().fillna(0.0)
    return activated


def vol_target_positions(
    raw_pos: pd.Series,
    px: pd.Series,
    ann_target: float = 0.10,
    lookback_days: int = 21,
    lev_cap: float = 2.5
) -> pd.Series:
    """
    Scale raw discrete signal to hit annual vol target on a rolling basis.
    pos_t = raw_t * min(lev_cap, target / (rolling_vol_d * sqrt(252)))
    """
    ret_d = daily_log_returns(px).fillna(0.0)
    # Rolling daily vol of the underlying
    vol_d = ret_d.rolling(lookback_days, min_periods=lookback_days).std(ddof=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        lev = ann_target / (vol_d * np.sqrt(252.0))
    lev = lev.clip(upper=lev_cap)
    lev = lev.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return (raw_pos * lev).fillna(0.0)


def pnl_with_costs(px: pd.Series, pos: pd.Series, one_way_bps: float = 1.5) -> pd.DataFrame:
    """
    pnl_t = pos_{t-1} * ret_t  -  cost_per_turnover
    turnover_t = |pos_t - pos_{t-1}|
    cost_t = (one_way_bps * 1e-4) * turnover_t
    """
    ret = daily_log_returns(px).fillna(0.0)
    pos_lag = pos.shift(1).fillna(0.0)

    pnl_gross = pos_lag * ret
    turnover = (pos - pos.shift(1)).abs().fillna(0.0)
    cost = (one_way_bps * 1e-4) * turnover

    pnl_net = pnl_gross - cost
    return pd.DataFrame({
        "ret": ret,
        "pos": pos,
        "pos_lag": pos_lag,
        "turnover": turnover,
        "cost": cost,
        "pnl_gross": pnl_gross,
        "pnl_net": pnl_net,
    })


# ----------------------------
# HookCore v0.4.0 (config-driven)
# ----------------------------
def run_hookcore_v040(prices_wide: pd.DataFrame, cfg: dict, global_cfg: dict, out_root: Path, symbol: str):
    """
    - Equal-weight of 3d & 5d z-returns
    - Discrete ±1/0 with threshold (default 0.75)
    - Bi-weekly execution (Mon uses Fri; Wed uses Tue)
    - T+1 positions
    - 10% vol target, 21d, cap 2.5x
    - 1.5 bps one-way costs
    """
    # Read global
    ann_target = float(global_cfg.get("vol_target_annual", 0.10))
    lookback_days = int(global_cfg.get("vol_lookback_days", 21))
    lev_cap = float(global_cfg.get("leverage_cap", 2.5))
    one_way_bps = float(global_cfg.get("cost_bps_per_turnover", 1.5))

    # Sleeve params
    thr = float(cfg.get("signals", {}).get("threshold", 0.75))
    use_weekly_backup = bool(cfg.get("signals", {}).get("weekly_backup", False))
    weekly_thr = float(cfg.get("signals", {}).get("weekly_threshold", 0.85))

    # Get price series
    if symbol not in prices_wide.columns:
        raise ValueError(f"Symbol '{symbol}' not found in price data columns: {list(prices_wide.columns)[:5]}...")
    px = prices_wide[symbol].dropna().sort_index()

    # Build z-returns
    z3 = z_of_hday_return(px, 3)
    z5 = z_of_hday_return(px, 5)
    z_eq = (z3 + z5) / 2.0

    # Discrete raw hook (mean reversion)
    raw_sig = discrete_hook_from_z(z_eq, threshold=thr)

    # Optional weekly-backup variant: if specified in YAML, override on Fridays (example)
    if use_weekly_backup:
        week_mask = (raw_sig.index.weekday == 4)  # Fri
        weekly_sig = discrete_hook_from_z(z_eq, threshold=weekly_thr)
        raw_sig.loc[week_mask] = weekly_sig.loc[week_mask]

    # Apply bi-weekly execution calendar
    exec_sig = apply_trade_calendar(raw_sig)

    # T+1 execution: positions are the executed signal, shifted by 1 day
    pos_raw_t1 = exec_sig.shift(1).fillna(0.0)

    # Vol targeting
    pos_vt = vol_target_positions(
        raw_pos=pos_raw_t1,
        px=px,
        ann_target=ann_target,
        lookback_days=lookback_days,
        lev_cap=lev_cap
    )

    # PnL with costs
    pnl_df = pnl_with_costs(px=px, pos=pos_vt, one_way_bps=one_way_bps)

    # Output
    out_dir = out_root / "copper" / "pricing" / "hookcore_v0_4_0"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Align indexes for tidy outputs
    signals = pd.DataFrame({
        "signal_raw": raw_sig,
        "signal_exec": exec_sig,
        "position_raw_t1": pos_raw_t1,
        "position_vt": pos_vt
    }).dropna(how="all")

    signals.to_csv(out_dir / "signals.csv", index_label="dt")
    pnl_df.to_csv(out_dir / "pnl_daily.csv", index_label="dt")

    # Simple summary
    oos_start = pd.to_datetime(cfg.get("sample", {}).get("out_of_sample_start", "2018-01-01"))
    oos = pnl_df.loc[pnl_df.index >= oos_start, "pnl_net"]
    is_ = pnl_df.loc[pnl_df.index < oos_start, "pnl_net"]

    def ann_stats(x: pd.Series) -> dict:
        mu = x.mean() * 252
        sd = x.std(ddof=0) * np.sqrt(252)
        sharpe = np.nan if sd == 0 or np.isnan(sd) else mu / sd
        return {"ann_mu": mu, "ann_vol": sd, "sharpe": sharpe}

    summary = {
        "symbol": symbol,
        "global": {
            "target": ann_target,
            "lookback_days": lookback_days,
            "lev_cap": lev_cap,
            "cost_bps": one_way_bps
        },
        "sleeve": {
            "threshold": thr,
            "weekly_backup": use_weekly_backup,
            "weekly_threshold": weekly_thr
        },
        "IS": ann_stats(is_),
        "OOS": ann_stats(oos),
        "rows": len(pnl_df)
    }
    pd.Series(summary).to_json(out_dir / "summary.json", indent=2)
    print(f"[HookCore v0.4.0] Wrote outputs → {out_dir}")


# ----------------------------
# Legacy simple signals path (kept intact)
# ----------------------------
def run_legacy_signals(db: str, outdir: str):
    Path(outdir).mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    px = pd.read_sql_query("SELECT dt, symbol, px_settle FROM prices", con, parse_dates=["dt"])
    con.close()

    wide = px.pivot(index="dt", columns="symbol", values="px_settle").sort_index()

    def mom(series, lb=20):
        return series.pct_change(lb)

    def hook(series, fast=5, slow=20):
        f = series.pct_change(fast)
        s = series.pct_change(slow)
        return f - s

    signals = {}
    for col in wide.columns:
        s = wide[col]
        signals[(col, "mom_20")] = mom(s, 20)
        signals[(col, "hook_5_20")] = hook(s, 5, 20)

    out = []
    for (sym, name), ser in signals.items():
        tmp = ser.rename("value").to_frame()
        tmp["symbol"] = sym
        tmp["signal"] = name
        out.append(tmp.reset_index())

    sig = pd.concat(out, ignore_index=True).dropna()
    sig = sig.sort_values(["dt", "symbol", "signal"])

    out_path = Path(outdir) / "signals_export.csv"
    sig.to_csv(out_path, index=False)
    print(f"Wrote {len(sig):,} signal rows → {out_path}")


# ----------------------------
# Main
# ----------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", help="Path to SQLite DB with prices(dt,symbol,px_settle)")
    parser.add_argument("--outdir", required=True, help="Output root folder")
    parser.add_argument("--global", dest="global_cfg", help="Path to config/global.yaml (for config-driven)")
    parser.add_argument("--sleeve-config", dest="sleeve_cfg", help="Path to single sleeve YAML")
    parser.add_argument("--params", dest="params", help="Path to registry YAML (build all sleeves)")
    parser.add_argument("--symbol", help="Symbol to run (for HookCore); defaults to first column if omitted")
    args = parser.parse_args()

    # If no config path is provided, run legacy mode (exactly as your original script)
    if not args.global_cfg and not args.sleeve_cfg and not args.params:
        if not args.db:
            print("ERROR: --db is required for legacy mode.", file=sys.stderr)
            sys.exit(2)
        run_legacy_signals(db=args.db, outdir=args.outdir)
        return

    # Config-driven path
    if yaml is None:
        print("ERROR: pyyaml not installed. pip install pyyaml", file=sys.stderr)
        sys.exit(2)

    # Global config (with sensible defaults if fields missing)
    if args.global_cfg and os.path.exists(args.global_cfg):
        with open(args.global_cfg, "r", encoding="utf-8") as f:
            gcfg = yaml.safe_load(f) or {}
    else:
        gcfg = {}
    # Map expected keys
    gcfg = {
        "vol_target_annual": gcfg.get("vol_target_annual", 0.10),
        "vol_lookback_days": gcfg.get("vol_lookback_days", 21),
        "leverage_cap": gcfg.get("leverage_cap", 2.5),
        "cost_bps_per_turnover": gcfg.get("cost_bps_per_turnover", 1.5),
    }

    if not args.db:
        print("ERROR: --db is required for config-driven mode (to load prices).", file=sys.stderr)
        sys.exit(2)

    prices_wide = load_prices_sqlite(args.db)

    # Helper to choose a default symbol (first column) if not provided
    symbol = args.symbol or (prices_wide.columns[0] if len(prices_wide.columns) else None)
    if symbol is None:
        raise ValueError("No symbols found in price data.")

    out_root = Path(args.outdir)

    if args.params:
        with open(args.params, "r", encoding="utf-8") as f:
            reg = yaml.safe_load(f) or {}
        sleeves = reg.get("copper", {}).get("sleeves", {})
        for name, path in sleeves.items():
            print(f"\n▶ Running sleeve: {name} ({path})")
            with open(path, "r", encoding="utf-8") as sf:
                scfg = yaml.safe_load(sf) or {}
            # Very simple router — here we detect HookCore by sleeve name or path
            sleeve_name = scfg.get("sleeve", "") or name
            if "hook" in sleeve_name or "pricing/hookcore" in path:
                run_hookcore_v040(prices_wide, scfg, gcfg, out_root, symbol)
            else:
                print(f"  (No runner implemented for {name} yet; skipping)")
        return

    if args.sleeve_cfg:
        with open(args.sleeve_cfg, "r", encoding="utf-8") as f:
            scfg = yaml.safe_load(f) or {}
        sleeve_name = scfg.get("sleeve", "")
        if "hook" in sleeve_name:
            run_hookcore_v040(prices_wide, scfg, gcfg, out_root, symbol)
        else:
            raise NotImplementedError(f"No runner implemented for sleeve '{sleeve_name}'.")
        return


if __name__ == "__main__":
    main()
