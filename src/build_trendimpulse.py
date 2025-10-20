# src/build_trendimpulse.py
# TrendImpulse — fast-trend (2–4 day) continuation sleeve
# - Cadences: monwed | tuethu | tuefri | daily
# - Continuation trigger using z-dev vs EMA60 + short momentum (EMA5-EMA20)
# - Time-stop exit (default H=3), optional cooldown after exit
# - 10% vol target, 28d RV, 2.5x cap, costs in bps
#
# Example:
#   python src/build_trendimpulse.py ^
#     --excel "C:\Code\Metals\Data\copper\pricing\pricing_values.xlsx" ^
#     --sheet Raw ^
#     --date-col Date ^
#     --price-col copper_lme_3mo ^
#     --symbol COPPER ^
#     --outdir outputs ^
#     --oos-start 2018-01-01 ^
#     --z-th 1.0 ^
#     --hold 3 ^
#     --rebalance-threshold 0.10 ^
#     --vol-lookback 28 ^
#     --lev-cap 2.5 ^
#     --bps 1.5 ^
#     --cadence tuefri ^
#     --cooldown 0 ^
#     --schema-path "Config\schema.yaml"

import argparse, os, json, hashlib, shutil
import pandas as pd
import numpy as np

# ---------- helpers ----------


def ann_sharpe(r):
    r = pd.Series(r).dropna()
    sd = r.std()
    if sd == 0 or len(r) == 0:
        return float("nan")
    return float(r.mean() / sd * np.sqrt(252))


def max_drawdown_from_equity(eq):
    x = eq.values.astype(float)
    peaks = np.maximum.accumulate(x)
    dd = (x - peaks) / peaks
    return float(dd.min())


def load_price_frame(excel_path, sheet, date_col, price_col):
    df = pd.read_excel(excel_path, sheet_name=sheet, parse_dates=[date_col])
    if date_col not in df.columns:
        raise ValueError(f"Date column '{date_col}' not found in sheet '{sheet}'.")
    if price_col not in df.columns:
        raise ValueError(f"Price column '{price_col}' not found in sheet '{sheet}'.")
    df = df[[date_col, price_col]].rename(
        columns={date_col: "date", price_col: "price"}
    )
    df = df.dropna().sort_values("date").set_index("date")
    df = df[~df.index.duplicated(keep="first")]
    return df


def sha1_series(s: pd.Series) -> str:
    # stable hash of the float series (rounded to reduce tiny fp noise)
    b = (s.astype(float).round(10)).to_csv(index=True).encode("utf-8")
    return hashlib.sha1(b).hexdigest()


def build_features(df):
    px = df["price"].astype(float)
    ret = np.log(px).diff()
    out = df.copy()
    out["ret"] = ret
    out["ema5"] = px.ewm(span=5, adjust=False).mean()
    out["ema20"] = px.ewm(span=20, adjust=False).mean()
    out["ema60"] = px.ewm(span=60, adjust=False).mean()
    out["stdev60"] = px.rolling(60).std()
    out["z_dev"] = (px - out["ema60"]) / out["stdev60"]
    # short momentum: EMA5 vs EMA20 scaled by 20d stdev of price
    out["mom_short"] = (out["ema5"] - out["ema20"]) / (px.rolling(20).std())
    return out


def decide_entries_trendimpulse(df_feat, z_th=1.0, cadence="tuefri"):
    """
    Continuation triggers:
      - Long when z_dev > +z_th and mom_short > 0
      - Short when z_dev < -z_th and mom_short < 0
    Cadence:
      - 'monwed'  => evaluate only Monday (0) and Wednesday (2)
      - 'tuethu'  => evaluate only Tuesday (1) and Thursday (3)
      - 'tuefri'  => evaluate only Tuesday (1) and Friday (4)
      - 'daily'   => evaluate every business day
    """
    df = df_feat.copy()
    wd = df.index.weekday
    if cadence == "monwed":
        eval_mask = (wd == 0) | (wd == 2)
    elif cadence == "tuethu":
        eval_mask = (wd == 1) | (wd == 3)
    elif cadence == "tuefri":
        eval_mask = (wd == 1) | (wd == 4)
    else:
        eval_mask = np.ones(len(df), dtype=bool)

    long_trig = (df["z_dev"] > z_th) & (df["mom_short"] > 0)
    short_trig = (df["z_dev"] < -z_th) & (df["mom_short"] < 0)

    sig = pd.Series(0.0, index=df.index)
    sig[eval_mask & long_trig] = 1.0
    sig[eval_mask & short_trig] = -1.0
    df["signal_raw"] = sig
    return df


