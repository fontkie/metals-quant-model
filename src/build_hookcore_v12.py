import os, json, argparse, math
import pandas as pd
import numpy as np

# ---------------------- v1.2 Defaults (live-safe) ----------------------
DEFAULT_LOW = 30.0
DEFAULT_HIGH = 70.0
DEFAULT_VOLRATIO = 1.20  # 10d/60d realised vol must be < this
DEFAULT_VOL_TARGET = 0.10
DEFAULT_VOL_LB = 28
DEFAULT_LEV_CAP = 2.5
DEFAULT_COST_PER_ABS_DELTA = 0.000015  # 1.5 bps
DEFAULT_HOLD = 3
DEFAULT_EXEC = "T"  # "T" or "next"
DEFAULT_CADENCE = "biweekly"  # "biweekly" (Tue/Fri), "weekly" (Fri), "event"
IS_CUTOFF = pd.Timestamp("2018-01-01")


def rsi(series: pd.Series, window=3):
    delta = series.diff()
    up = delta.clip(lower=0).rolling(window).mean()
    down = (-delta.clip(upper=0)).rolling(window).mean()
    rs = up / down.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def rolling_vol(returns: pd.Series, lb: int = DEFAULT_VOL_LB) -> pd.Series:
    return returns.rolling(lb).std() * np.sqrt(252)


def vol_target_weights(
    raw_ret: pd.Series,
    target_vol=DEFAULT_VOL_TARGET,
    lb=DEFAULT_VOL_LB,
    max_lev=DEFAULT_LEV_CAP,
):
    rv = rolling_vol(raw_ret, lb=lb).replace(0, np.nan)
    w = target_vol / rv
    return w.clip(upper=max_lev).fillna(0.0)


def schedule_mask(idx: pd.DatetimeIndex, schedule: str) -> pd.Series:
    if schedule == "biweekly":
        return pd.Series(idx.weekday, index=idx).isin([1, 4])  # Tue, Fri
    if schedule == "weekly":
        return pd.Series(idx.weekday, index=idx) == 4  # Fri
    return pd.Series(True, index=idx)  # event (always allowed)


def pnl_with_costs(
    ret: pd.Series,
    pos_prev: pd.Series,
    pos: pd.Series,
    cost_per_abs_delta: float,
    is_exec_day: pd.Series,
):
    # Costs only when |Δpos|>0 AND it's an allowed execution day (Tue/Fri, etc)
    delta = (pos - pos_prev).abs()
    cost_mask = (delta > 0) & is_exec_day.fillna(False)
    costs = cost_per_abs_delta * delta.where(cost_mask, 0.0)
    strat_ret = pos_prev * ret - costs
    return strat_ret, costs


def equity_curve(strat_ret: pd.Series):
    return (1 + strat_ret.fillna(0.0)).cumprod()


def max_drawdown(curve: pd.Series):
    peak = curve.cummax()
    dd = curve / peak - 1.0
    return float(dd.min())


def annualise_sharpe(ret: pd.Series):
    m = ret.mean() * 252
    s = ret.std() * math.sqrt(252)
    return 0.0 if (s == 0 or np.isnan(s)) else float(m / s)


def signal_rsi3_cross(price: pd.Series, low_th: float, high_th: float):
    r = rsi(price, 3)
    dr = r.diff()
    cross_up = (r.shift(1) <= low_th) & (r > low_th) & (dr > 0)
    cross_dn = (r.shift(1) >= high_th) & (r < high_th) & (dr < 0)
    sig = pd.Series(0.0, index=price.index)
    sig[cross_up] = 1.0
    sig[cross_dn] = -1.0
    return sig.rename("signal")


