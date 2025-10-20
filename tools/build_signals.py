# build_signals.py — HookCore v0.4.0 (parity-fixed)

import sys, hashlib, pathlib

if any(a in sys.argv for a in ["--banner", "--version", "-V"]):
    p = pathlib.Path(__file__)
    print(f"[build_signals] file = {p}")
    print(f"[build_signals] sha256 = {hashlib.sha256(p.read_bytes()).hexdigest()[:16]}")
    sys.exit(0)

import argparse
import itertools
import json
import os
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay


# -------------------------
# Data loaders
# -------------------------


def load_prices_sqlite(db_path: str) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(
            "SELECT dt, symbol, px_settle FROM prices", con, parse_dates=["dt"]
        )
    finally:
        con.close()
    if df.empty:
        raise ValueError("No rows found in prices table.")
    df = df.sort_values(["dt", "symbol"])
    wide = df.pivot(index="dt", columns="symbol", values="px_settle").sort_index()
    wide.index = pd.DatetimeIndex(wide.index).tz_localize(None)
    return wide.asfreq("B").ffill()


def load_prices_excel(
    path: str, sheet: str, date_col: str, price_col: str, symbol: str
) -> pd.Series:
    df = pd.read_excel(path, sheet_name=sheet, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns={date_col: "dt", price_col: symbol})[["dt", symbol]]
    df["dt"] = pd.to_datetime(df["dt"])
    df = df.dropna().sort_values("dt").drop_duplicates("dt").set_index("dt")
    df.index = pd.DatetimeIndex(df.index).tz_localize(None)
    df = df.asfreq("B").ffill()
    return df[symbol].rename(symbol)


# -------------------------
# Signal maths
# -------------------------


def daily_log_returns(px: pd.Series) -> pd.Series:
    return np.log(px).diff()


def daily_simple_returns(px: pd.Series) -> pd.Series:
    return px.pct_change()


def hday_log_return(px: pd.Series, h: int) -> pd.Series:
    return np.log(px / px.shift(h))


def z_of_hday_return(
    px: pd.Series, h: int, stdev_lb: int = 252, minp: int | None = None
) -> pd.Series:
    """
    Parity fix: require the *same* warm-up as stdev_lb so early z's do not start at 60d.
    """
    if minp is None:
        minp = stdev_lb
    r_h = hday_log_return(px, h)
    sd_h = r_h.rolling(window=stdev_lb, min_periods=minp).std(ddof=0)
    return r_h / sd_h.replace(0.0, np.nan)


def discrete_hook_from_z(z: pd.Series, threshold: float) -> pd.Series:
    s = pd.Series(0.0, index=z.index, dtype=float)
    s[z >= threshold] = -1.0
    s[z <= -threshold] = 1.0
    return s


# -------------------------
# Execution calendar
# -------------------------


def biweekly_exec_origin(idx: pd.DatetimeIndex) -> pd.Series:
    """
    Calendar:
      - Monday executes Friday origin (Mon uses Fri_close signal)
      - Wednesday executes Tuesday origin (Wed uses Tue_close signal)
    """
    weekday = idx.weekday
    origin = pd.Series(pd.NaT, index=idx, dtype="datetime64[ns]")
    mon = weekday == 0
    wed = weekday == 2
    origin.loc[mon] = (idx[mon] - BDay(3)).values  # Fri
    origin.loc[wed] = (idx[wed] - BDay(1)).values  # Tue
    return origin


def apply_trade_calendar(raw_signal: pd.Series) -> pd.Series:
    """
    Activate only on Mon/Wed (mapped from Fri/Tue origins), then *hold* between rebalances.
    If an origin is a holiday, fall back to the nearest prior business day.
    """
    idx = raw_signal.index
    origin_map = biweekly_exec_origin(idx)
    activated = pd.Series(np.nan, index=idx, dtype=float)
    exec_days = origin_map.dropna().index
    for d in exec_days:
        od = origin_map.loc[d]
        if od not in raw_signal.index:
            pos = raw_signal.index.searchsorted(od, side="right") - 1
            if pos < 0:
                continue
            od = raw_signal.index[pos]
        activated.loc[d] = raw_signal.loc[od]
    return activated.ffill().fillna(0.0)