def simulate_time_stop(
    df_sig,
    target_vol=0.10,
    vol_lb=28,
    lev_cap=2.5,
    bps=1.5,
    hold=3,
    rebalance_threshold=0.10,
    cooldown=0,
):
    """
    - Enter only when flat, on signal days.
    - Hold for 'hold' bars (time stop), then flat.
    - Optional 'cooldown' bars waiting period after exit before allowing a new entry.
    - Vol-target with RV(vol_lb), cap at lev_cap.
    - Rebalance leverage only if relative change >= rebalance_threshold (to cut churn).
    - Costs charged on |Δ position| in bps (1bp = 1e-4).
    """
    df = df_sig.copy()
    rv = df["ret"].rolling(vol_lb).std()
    ann = rv * np.sqrt(252)
    lev_target = (target_vol / ann.replace(0, np.nan)).clip(upper=lev_cap).fillna(0.0)

    pos_dir = 0  # -1, 0, +1
    bars_in_trade = 0
    cooldown_left = 0
    positions = []
    lev_series = []
    last_lev = 0.0

    for ts, row in df.iterrows():
        desired = row["signal_raw"]

        # Entry / Exit logic with cooldown
        if pos_dir == 0:
            if cooldown_left > 0:
                cooldown_left -= 1
            elif desired != 0:
                pos_dir = int(np.sign(desired))
                bars_in_trade = 0
        else:
            bars_in_trade += 1
            if bars_in_trade >= hold:
                pos_dir = 0
                bars_in_trade = 0
                cooldown_left = cooldown

        # Rebalance threshold
        lev_t = lev_target.loc[ts]
        if rebalance_threshold > 0 and last_lev != 0:
            if abs(lev_t - last_lev) / abs(last_lev) < rebalance_threshold:
                lev = last_lev
            else:
                lev = lev_t
        else:
            lev = lev_t
        last_lev = lev

        lev_series.append(lev)
        positions.append(pos_dir * lev)

    df["lev"] = pd.Series(lev_series, index=df.index).astype(float)
    df["position"] = pd.Series(positions, index=df.index).astype(float)
    df["pos_dir"] = np.sign(df["position"]).fillna(0.0)

    # Costs on position change
    delta = df["position"].diff().abs().fillna(0.0)
    cost = delta * (bps * 1e-4)

    # Strategy return = lagged position * underlying return - costs
    strat_ret = df["position"].shift(1).fillna(0.0) * df["ret"] - cost
    df["strat_ret"] = strat_ret.fillna(0.0)
    df["equity"] = (1.0 + df["strat_ret"]).cumprod()
    return df


def pack_metrics(sim, oos_start):
    def seg(sub):
        if len(sub) < 30:
            return dict(
                sharpe=float("nan"),
                max_dd=float("nan"),
                turnover=float("nan"),
                pct_days_in_pos=float("nan"),
                trades=0,
                avg_hold=float("nan"),
                hit=float("nan"),
            )
        sh = ann_sharpe(sub["strat_ret"])
        eq = (1.0 + sub["strat_ret"]).cumprod()
        dd = max_drawdown_from_equity(eq / eq.iloc[0])
        t = sub["position"].diff().abs().sum() / len(sub)
        inpos = (sub["pos_dir"].abs() > 0).mean()
        # trade stats
        trades = []
        prev = 0
        entry_idx = None
        entry_eq = None
        for idx, row in sub.iterrows():
            pos = int(row["pos_dir"])
            if prev == 0 and pos != 0:
                entry_idx = idx
                entry_eq = row["equity"]
            if prev != 0 and pos == 0:
                exit_idx = idx
                exit_eq = row["equity"]
                pnl = (exit_eq / entry_eq) - 1.0
                bars = sub.index.get_loc(exit_idx) - sub.index.get_loc(entry_idx)
                trades.append((pnl, bars))
                entry_idx = None
                entry_eq = None
            prev = pos
        if trades:
            pnl = pd.Series([p for p, b in trades])
            bars = pd.Series([b for p, b in trades])
            hit = (pnl > 0).mean()
            avg_hold = bars.mean()
            count = int(len(trades))
        else:
            hit = float("nan")
            avg_hold = float("nan")
            count = 0
        return dict(
            sharpe=float(sh),
            max_dd=float(dd),
            turnover=float(t),
            pct_days_in_pos=float(inpos),
            trades=count,
            avg_hold=float(avg_hold),
            hit=float(hit),
        )

    is_mask = sim.index < oos_start
    oos_mask = sim.index >= oos_start
    return {"IS": seg(sim.loc[is_mask]), "OOS": seg(sim.loc[oos_mask])}