def run_strategy(
    df: pd.DataFrame,
    low_th: float,
    high_th: float,
    volratio_cap: float,
    cadence: str,
    exec_mode: str,
    hold_bars: int,
    vol_target: float,
    vol_lb: int,
    lev_cap: float,
    cost_per_abs_delta: float,
):
    idx = df.index
    ret = df["ret"]
    price = df["Price"]

    # Signal
    signal = signal_rsi3_cross(price, low_th, high_th)

    # Vol gate (10d/60d realised). Ratio is unitless, so no annualisation needed.
    vol10 = ret.rolling(10).std()
    vol60 = ret.rolling(60).std()
    quiet = (vol10 / vol60) < volratio_cap

    # Execution days (Tue/Fri etc)
    is_exec_day = schedule_mask(idx, cadence).reindex(idx).fillna(False)

    # Allowed to act (both vol gate & exec day)
    allow = is_exec_day & quiet.fillna(False)

    # Execution timing of the **signal** (exec=T uses today's signal; "next" shifts)
    sig_use = signal if exec_mode.upper() == "T" else signal.shift(1)
    sig_use = sig_use.fillna(0.0)

    # Sizing
    w = vol_target_weights(ret, vol_target, vol_lb, lev_cap)

    # Time-stop engine with exits on next allowed exec day after hold expiry
    pos_dir = 0  # -1, 0, +1
    holding_left = 0  # trading-day countdown
    exit_due = False  # become True when holding hits 0; flatten on next allowed day

    pos = pd.Series(0.0, index=idx)

    for i, d in enumerate(idx):
        can_trade_today = bool(allow.iloc[i])

        # Decrement hold while in position
        if pos_dir != 0 and holding_left > 0:
            holding_left -= 1
            if holding_left == 0:
                exit_due = True

        # Entry: only from flat, only on allowed day
        if pos_dir == 0 and can_trade_today and sig_use.iloc[i] != 0.0:
            pos_dir = int(np.sign(sig_use.iloc[i]))
            holding_left = hold_bars
            exit_due = False

        # Exit: only when due AND on an allowed day
        if pos_dir != 0 and exit_due and can_trade_today:
            pos_dir = 0
            exit_due = False

        # Set today's end-of-day position (applies to PnL from T -> T+1)
        pos.iloc[i] = pos_dir * w.iloc[i]

    # Correct PnL timing
    pos_prev = pos.shift(1).fillna(0.0)
    strat_ret, costs = pnl_with_costs(
        ret, pos_prev, pos, cost_per_abs_delta, is_exec_day
    )

    curve = equity_curve(strat_ret)

    def seg(mask: pd.Series):
        r = strat_ret[mask]
        if r.empty:
            return dict(
                sharpe=0.0,
                dd=np.nan,
                turnover=np.nan,
                trades=0,
                avg_hold=np.nan,
                pct_days=np.nan,
                hit=np.nan,
                ann_return=np.nan,
            )
        ec = equity_curve(r)
        dd = max_drawdown(ec)
        sharpe = annualise_sharpe(r)
        turnover = (pos[mask] - pos_prev[mask]).abs().mean()
        # Approx trade counting: count entry events on allowed days
        entries = ((pos[mask] != 0) & (pos_prev[mask] == 0) & is_exec_day[mask]).sum()
        pct_days = 100.0 * (pos[mask].abs() > 1e-9).mean()
        ann_ret = (1 + r).prod() ** (252 / len(r)) - 1 if len(r) > 0 else np.nan
        return dict(
            sharpe=sharpe,
            dd=dd,
            turnover=turnover,
            trades=int(entries),
            avg_hold=float(hold_bars),
            pct_days=pct_days,
            hit=np.nan,
            ann_return=ann_ret,
        )

    is_mask = idx < IS_CUTOFF
    oos_mask = idx >= IS_CUTOFF

    return {
        "signal": signal,
        "position_prev": pos_prev,
        "position": pos,
        "strat_ret": strat_ret,
        "equity": curve,
        "costs": costs,
        "is_exec_day": is_exec_day,
        "allow": allow,
        "IS": seg(is_mask),
        "OOS": seg(oos_mask),
        "ALL": seg(pd.Series(True, index=idx)),
    }