# -------------------------
# Sizing, costs, PnL
# -------------------------


def realized_vol_annual(ret_d: pd.Series, lookback_days: int) -> pd.Series:
    return ret_d.rolling(lookback_days, min_periods=lookback_days).std(
        ddof=0
    ) * np.sqrt(252.0)


def vol_target_positions_exec_only(
    raw_exec_pos_t1: pd.Series,
    px: pd.Series,
    ann_target: float = 0.10,
    lookback_days: int = 21,
    lev_cap: float = 2.5,
    use_log_returns_for_vol: bool = False,
) -> pd.Series:
    ret_d = (
        daily_log_returns(px) if use_log_returns_for_vol else daily_simple_returns(px)
    )
    vol_ann = realized_vol_annual(ret_d.fillna(0.0), lookback_days).replace(0.0, np.nan)

    idx = raw_exec_pos_t1.index
    exec_mask = (idx.weekday == 0) | (idx.weekday == 2)  # Mon/Wed (signal days)
    exec_dates = idx[exec_mask]

    # Compute leverage only on exec dates; no back-fill to the left (parity fix).
    lev_exec = (ann_target / (vol_ann.reindex(exec_dates))).clip(upper=lev_cap)
    lev_series = pd.Series(np.nan, index=idx, dtype=float)
    lev_series.loc[exec_dates] = lev_exec.values
    lev_series = lev_series.ffill()  # <— no bfill

    # Positions are zero until leverage exists; inherit cap from leverage construction.
    pos = raw_exec_pos_t1 * lev_series
    pos = pos.where(~lev_series.isna(), 0.0)
    return pos


def pnl_with_costs(
    px: pd.Series,
    pos: pd.Series,
    one_way_bps: float = 1.5,
    use_log_returns_for_pnl: bool = False,
) -> pd.DataFrame:
    ret = daily_log_returns(px) if use_log_returns_for_pnl else daily_simple_returns(px)
    ret = ret.fillna(0.0)

    # T+1: the *position* changes on fill days (Tue/Thu), so costs are applied there.
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


# -------------------------
# Sleeve runner
# -------------------------


def run_hookcore(
    px: pd.Series,
    threshold: float = 0.75,
    z_std_lb: int = 252,
    ann_target: float = 0.10,
    lookback_days: int = 21,
    lev_cap: float = 2.5,
    one_way_bps: float = 1.5,
    use_log_returns_for_vol: bool = False,
    use_log_returns_for_pnl: bool = False,
    weekly_backup: bool = False,
    weekly_threshold: float = 0.85,
    veto_enabled: bool = False,
    veto_abs_threshold: float = 0.30,
    veto_stdev_lb: int = 100,
):
    # z(3/5) on log returns, equal weight
    z3 = z_of_hday_return(px, 3, stdev_lb=z_std_lb)
    z5 = z_of_hday_return(px, 5, stdev_lb=z_std_lb)
    z_eq = 0.5 * z3 + 0.5 * z5
    raw = discrete_hook_from_z(z_eq, threshold=threshold)

    if weekly_backup:
        weekly = discrete_hook_from_z(z_eq, threshold=weekly_threshold)
        raw.loc[raw.index.weekday == 4] = weekly.loc[raw.index.weekday == 4]

    if veto_enabled:
        z_long = z_of_hday_return(px, 1, stdev_lb=veto_stdev_lb)  # slow-ish proxy
        raw[(z_long.abs() >= veto_abs_threshold)] = 0.0

    exec_sig = apply_trade_calendar(raw)
    pos_raw_t1 = exec_sig.shift(1).fillna(0.0)  # T+1 fills

    pos_vt = vol_target_positions_exec_only(
        raw_exec_pos_t1=pos_raw_t1,
        px=px,
        ann_target=ann_target,
        lookback_days=lookback_days,
        lev_cap=lev_cap,
        use_log_returns_for_vol=use_log_returns_for_vol,
    )

    pnl_df = pnl_with_costs(
        px=px,
        pos=pos_vt,
        one_way_bps=one_way_bps,
        use_log_returns_for_pnl=use_log_returns_for_pnl,
    )

    signals = pd.DataFrame(
        {
            "signal_raw": raw,
            "signal_exec": exec_sig,
            "position_raw_t1": pos_raw_t1,
            "position_vt": pos_vt,
        }
    )
    return signals, pnl_df