# ---------- main ----------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--date-col", required=True)
    ap.add_argument("--price-col", required=True)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--outdir", default="outputs")
    ap.add_argument("--oos-start", default="2018-01-01")
    ap.add_argument("--z-th", type=float, default=1.0)
    ap.add_argument("--hold", type=int, default=3)
    ap.add_argument("--rebalance-threshold", type=float, default=0.10)
    ap.add_argument("--vol-lookback", type=int, default=28)
    ap.add_argument("--lev-cap", type=float, default=2.5)
    ap.add_argument("--bps", type=float, default=1.5)
    ap.add_argument(
        "--cadence", choices=["monwed", "tuethu", "tuefri", "daily"], default="tuefri"
    )
    ap.add_argument(
        "--cooldown",
        type=int,
        default=0,
        help="Bars to wait after exit before a new entry (daily cadence also supported)",
    )
    ap.add_argument(
        "--schema-path", default=None
    )  # optional passthrough, not used here
    ap.add_argument(
        "--run-tag", default=None, help="Optional subfolder tag (default: timestamp)"
    )
    args = ap.parse_args()

    # Load prices
    df_px = load_price_frame(args.excel, args.sheet, args.date_col, args.price_col)

    # Features & signals
    feat = build_features(df_px)
    sig = decide_entries_trendimpulse(feat, z_th=args.z_th, cadence=args.cadence)

    # Simulate
    sim = simulate_time_stop(
        sig,
        target_vol=0.10,
        vol_lb=args.vol_lookback,
        lev_cap=args.lev_cap,
        bps=args.bps,
        hold=args.hold,
        rebalance_threshold=args.rebalance_threshold,
        cooldown=args.cooldown,
    )

    # Effective config for auditability
    oos_start = pd.Timestamp(args.oos_start)
    effective = {
        "excel": os.path.abspath(args.excel),
        "sheet": args.sheet,
        "date_col": args.date_col,
        "price_col": args.price_col,
        "symbol": args.symbol,
        "oos_start": args.oos_start,
        "cadence": args.cadence,
        "z_th": args.z_th,
        "hold": args.hold,
        "rebalance_threshold": args.rebalance_threshold,
        "vol_lookback": args.vol_lookback,
        "lev_cap": args.lev_cap,
        "bps": args.bps,
        "cooldown": args.cooldown,
        "price_sha1": sha1_series(df_px["price"]),
    }
    print("[TrendImpulse:effective]", effective)

    # Metrics
    metrics = pack_metrics(sim, oos_start)

    # Output paths — timestamped run dir to avoid file locks
    run_tag = args.run_tag or pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    run_base = os.path.join(args.outdir, "trendimpulse", args.symbol, run_tag)
    latest_dir = os.path.join(args.outdir, "trendimpulse", args.symbol)
    os.makedirs(run_base, exist_ok=True)
    os.makedirs(latest_dir, exist_ok=True)

    # Save daily series
    daily = sim[
        [
            "price",
            "signal_raw",
            "pos_dir",
            "lev",
            "position",
            "ret",
            "strat_ret",
            "equity",
        ]
    ].copy()
    daily_path = os.path.join(run_base, "daily_series.csv")
    daily.to_csv(daily_path)

    # Save equity curves
    eq_df = pd.DataFrame(
        {
            "equity_all": daily["equity"],
            "equity_IS": (
                1.0 + daily.loc[daily.index < oos_start, "strat_ret"]
            ).cumprod(),
            "equity_OOS": (
                1.0 + daily.loc[daily.index >= oos_start, "strat_ret"]
            ).cumprod(),
        }
    )
    eq_path = os.path.join(run_base, "equity_curves.csv")
    eq_df.to_csv(eq_path)

    # Summary JSON (also serves as run lock)
    summary = {"symbol": args.symbol, "effective_params": effective, "metrics": metrics}
    summary_path = os.path.join(run_base, "summary_metrics.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=float)

    # Try to update "latest" copies (skip if locked)
    try:
        shutil.copyfile(daily_path, os.path.join(latest_dir, "daily_series.csv"))
        shutil.copyfile(eq_path, os.path.join(latest_dir, "equity_curves.csv"))
        shutil.copyfile(summary_path, os.path.join(latest_dir, "summary_metrics.json"))
        shutil.copyfile(summary_path, os.path.join(latest_dir, "run_lock.json"))
    except PermissionError:
        # If something is open in Excel, we still keep the timestamped run
        pass

    print(f"[TrendImpulse] Outputs written to: {run_base}")
    print(f"[TrendImpulse] Latest copies at: {latest_dir}  (skipped if locked)")


if __name__ == "__main__":
    main()