def main():
    p = argparse.ArgumentParser(
        description="HookCore v1.2 (RSI3 cross + calm-vol gate)"
    )
    p.add_argument("--excel", required=True)
    p.add_argument("--sheet", default="Raw")
    p.add_argument("--date-col", default="Date")
    p.add_argument("--price-col", default="copper_lme_3mo")
    p.add_argument("--symbol", default="COPPER")
    p.add_argument("--outdir", default=None)

    # Strategy params (same flags as before; new defaults reflect v1.2)
    p.add_argument(
        "--low", type=float, default=DEFAULT_LOW, help="RSI low threshold (default 30)"
    )
    p.add_argument(
        "--high",
        type=float,
        default=DEFAULT_HIGH,
        help="RSI high threshold (default 70)",
    )
    p.add_argument(
        "--volratio",
        type=float,
        default=DEFAULT_VOLRATIO,
        help="10d/60d vol must be < this (default 1.20)",
    )
    p.add_argument(
        "--cadence", choices=["biweekly", "weekly", "event"], default=DEFAULT_CADENCE
    )
    p.add_argument("--exec", choices=["T", "next"], default=DEFAULT_EXEC)
    p.add_argument("--hold", type=int, default=DEFAULT_HOLD)
    # Risk & costs
    p.add_argument("--vol-target", type=float, default=DEFAULT_VOL_TARGET)
    p.add_argument("--vol-lb", type=int, default=DEFAULT_VOL_LB)
    p.add_argument("--lev-cap", type=float, default=DEFAULT_LEV_CAP)
    p.add_argument(
        "--cost-bps",
        type=float,
        default=1.5,
        help="Per |Δposition|, in bps (default 1.5)",
    )

    args = p.parse_args()

    # Load data
    df_raw = pd.read_excel(args.excel, sheet_name=args.sheet)
    if args.date_col not in df_raw.columns or args.price_col not in df_raw.columns:
        # fallback: pick first two columns
        df_raw = df_raw.rename(
            columns={df_raw.columns[0]: "Date", df_raw.columns[1]: "Price"}
        )
        date_col, price_col = "Date", "Price"
    else:
        date_col, price_col = args.date_col, args.price_col

    df = df_raw[[date_col, price_col]].copy()
    df.columns = ["Date", "Price"]
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").dropna(subset=["Price"]).set_index("Date")
    df["ret"] = df["Price"].pct_change().fillna(0.0)

    cost_per_abs_delta = args.cost_bps / 10000.0

    # Run
    res = run_strategy(
        df,
        low_th=args.low,
        high_th=args.high,
        volratio_cap=args.volratio,
        cadence=args.cadence,
        exec_mode=args.exec,
        hold_bars=args.hold,
        vol_target=args.vol_target,
        vol_lb=args.vol_lb,
        lev_cap=args.lev_cap,
        cost_per_abs_delta=cost_per_abs_delta,
    )

    # Output paths (unchanged structure)
    outdir = args.outdir or os.path.join(
        "outputs",
        "hookcore",
        args.symbol,
        f"RSI3_{int(args.low)}_{int(args.high)}_vr{args.volratio}_{args.cadence}_{args.exec}_hold{args.hold}",
    )
    os.makedirs(outdir, exist_ok=True)

    daily = pd.DataFrame(
        {
            "Price": df["Price"],
            "ret": df["ret"],
            "signal": res["signal"],
            "position_prev": res["position_prev"],
            "position": res["position"],
            "strat_ret": res["strat_ret"],
            "equity": res["equity"],
            "costs": res["costs"],
            "is_exec_day": res["is_exec_day"],
            "allow": res["allow"],
        },
        index=df.index,
    )
    daily.index.name = "Date"
    daily.to_csv(os.path.join(outdir, "daily_series.csv"))

    pd.DataFrame({"equity": res["equity"]}, index=df.index).to_csv(
        os.path.join(outdir, "equity_curves.csv")
    )

    summary = {
        "sleeve": "HookCore",
        "version": "v1.2",
        "config": {
            "rsi_window": 3,
            "rsi_thresholds": [args.low, args.high],
            "volratio_cap": args.volratio,
            "cadence": args.cadence,
            "exec": args.exec,
            "hold_bars": args.hold,
            "vol_target": args.vol_target,
            "vol_lookback": args.vol_lb,
            "leverage_cap": args.lev_cap,
            "cost_bps": args.cost_bps,
            "is_cutoff": str(IS_CUTOFF.date()),
        },
        "IS": res["IS"],
        "OOS": res["OOS"],
        "ALL": res["ALL"],
    }
    with open(os.path.join(outdir, "summary_metrics.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps({"outdir": outdir, "IS": res["IS"], "OOS": res["OOS"]}, indent=2))


if __name__ == "__main__":
    main()