# -------------------------
# Metrics & grid engine (unchanged except comments)
# -------------------------


def _sharpe_daily(s: pd.Series) -> float:
    x = s.dropna()
    if x.size < 2:
        return float("nan")
    sd = x.std(ddof=0)
    return float("nan") if sd == 0 else float((x.mean() / sd) * np.sqrt(252.0))


def _sharpe_exec_monwed(daily: pd.Series) -> float:
    idx = daily.index
    exec_days = idx[(idx.weekday == 0) | (idx.weekday == 2)]
    if len(exec_days) < 2:
        return float("nan")
    seg, prev = [], exec_days[0]
    for d in exec_days[1:]:
        i0 = idx.searchsorted(prev, side="left")
        i1 = idx.searchsorted(d, side="right") - 1
        i0 = max(i0, 0)
        i1 = min(i1, len(idx) - 1)
        if i1 >= i0:
            w = daily.iloc[i0 : i1 + 1].fillna(0.0)
            seg.append((1.0 + w).prod() - 1.0)
        prev = d
    x = pd.Series(seg, index=exec_days[1:])
    sd = x.std(ddof=0)
    return float("nan") if sd == 0 else float((x.mean() / sd) * np.sqrt(104.0))


def _max_dd_from_pnl(daily: pd.Series) -> float:
    eq = (1.0 + daily.dropna()).cumprod()
    cummax = np.maximum.accumulate(eq)
    dd = eq / cummax - 1.0
    return float(dd.min() * 100.0)


def _turnover_pa(turn: pd.Series) -> float:
    return float(turn.sum() * (252.0 / max(1, len(turn))))


def _participation(pos: pd.Series) -> float:
    return float((pos != 0.0).mean() * 100.0)


def _avg_holding_days(pos: pd.Series) -> float:
    changes = (pos != pos.shift(1)).fillna(False)
    if changes.sum() <= 1:
        return float("nan")
    runs = np.diff(np.flatnonzero(np.r_[True, changes.values, True])).astype(float)
    return float(np.nanmean(runs))


def _expand_param_grid(sleeve_cfg: dict) -> list[dict]:
    sig = sleeve_cfg.get("signals", {})
    exe = sleeve_cfg.get("execution", {})
    grid_fields = {
        "threshold": sig.get("threshold", 0.75),
        "z_std_lb": sig.get("z_std_lb", 252),
        "veto_enabled": sig.get("veto_enabled", False),
        "veto_abs_threshold": sig.get("veto_abs_threshold", 0.30),
        "veto_stdev_lb": sig.get("veto_stdev_lb", 100),
        "execution.vol_cap": exe.get("vol_cap", 2.5),
        "execution.vol_lookback_days": exe.get("vol_lookback_days", 21),
    }
    lists = {k: (v if isinstance(v, list) else [v]) for k, v in grid_fields.items()}
    keys = list(lists.keys())
    combos = []
    for vals in itertools.product(*[lists[k] for k in keys]):
        d = {k: vals[i] for i, k in enumerate(keys)}
        combos.append(d)
    return combos


