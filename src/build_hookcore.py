import os, json, argparse, math
import pandas as pd
import numpy as np

# ---------------------- Defaults ----------------------
DEFAULT_LOW = 35.0
DEFAULT_HIGH = 65.0
DEFAULT_VOLRATIO = 1.0  # 10d/60d realised vol must be < this
DEFAULT_VOL_TARGET = 0.10
DEFAULT_VOL_LB = 28
DEFAULT_LEV_CAP = 2.5
DEFAULT_COST_PER_ABS_DELTA = 0.000015  # 1.5 bps
DEFAULT_HOLD = 2
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


def pnl_with_costs(ret: pd.Series, pos: pd.Series, cost_per_abs_delta: float):
    pos_filled = pos.fillna(0.0)
    delta = pos_filled.diff().abs().fillna(pos_filled.abs())
    costs = cost_per_abs_delta * delta
    strat_ret = pos_filled * ret - costs
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
    cross_up = (r.shift(1) < low_th) & (r >= low_th) & (dr > 0)
    cross_dn = (r.shift(1) > high_th) & (r <= high_th) & (dr < 0)
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

    # Vol gate (10d/60d realised)
    vol10 = ret.rolling(10).std()
    vol60 = ret.rolling(60).std()
    quiet = (vol10 / vol60) < volratio_cap

    allow = schedule_mask(idx, cadence).reindex(idx).fillna(False) & quiet

    # Execution choice
    sig_use = signal if exec_mode.upper() == "T" else signal.shift(1)
    sig_use = sig_use.fillna(0.0)

    # Sizing
    w = vol_target_weights(ret, vol_target, vol_lb, lev_cap)

    # Time-stop engine
    pos = pd.Series(0.0, index=idx)
    trades = []
    holding = 0
    current_dir = 0
    entry_date = None

    for i, d in enumerate(idx):
        if holding > 0:
            pos.iloc[i] = current_dir * w.iloc[i]
            holding -= 1
            if holding == 0:
                trades.append((entry_date, d, current_dir))
                current_dir = 0
                entry_date = None
        else:
            if allow.iloc[i] and sig_use.iloc[i] != 0.0:
                current_dir = int(np.sign(sig_use.iloc[i]))
                holding = hold_bars
                pos.iloc[i] = current_dir * w.iloc[i]
                entry_date = d
            else:
                pos.iloc[i] = 0.0

    strat_ret, costs = pnl_with_costs(ret, pos, cost_per_abs_delta)
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
        turnover = pos[mask].diff().abs().mean()
        # trade stats in segment (approx hit via sign*sum(ret))
        tlist = [t for t in trades if (t[0] in r.index)]
        if tlist:
            holds = [(t[1] - t[0]).days for t in tlist]
            hits = []
            for s, e, dr in tlist:
                sub = df.loc[s:e, "ret"]
                hits.append(1 if dr * sub.sum() > 0 else 0)
            avg_hold = float(np.mean(holds)) if holds else np.nan
            hitrate = 100.0 * float(np.mean(hits)) if hits else np.nan
            tcount = len(tlist)
        else:
            avg_hold, hitrate, tcount = np.nan, np.nan, 0
        ann_ret = (1 + r).prod() ** (252 / len(r)) - 1 if len(r) > 0 else np.nan
        pct_days = 100.0 * (pos[mask] != 0).mean()
        return dict(
            sharpe=sharpe,
            dd=dd,
            turnover=turnover,
            trades=tcount,
            avg_hold=avg_hold,
            pct_days=pct_days,
            hit=hitrate,
            ann_return=ann_ret,
        )

    is_mask = idx < IS_CUTOFF
    oos_mask = idx >= IS_CUTOFF

    return {
        "signal": signal,
        "position": pos,
        "strat_ret": strat_ret,
        "equity": curve,
        "costs": costs,
        "IS": seg(is_mask),
        "OOS": seg(oos_mask),
        "ALL": seg(pd.Series(True, index=idx)),
    }


def main():
    p = argparse.ArgumentParser(
        description="HookCore signals builder (RSI3 cross + vol gate)"
    )
    p.add_argument("--excel", required=True)
    p.add_argument("--sheet", default="Raw")
    p.add_argument("--date-col", default="Date")
    p.add_argument("--price-col", default="copper_lme_3mo")
    p.add_argument("--symbol", default="COPPER")
    p.add_argument("--outdir", default=None)

    # Strategy params
    p.add_argument(
        "--low", type=float, default=DEFAULT_LOW, help="RSI low threshold (default 35)"
    )
    p.add_argument(
        "--high",
        type=float,
        default=DEFAULT_HIGH,
        help="RSI high threshold (default 65)",
    )
    p.add_argument(
        "--volratio",
        type=float,
        default=DEFAULT_VOLRATIO,
        help="10d/60d vol must be < this (default 1.0)",
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

    # Output paths
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
            "position": res["position"],
            "strat_ret": res["strat_ret"],
            "equity": res["equity"],
            "costs": res["costs"],
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
        "version": "v1.1",
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
