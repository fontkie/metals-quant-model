# --- Policy header (paste near the top of each build_*.py) ---
from __future__ import annotations
from utils.policy import load_execution_policy, policy_banner, warn_if_mismatch
import yaml

# >>> EDIT ME per sleeve <<<
SLEEVE_NAME = (
    "TrendCore"  # e.g., "TrendCore", "TrendImpulse", "HookCore", "StocksScore"
)
CONFIG_PATH = "docs/copper/trendcore_config.yaml"  # path to THIS sleeve's YAML

POLICY = load_execution_policy()
print(policy_banner(POLICY, sleeve_name=SLEEVE_NAME))


def _read_exec_days(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            y = yaml.safe_load(f) or {}
        run = y.get("run") or {}
        cad = (run.get("cadence") or "").lower()
        if cad == "monwed":
            return (0, 2)
        if cad == "tuefri":
            return (1, 4)
        # default Mon/Wed
        return (0, 2)
    except FileNotFoundError:
        return (0, 2)


_exec_days = _read_exec_days(CONFIG_PATH)

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


#!/usr/bin/env python
# TrendCore — Copper (T-close execution, price-level z)
# Mon/Wed exec, fill at same-day close (T), PnL from T+1
# Vol targeting 10% (28d), no look-ahead beyond T
# Costs: 1.5 bps per |Δpos| on trade days
# PnL: pos_{t-1} * simple_return_t

import argparse, json
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay


# ---------- IO ----------


def load_prices_excel(path, sheet, date_col, price_col, symbol) -> pd.Series:
    df = pd.read_excel(path, sheet_name=sheet, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns={date_col: "dt", price_col: symbol})[["dt", symbol]]
    df["dt"] = pd.to_datetime(df["dt"])
    df = (
        df.dropna()
        .sort_values("dt")
        .drop_duplicates("dt")
        .set_index("dt")
        .asfreq("B")
        .ffill()
    )
    return df[symbol].rename(symbol)


# ---------- Signal maths (price-level z) ----------


def price_level_z(px: pd.Series, lb: int = 252) -> pd.Series:
    logp = np.log(px)
    mu = logp.rolling(lb, min_periods=lb).mean()
    sd = logp.rolling(lb, min_periods=lb).std(ddof=0)
    return (logp - mu) / sd.replace(0.0, np.nan)


def trend_signal_from_z(z: pd.Series, threshold: float) -> pd.Series:
    s = pd.Series(0.0, index=z.index, dtype=float)
    s[z >= threshold] = 1.0
    s[z <= -threshold] = -1.0
    return s


# ---------- Exec calendar (Mon/Wed close; use Fri/Tue origins for stability) ----------


def biweekly_exec_origin(idx: pd.DatetimeIndex) -> pd.Series:
    wk = idx.weekday
    origin = pd.Series(pd.NaT, index=idx, dtype="datetime64[ns]")
    origin.loc[wk == 0] = (idx[wk == 0] - BDay(3)).values  # Mon uses Fri
    origin.loc[wk == 2] = (idx[wk == 2] - BDay(1)).values  # Wed uses Tue
    return origin


def apply_exec_calendar(raw_sig: pd.Series) -> pd.Series:
    idx = raw_sig.index
    origin_map = biweekly_exec_origin(idx)
    exec_only = pd.Series(np.nan, index=idx, dtype=float)
    for d, od in origin_map.dropna().items():
        if od not in raw_sig.index:
            pos = raw_sig.index.searchsorted(od, side="right") - 1
            if pos < 0:
                continue
            od = raw_sig.index[pos]
        exec_only.loc[d] = raw_sig.loc[od]
    return exec_only.ffill().fillna(0.0)


# ---------- Vol targeting (T-close) ----------


def realized_vol_annual_simple(px: pd.Series, lookback_days: int) -> pd.Series:
    ret = px.pct_change()
    vol = ret.rolling(lookback_days, min_periods=lookback_days).std(ddof=0) * np.sqrt(
        252.0
    )
    return vol


def size_on_exec_days_Tclose(
    exec_sig: pd.Series,
    px: pd.Series,
    ann_target: float = 0.10,
    lookback_days: int = 28,
    lev_cap: float = 2.5,
) -> pd.Series:
    vol_ann = realized_vol_annual_simple(px, lookback_days).replace(0.0, np.nan)

    idx = exec_sig.index
    wk = idx.weekday
    exec_mask = (wk == 0) | (wk == 2)  # Mon/Wed
    exec_dates = idx[exec_mask]

    lev_on_exec = (ann_target / vol_ann.reindex(exec_dates)).clip(upper=lev_cap)
    lev_series = pd.Series(np.nan, index=idx, dtype=float)
    lev_series.loc[exec_dates] = lev_on_exec.values
    lev_series = lev_series.ffill()

    pos = exec_sig * lev_series
    pos = pos.where(~lev_series.isna(), 0.0)
    return pos


# ---------- PnL with costs ----------


def pnl_with_costs(
    px: pd.Series, pos: pd.Series, one_way_bps: float = 1.5
) -> pd.DataFrame:
    ret = px.pct_change().fillna(0.0)
    pos_lag = pos.shift(1).fillna(0.0)
    pnl_gross = pos_lag * ret
    turnover = (pos - pos.shift(1)).abs().fillna(0.0)
    cost = (one_way_bps * 1e-4) * turnover
    pnl_net = pnl_gross - cost
    return pd.DataFrame(
        {
            "ret": ret,
            "pos": pos,
            "pos_lag": pos_lag,
            "turnover": turnover,
            "cost": cost,
            "pnl_gross": pnl_gross,
            "pnl_net": pnl_net,
        }
    )


# ---------- Runner ----------


def run_trendcore(
    px: pd.Series,
    threshold: float = 0.60,  # default updated from 0.85 → 0.60
    z_std_lb: int = 252,
    vol_lookback_days: int = 28,
    lev_cap: float = 2.5,
    one_way_bps: float = 1.5,
):
    z = price_level_z(px, lb=z_std_lb)
    raw = trend_signal_from_z(z, threshold=threshold)

    exec_sig = apply_exec_calendar(raw)  # Mon/Wed values held between rebalances
    pos = size_on_exec_days_Tclose(
        exec_sig, px, ann_target=0.10, lookback_days=vol_lookback_days, lev_cap=lev_cap
    )
    pnl = pnl_with_costs(px, pos, one_way_bps=one_way_bps)

    signals = pd.DataFrame(
        {"z": z, "signal_raw": raw, "signal_exec": exec_sig, "position_vt": pos}
    )
    return signals, pnl


def sharpe_252(s: pd.Series) -> float:
    s = s.dropna()
    sd = s.std(ddof=0)
    return float("nan") if sd == 0 else float((s.mean() / sd) * np.sqrt(252.0))


def main():
    ap = argparse.ArgumentParser(
        description="Build TrendCore (Copper) — T-close execution, price-level z."
    )
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default="Raw")
    ap.add_argument("--date-col", default="Date")
    ap.add_argument("--price-col", default="copper_lme_3mo")
    ap.add_argument("--symbol", default="COPPER")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--oos-start", default="2018-01-01")

    # Params
    ap.add_argument("--threshold", type=float, default=0.60)  # updated default
    ap.add_argument("--z-std-lb", type=int, default=252)
    ap.add_argument("--vol-lookback", type=int, default=28)
    ap.add_argument("--lev-cap", type=float, default=2.5)
    ap.add_argument("--bps", type=float, default=1.5)

    # Policy path (for banner/mismatch warnings)
    ap.add_argument("--schema-path", default="Config/schema.yaml")

    args = ap.parse_args()

    policy = load_execution_policy(args.schema_path)
    print(policy_banner(policy, sleeve_name="TrendCore-Cu-v1.2-Tclose"))
    for w in warn_if_mismatch(
        policy,
        exec_weekdays=(0, 2),
        fill_timing="close_T",
        vol_info="T",
        leverage_cap=args.lev_cap,
        one_way_bps=args.bps,
    ):
        print(w)

    px = load_prices_excel(
        args.excel, args.sheet, args.date_col, args.price_col, args.symbol
    )
    signals, pnl = run_trendcore(
        px=px,
        threshold=args.threshold,
        z_std_lb=args.z_std_lb,
        vol_lookback_days=args.vol_lookback,
        lev_cap=args.lev_cap,
        one_way_bps=args.bps,
    )

    out_root = Path(args.outdir) / "copper" / "pricing" / "trendcore_single_Tclose"
    out_root.mkdir(parents=True, exist_ok=True)
    signals.to_csv(out_root / "signals.csv", index_label="dt")
    pnl.to_csv(out_root / "pnl_daily.csv", index_label="dt")

    oos_start = pd.Timestamp(args.oos_start)
    is_pnl = pnl.loc[pnl.index < oos_start, "pnl_net"].dropna()
    oos_pnl = pnl.loc[pnl.index >= oos_start, "pnl_net"].dropna()

    summary = {
        "params": {
            "threshold": args.threshold,
            "z_std_lb": args.z_std_lb,
            "vol_lookback_days": args.vol_lookback,
            "lev_cap": args.lev_cap,
            "bps": args.bps,
            "ann_target": 0.10,
            "execution": "Mon/Wed close (T); PnL next day",
        },
        "IS": {"sharpe_252": sharpe_252(is_pnl), "n": int(is_pnl.size)},
        "OOS": {"sharpe_252": sharpe_252(oos_pnl), "n": int(oos_pnl.size)},
    }
    with open(out_root / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"[trendcore] wrote → {out_root}")


if __name__ == "__main__":
    main()