def _run_one_combo(
    px: pd.Series, oos_start: pd.Timestamp, params: dict, costs_bps: float
):
    signals, pnl_df = run_hookcore(
        px=px,
        threshold=float(params.get("threshold", 0.75)),
        z_std_lb=int(params.get("z_std_lb", 252)),
        ann_target=0.10,
        lookback_days=int(params.get("execution.vol_lookback_days", 21)),
        lev_cap=float(params.get("execution.vol_cap", 2.5)),
        one_way_bps=float(costs_bps),
        use_log_returns_for_vol=False,
        use_log_returns_for_pnl=False,
        weekly_backup=False,
        veto_enabled=bool(params.get("veto_enabled", False)),
        veto_abs_threshold=float(params.get("veto_abs_threshold", 0.30)),
        veto_stdev_lb=int(params.get("veto_stdev_lb", 100)),
    )

    is_mask = pnl_df.index < oos_start
    oos_mask = pnl_df.index >= oos_start
    is_pnl = pnl_df.loc[is_mask, "pnl_net"]
    oos_pnl = pnl_df.loc[oos_mask, "pnl_net"]
    is_turn = pnl_df.loc[is_mask, "turnover"]
    oos_turn = pnl_df.loc[oos_mask, "turnover"]

    row = {
        "threshold": float(params.get("threshold", 0.75)),
        "z_std_lb": int(params.get("z_std_lb", 252)),
        "veto_enabled": bool(params.get("veto_enabled", False)),
        "veto_abs_threshold": float(params.get("veto_abs_threshold", 0.30)),
        "veto_stdev_lb": int(params.get("veto_stdev_lb", 100)),
        "vol_cap": float(params.get("execution.vol_cap", 2.5)),
        "vol_lookback_days": int(params.get("execution.vol_lookback_days", 21)),
        "IS_sharpe_252": _sharpe_daily(is_pnl),
        "IS_sharpe_104": _sharpe_exec_monwed(is_pnl),
        "IS_ann_vol": float(is_pnl.std(ddof=0) * np.sqrt(252.0)),
        "IS_maxDD_pct": _max_dd_from_pnl(is_pnl),
        "IS_turn_pa": _turnover_pa(is_turn),
        "IS_hit": float((is_pnl > 0).mean() * 100.0),
        "IS_participation_pct": _participation(signals.loc[is_mask, "position_vt"]),
        "IS_avg_hold_days": _avg_holding_days(signals.loc[is_mask, "position_vt"]),
        "OOS_sharpe_252": _sharpe_daily(oos_pnl),
        "OOS_sharpe_104": _sharpe_exec_monwed(oos_pnl),
        "OOS_ann_vol": float(oos_pnl.std(ddof=0) * np.sqrt(252.0)),
        "OOS_maxDD_pct": _max_dd_from_pnl(oos_pnl),
        "OOS_turn_pa": _turnover_pa(oos_turn),
        "OOS_hit": float((oos_pnl > 0).mean() * 100.0),
        "OOS_participation_pct": _participation(signals.loc[oos_mask, "position_vt"]),
        "OOS_avg_hold_days": _avg_holding_days(signals.loc[oos_mask, "position_vt"]),
        "N_IS": int(is_pnl.dropna().shape[0]),
        "N_OOS": int(oos_pnl.dropna().shape[0]),
    }
    return row, signals, pnl_df


