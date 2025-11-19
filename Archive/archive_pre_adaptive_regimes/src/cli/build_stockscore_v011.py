# --- Policy header (paste near the top of each build_*.py) ---
from utils.policy import load_execution_policy, policy_banner, warn_if_mismatch
import yaml

# >>> EDIT ME per sleeve <<<
SLEEVE_NAME = (
    "Stockscore"  # e.g., "TrendCore", "TrendImpulse", "HookCore", "StocksScore"
)
CONFIG_PATH = "Docs/Copper/stocks/config.yaml"  # path to THIS sleeve's YAML

POLICY = load_execution_policy()
print(policy_banner(POLICY, sleeve_name=SLEEVE_NAME))


# Read this sleeve's actual execution setup from its YAML
def _read_exec_days(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            y = yaml.safe_load(f) or {}
        ex = y.get("execution") or {}
        if ex.get("event_driven", False):
            return None  # skip weekday check for event-driven sleeves
        return tuple(ex.get("exec_weekdays", (0, 2, 4)))
    except FileNotFoundError:
        # If the sleeve has no YAML yet, fall back to project default
        return (0, 2, 4)


_exec_days = _read_exec_days(CONFIG_PATH)

# Warn if this script’s assumptions diverge from project policy
if _exec_days is None:
    # event-driven: don't pass exec_weekdays
    msgs = warn_if_mismatch(
        POLICY,
        fill_timing="close_T",
        vol_info="T",
        leverage_cap=2.5,
        one_way_bps=1.5,
    )
else:
    msgs = warn_if_mismatch(
        POLICY,
        exec_weekdays=_exec_days,
        fill_timing="close_T",
        vol_info="T",
        leverage_cap=2.5,
        one_way_bps=1.5,
    )

for _m in msgs:
    print(_m)
# --- end policy header ---

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copper StocksCore v0.1.1 builder (standalone)

Signal: z20(Δ total LME stocks), threshold = 1.0 → {+1, 0, -1}
Exec: daily; positions trade T+1
Risk: 10% annual vol target (21d), leverage cap 2.5×
Costs: 1.5 bps per one-way turnover

Inputs (from YAML):
- stocks Excel path + columns for Date and total stocks
- price source for PnL/VT (SQLite prices table OR Excel with price column)

Outputs:
- daily_series.csv         (signals, positions, returns, PnL, costs)
- equity_curves.csv        (all / IS / OOS)
- annual_returns.csv       (calendar-year PnL)
- summary_metrics.csv      (IS/OOS Sharpe, DD, cumRet, etc.)
"""

import argparse, sqlite3, sys
from pathlib import Path
import numpy as np
import pandas as pd
import yaml

# ----------------------- helpers -----------------------


def as_bday(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    return df.sort_values(date_col).set_index(date_col).asfreq("B").ffill()


def daily_log_returns(px: pd.Series) -> pd.Series:
    return np.log(px).diff()


def vol_target_positions(
    raw_pos: pd.Series, px: pd.Series, ann_target=0.10, lookback_days=21, lev_cap=2.5
) -> pd.Series:
    ret = daily_log_returns(px)
    vol_d = ret.rolling(lookback_days, min_periods=lookback_days).std(ddof=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        lev = ann_target / (vol_d * np.sqrt(252.0))
    lev = lev.clip(upper=lev_cap)
    lev = lev.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return (raw_pos.fillna(0.0) * lev).fillna(0.0)


def pnl_with_costs_Tplus1(
    px: pd.Series, pos_Tplus1: pd.Series, one_way_bps=1.5
) -> pd.DataFrame:
    ret = daily_log_returns(px).fillna(0.0)
    pos = pos_Tplus1.fillna(0.0)
    turnover = (pos - pos.shift(1)).abs().fillna(0.0)
    cost = (one_way_bps * 1e-4) * turnover
    pnl_gross = pos * ret
    pnl_net = pnl_gross - cost
    return pd.DataFrame(
        {
            "ret": ret,
            "pos": pos,
            "turnover": turnover,
            "cost": cost,
            "pnl_gross": pnl_gross,
            "pnl_net": pnl_net,
        }
    )


def max_drawdown(curve: pd.Series) -> float:
    peak = curve.cummax()
    dd = curve - peak
    return float(-dd.min()) if len(dd) else float("nan")


def ann_metrics(pnl: pd.Series):
    mu = pnl.mean() * 252
    vol = pnl.std(ddof=0) * np.sqrt(252)
    sharpe = (mu / vol) if vol else np.nan
    eq = pnl.cumsum()
    mdd = max_drawdown(eq)
    cum = float(eq.iloc[-1]) if len(eq) else np.nan
    return mu, vol, sharpe, mdd, cum


# ----------------------- loaders -----------------------


def load_price_from_sqlite(db_path: Path, symbol: str) -> pd.Series:
    con = sqlite3.connect(str(db_path))
    try:
        df = pd.read_sql_query(
            "SELECT dt, symbol, px_settle FROM prices WHERE symbol = ? ORDER BY dt",
            con,
            params=(symbol,),
            parse_dates=["dt"],
        )
    finally:
        con.close()
    if df.empty:
        raise FileNotFoundError(f"No rows in {db_path} for symbol={symbol}")
    s = (
        df.pivot(index="dt", columns="symbol", values="px_settle")
        .iloc[:, 0]
        .astype(float)
    )
    return s.asfreq("B").ffill()


def load_price_from_excel(
    path: Path, sheet: str, date_col: str, price_col: str
) -> pd.Series:
    df = pd.read_excel(path, sheet_name=sheet)
    df = as_bday(df, date_col)
    s = df[price_col].astype(float)
    return s.asfreq("B").ffill()


def load_stocks_excel(
    path: Path, sheet: str, date_col: str, total_col: str
) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet)
    df = as_bday(df, date_col)
    if total_col not in df.columns:
        raise KeyError(
            f"'{total_col}' not found in stocks sheet. Columns: {list(df.columns)}"
        )
    return df


# ----------------------- main build -----------------------


def run_stockscore_v011(cfg: dict, out_root: Path):
    # ---- Inputs: stocks
    inp = cfg["inputs"]
    stocks = load_stocks_excel(
        Path(inp["file"]),
        inp.get("sheet", "Sheet1"),
        inp.get("date_col", "Date"),
        inp["fields"]["total"],
    )
    total_col = inp["fields"]["total"]
    stocks["d_total"] = stocks[total_col].diff()

    # ---- Price for VT/PnL (signal does NOT use price)
    price_cfg = cfg.get("price", {})
    if "table" in price_cfg or "symbol" in price_cfg:
        db_path = Path(cfg.get("db_path", "data/quant.db"))
        px = load_price_from_sqlite(db_path, price_cfg["symbol"])
    else:
        # Excel route if provided
        px = load_price_from_excel(
            Path(price_cfg["file"]),
            price_cfg.get("sheet", "Raw"),
            price_cfg.get("date_col", "Date"),
            price_cfg.get("price_col", "copper_lme_3mo"),
        )

    # Align indexes
    idx = stocks.index.union(px.index)
    stocks = stocks.reindex(idx).ffill()
    px = px.reindex(idx).ffill()

    # ---- Params
    sig_cfg = cfg.get("signals", {}).get("components", [{}])[0]
    lookback = int(sig_cfg.get("lookback", 20))
    thr = float(sig_cfg.get("threshold", 1.0))
    vt = float(cfg.get("risk", {}).get("vol_target", {}).get("annual", 0.10))
    vt_lb = int(cfg.get("risk", {}).get("vol_target", {}).get("lookback_days", 21))
    lev_cap = float(cfg.get("risk", {}).get("vol_target", {}).get("leverage_cap", 2.5))
    cost_bps = float(cfg.get("risk", {}).get("costs", {}).get("turnover_bps", 1.5))

    # ---- Signal: z(Δstocks) with 20d window by default
    d = stocks["d_total"]
    mu = d.rolling(lookback, min_periods=lookback).mean()
    sd = d.rolling(lookback, min_periods=lookback).std(ddof=0)
    z = (d - mu) / sd

    # discretise: large draws (z<=-thr) → +1; large builds (z>=+thr) → -1; else 0
    signal_raw = pd.Series(0.0, index=z.index)
    signal_raw[z <= -thr] = 1.0
    signal_raw[z >= thr] = -1.0

    # Exec: daily; T+1
    signal_exec = signal_raw.copy()
    pos_Tplus1 = signal_exec.shift(1)

    # Vol targeting + PnL
    pos_vt = vol_target_positions(
        pos_Tplus1, px, ann_target=vt, lookback_days=vt_lb, lev_cap=lev_cap
    )
    pnl_df = pnl_with_costs_Tplus1(px, pos_vt, one_way_bps=cost_bps)

    # ---- Outputs
    out_root.mkdir(parents=True, exist_ok=True)

    # 1) Daily series
    daily = pd.DataFrame(
        {
            "signal_raw": signal_raw,
            "signal_exec": signal_exec,
            "position_Tplus1": pos_Tplus1,
            "position_vt": pos_vt,
            "ret": pnl_df["ret"],
            "turnover": pnl_df["turnover"],
            "cost": pnl_df["cost"],
            "pnl_gross": pnl_df["pnl_gross"],
            "pnl_net": pnl_df["pnl_net"],
        }
    )
    daily_path = out_root / "daily_series.csv"
    daily.to_csv(daily_path, index_label="dt")

    # 2) Equity curves
    oos_start = pd.Timestamp(
        cfg.get("sample", {}).get("out_of_sample_start", "2018-01-01")
    )
    eq_all = daily["pnl_net"].cumsum()
    eq_is = daily.loc[daily.index < oos_start, "pnl_net"].cumsum()
    eq_oos = daily.loc[daily.index >= oos_start, "pnl_net"].cumsum()
    eq = pd.DataFrame({"equity_all": eq_all})
    eq["equity_is"] = eq_is.reindex(eq.index)
    eq["equity_oos"] = eq_oos.reindex(eq.index)
    (out_root / "equity_curves.csv").write_text(eq.to_csv(index_label="dt"))

    # 3) Annual returns
    ann = daily["pnl_net"].groupby(daily.index.year).sum().rename("annual_return")
    ann_df = ann.to_frame()
    (out_root / "annual_returns.csv").write_text(ann_df.to_csv(index_label="year"))

    # 4) Summary metrics
    is_mu, is_vol, is_sh, is_mdd, is_cum = ann_metrics(
        daily.loc[daily.index < oos_start, "pnl_net"]
    )
    oos_mu, oos_vol, oos_sh, oos_mdd, oos_cum = ann_metrics(
        daily.loc[daily.index >= oos_start, "pnl_net"]
    )
    summary = pd.DataFrame(
        [
            {
                "sleeve": "StocksCore v0.1.1",
                "lookback": lookback,
                "threshold": thr,
                "exec": "daily, T+1",
                "vol_target_annual": vt,
                "vol_lookback_days": vt_lb,
                "leverage_cap": lev_cap,
                "costs_bps_turnover": cost_bps,
                "IS_ann_return": is_mu,
                "IS_ann_vol": is_vol,
                "IS_sharpe": is_sh,
                "IS_maxDD": is_mdd,
                "IS_cumRet": is_cum,
                "OOS_ann_return": oos_mu,
                "OOS_ann_vol": oos_vol,
                "OOS_sharpe": oos_sh,
                "OOS_maxDD": oos_mdd,
                "OOS_cumRet": oos_cum,
                "start": str(daily.index.min().date()),
                "end": str(daily.index.max().date()),
            }
        ]
    )
    (out_root / "summary_metrics.csv").write_text(summary.to_csv(index=False))

    print(
        f"[OK] Wrote:\n - {daily_path}\n - {out_root/'equity_curves.csv'}\n - {out_root/'annual_returns.csv'}\n - {out_root/'summary_metrics.csv'}"
    )


# ----------------------- CLI -----------------------


def main():
    ap = argparse.ArgumentParser(
        description="Build Copper StocksCore v0.1.1 (Δstocks z20, thr=1.0)"
    )
    ap.add_argument(
        "--config",
        required=True,
        help="YAML: docs/copper/stocks/stockscore_config.yaml",
    )
    ap.add_argument(
        "--db", required=False, help="SQLite DB path (if using price.table)"
    )
    ap.add_argument("--outdir", required=False, help="Override outputs.root")
    args = ap.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if args.db:
        cfg["db_path"] = args.db

    # default outputs root if not in YAML
    out_root = Path(
        cfg.get("outputs", {}).get("root", "outputs/copper/stocks/stockscore_v0_1_1")
    )
    if args.outdir:
        out_root = Path(args.outdir)

    run_stockscore_v011(cfg, out_root)


if __name__ == "__main__":
    main()