# -------------------------
# CLI
# -------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db")
    ap.add_argument("--excel")
    ap.add_argument("--excel-sheet", default="Raw")
    ap.add_argument("--excel-date-col", default="Date")
    ap.add_argument("--excel-price-col", default="copper_lme_3mo")
    ap.add_argument("--symbol", default="COPPER")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--oos-start", default="2018-01-01")

    ap.add_argument("--threshold", type=float, default=0.75)
    ap.add_argument("--z-std-lb", dest="z_std_lb", type=int, default=252)
    ap.add_argument("--ann-target", type=float, default=0.10)
    ap.add_argument("--lookback-days", type=int, default=21)
    ap.add_argument("--lev-cap", type=float, default=2.5)
    ap.add_argument("--bps", type=float, default=1.5)
    ap.add_argument("--log-vol", action="store_true")
    ap.add_argument("--log-pnl", action="store_true")
    ap.add_argument("--weekly-backup", action="store_true")
    ap.add_argument("--weekly-threshold", type=float, default=0.85)
    ap.add_argument("--veto-enabled", action="store_true")
    ap.add_argument("--veto-abs-threshold", type=float, default=0.30)
    ap.add_argument("--veto-stdev-lb", type=int, default=100)

    ap.add_argument("--sleeve-config")
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--save-per-combo", action="store_true")

    args = ap.parse_args()

    if args.excel:
        px = load_prices_excel(
            args.excel,
            args.excel_sheet,
            args.excel_date_col,
            args.excel_price_col,
            args.symbol,
        )
    elif args.db:
        wide = load_prices_sqlite(args.db)
        if args.symbol not in wide.columns:
            raise ValueError(
                f"Symbol '{args.symbol}' not found. Available: {list(wide.columns)[:6]}..."
            )
        px = wide[args.symbol]
    else:
        raise SystemExit("Provide either --excel or --db input.")

    px = px.dropna().sort_index()
    oos_start = pd.Timestamp(args.oos_start)

    if args.grid:
        import yaml

        if not args.sleeve_config:
            raise SystemExit("--grid requires --sleeve-config")
        with open(args.sleeve_config, "r", encoding="utf-8") as f:
            sleeve_cfg = yaml.safe_load(f) or {}
        combos = _expand_param_grid(sleeve_cfg)

        out_root = Path(args.outdir) / "copper" / "pricing" / "hookcore_grid"
        out_root.mkdir(parents=True, exist_ok=True)

        rows = []
        for i, combo in enumerate(combos, 1):
            row, signals, pnl = _run_one_combo(
                px=px,
                oos_start=oos_start,
                params=combo,
                costs_bps=float(
                    sleeve_cfg.get("costs", {}).get("cost_bps_per_turnover", 1.5)
                ),
            )
            row["combo_id"] = i
            rows.append(row)

            if args.save_per_combo:
                sub = out_root / f"combo_{i:02d}"
                sub.mkdir(parents=True, exist_ok=True)
                signals.to_csv(sub / "signals.csv", index_label="dt")
                pnl.to_csv(sub / "pnl_daily.csv", index_label="dt")
                with open(sub / "params.json", "w", encoding="utf-8") as jf:
                    json.dump(combo, jf, indent=2)

        summary = pd.DataFrame(rows)
        summary_cols = [
            "combo_id",
            "threshold",
            "z_std_lb",
            "veto_enabled",
            "veto_abs_threshold",
            "veto_stdev_lb",
            "vol_cap",
            "vol_lookback_days",
            "IS_sharpe_252",
            "IS_sharpe_104",
            "IS_ann_vol",
            "IS_maxDD_pct",
            "IS_turn_pa",
            "IS_hit",
            "IS_participation_pct",
            "IS_avg_hold_days",
            "OOS_sharpe_252",
            "OOS_sharpe_104",
            "OOS_ann_vol",
            "OOS_maxDD_pct",
            "OOS_turn_pa",
            "OOS_hit",
            "OOS_participation_pct",
            "OOS_avg_hold_days",
            "N_IS",
            "N_OOS",
        ]
        summary = summary[summary_cols]
        summary.to_csv(out_root / "grid_summary.csv", index=False)
        print(f"[grid] wrote {len(rows)} combos → {out_root / 'grid_summary.csv'}")
        return

    signals, pnl = run_hookcore(
        px=px,
        threshold=args.threshold,
        z_std_lb=args.z_std_lb,
        ann_target=args.ann_target,
        lookback_days=args.lookback_days,
        lev_cap=args.lev_cap,
        one_way_bps=args.bps,
        use_log_returns_for_vol=args.log_vol,
        use_log_returns_for_pnl=args.log_pnl,
        weekly_backup=args.weekly_backup,
        weekly_threshold=args.weekly_threshold,
        veto_enabled=args.veto_enabled,
        veto_abs_threshold=args.veto_abs_threshold,
        veto_stdev_lb=args.veto_stdev_lb,
    )

    out_root = Path(args.outdir) / "copper" / "pricing" / "hookcore_single"
    out_root.mkdir(parents=True, exist_ok=True)
    signals.to_csv(out_root / "signals.csv", index_label="dt")
    pnl.to_csv(out_root / "pnl_daily.csv", index_label="dt")

    is_pnl = pnl.loc[pnl.index < oos_start, "pnl_net"].dropna()
    oos_pnl = pnl.loc[pnl.index >= oos_start, "pnl_net"].dropna()

    def ann_stats(x: pd.Series) -> dict:
        mu = float(x.mean() * 252.0)
        sd = float(x.std(ddof=0) * np.sqrt(252.0))
        sharpe = (mu / sd) if sd > 0 else float("nan")
        return {"ann_mu": mu, "ann_vol": sd, "sharpe": sharpe, "n": int(x.size)}

    summary = {"IS": ann_stats(is_pnl), "OOS": ann_stats(oos_pnl)}
    with open(out_root / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"[single] wrote → {out_root}")


if __name__ == "__main__":
    main()
