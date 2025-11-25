import os, json, math, itertools, datetime as dt
import pandas as pd
import numpy as np
import yaml

# ---------- Core helpers (copied from build_hookcore_v12, trimmed to be self-contained) ----------
# Force datetime index


IS_OOS_SPLIT = pd.Timestamp("2018-01-01")
# ---- Global constants ----
IS_OOS_SPLIT = pd.Timestamp("2018-01-01")

# Force split date and data index to be naïve UTC to avoid tz mismatches
IS_OOS_SPLIT = IS_OOS_SPLIT.tz_localize(None)


def rsi(series: pd.Series, length: int = 3) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    roll_up = up.ewm(alpha=1 / length, adjust=False).mean()
    roll_down = down.ewm(alpha=1 / length, adjust=False).mean()
    rs = roll_up / (roll_down.replace(0, np.nan))
    out = 100 - (100 / (1 + rs))
    return out.fillna(50.0)


def realized_vol(x: pd.Series, win: int) -> pd.Series:
    return x.rolling(win).std() * np.sqrt(252.0)


def weekday_mask(idx: pd.DatetimeIndex, allowed_days) -> pd.Series:
    wd3 = idx.day_name().str[:3]
    allowed = set([d[:3] for d in allowed_days])
    return wd3.isin(allowed)


def block_metrics(df: pd.DataFrame, ret_col: str) -> dict:
    s = df[ret_col].dropna()
    if s.empty:
        return dict(
            ann_return=np.nan,
            ann_vol=np.nan,
            sharpe=np.nan,
            max_dd=np.nan,
            trades=0,
            pct_days_in_pos=0.0,
        )
    ann_ret = s.mean() * 252.0
    ann_vol = s.std(ddof=0) * math.sqrt(252.0)
    sharpe = 0.0 if ann_vol == 0 else ann_ret / ann_vol
    eq = (1.0 + s).cumprod()
    max_dd = (eq / eq.cummax() - 1.0).min()
    # trades: count entry events (Δpos != 0 on exec days) /2 is unreliable; we count entries directly
    entries = (
        ((df["turnover"] > 1e-12) & df["is_exec_day"])
        .astype(int)
        .diff()
        .clip(lower=0)
        .sum()
    )
    pct_in_pos = float((df["position"].abs() > 1e-9).mean())
    return dict(
        ann_return=ann_ret,
        ann_vol=ann_vol,
        sharpe=sharpe,
        max_dd=max_dd,
        trades=int(entries),
        pct_days_in_pos=pct_in_pos,
    )


def run_hookcore_variant(
    price_series: pd.Series,
    rsi_length: int,
    vol_gate_ratio: float,
    early_exit_band: tuple | None,
    exec_days: tuple,
    hold_bars: int = 3,
    target_vol: float = 0.10,
    lookback: int = 28,
    lev_cap: float = 2.5,
    cost_bps: float = 1.5,
):
    # --- Ensure datetime index is valid for IS/OOS split ---
    df = pd.DataFrame({"price": price_series.ffill()}).copy()
    df.index = pd.to_datetime(df.index, utc=False)
    df.index = df.index.tz_localize(None)

    # --- Core calculations ---
    df["ret"] = df["price"].pct_change()
    df["rsi"] = rsi(df["price"], rsi_length)
    rv10 = realized_vol(df["ret"], 10)
    rv60 = realized_vol(df["ret"], 60)
    df["vol_ratio"] = (rv10 / rv60).replace([np.inf, -np.inf], np.nan).fillna(np.inf)

    buy_cross = 30.0
    sell_cross = 70.0
    df["cross_up"] = (df["rsi"].shift(1) <= buy_cross) & (df["rsi"] > buy_cross)
    df["cross_dn"] = (df["rsi"].shift(1) >= sell_cross) & (df["rsi"] < sell_cross)

    df["is_exec_day"] = weekday_mask(df.index, exec_days)
    df["vol_ok"] = df["vol_ratio"] < vol_gate_ratio

    pos_dir = 0
    exit_due_dt = pd.NaT
    last_pos = 0.0
    rolling_vol = df["ret"].rolling(lookback).std() * np.sqrt(252.0)
    pos_vals = []
    idx = df.index

    for t, row in df.iterrows():
        can_trade = bool(row["is_exec_day"] and row["vol_ok"])

        # Exit if hold expired and allowed to trade
        if pos_dir != 0 and pd.notna(exit_due_dt) and (t >= exit_due_dt) and can_trade:
            pos_dir = 0
            exit_due_dt = pd.NaT

        # Early exit (RSI mid-band)
        if early_exit_band and pos_dir != 0:
            lo, hi = early_exit_band
            if (df.at[t, "rsi"] >= lo) and (df.at[t, "rsi"] <= hi) and can_trade:
                pos_dir = 0
                exit_due_dt = pd.NaT

        # New entry
        if pos_dir == 0 and can_trade:
            if row["cross_up"]:
                pos_dir = +1
                tpos = idx.get_loc(t)
                tgt_idx = min(tpos + hold_bars, len(idx) - 1)
                exit_due_dt = idx[tgt_idx]
            elif row["cross_dn"]:
                pos_dir = -1
                tpos = idx.get_loc(t)
                tgt_idx = min(tpos + hold_bars, len(idx) - 1)
                exit_due_dt = idx[tgt_idx]

        # Vol targeting
        vol_today = rolling_vol.loc[t]
        if pd.isna(vol_today) or vol_today <= 0:
            scale = 0.0
        else:
            scale = float(np.clip(target_vol / vol_today, 0.0, lev_cap))
        pos_vals.append(float(pos_dir * scale))

    df["position"] = pd.Series(pos_vals, index=df.index)
    df["position_prev"] = df["position"].shift(1).fillna(0.0)
    df["turnover"] = (df["position"] - df["position_prev"]).abs()
    df["cost"] = (cost_bps * 1e-4) * df["turnover"] * df["is_exec_day"].astype(float)
    df["strat_ret"] = df["position_prev"] * df["ret"] - df["cost"]

    # --- IS/OOS metrics ---
    is_mask = df.index < IS_OOS_SPLIT
    oos_mask = df.index >= IS_OOS_SPLIT

    all_m = block_metrics(df, "strat_ret")
    is_m = block_metrics(df.loc[is_mask], "strat_ret")
    oos_m = block_metrics(df.loc[oos_mask], "strat_ret")

    non_exec_trade_days = int(((df["turnover"] > 1e-12) & (~df["is_exec_day"])).sum())

    return df, {
        "all": all_m,
        "is": is_m,
        "oos": oos_m,
        "non_exec_turnover_days": non_exec_trade_days,
    }


def main():
    # ---- Load base YAML for data path/column, but params get overridden by the grid ----
    with open("docs/Copper/hookcore/hookcore.yaml", "r") as f:
        base_cfg = yaml.safe_load(f)

    data_file = base_cfg["data"]["file"]
    price_col = base_cfg["data"]["price_col"]

    dfp = pd.read_excel(data_file)
    if "date" in dfp.columns:
        dfp["date"] = pd.to_datetime(dfp["date"])
        dfp = dfp.set_index("date").sort_index()
    else:
        dfp.index = pd.to_datetime(dfp.index)

    price = dfp[price_col].astype(float)

    # ---- Grid definitions ----
    rsi_lengths = [3, 4, 5]
    vol_gate_ratios = [1.10, 1.15, 1.20]
    early_exit_opts = [None, (40, 60)]  # None = off, (40,60) = on

    # Execution cadence sets (verify Tue/Fri assumption)
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    two_day_pairs = list(itertools.combinations(weekdays, 2))
    exec_sets = [tuple(p) for p in two_day_pairs] + [
        tuple(weekdays)
    ]  # all weekdays as a control

    # ---- Sweep ----
    rows = []
    out_root = "outputs/Copper/hookcore/experiments"
    os.makedirs(out_root, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(out_root, f"grid_{stamp}")
    os.makedirs(run_dir, exist_ok=True)

    n = 0
    for rsi_len, vg, ee, ex in itertools.product(
        rsi_lengths, vol_gate_ratios, early_exit_opts, exec_sets
    ):
        n += 1
        tag = f"RSI{rsi_len}_VG{vg:.2f}_{'EE4060' if ee else 'EEOFF'}_EX{'-'.join(ex)}"
        df, mets = run_hookcore_variant(
            price_series=price,
            rsi_length=rsi_len,
            vol_gate_ratio=vg,
            early_exit_band=ee,
            exec_days=ex,
            hold_bars=base_cfg["execution"]["hold_bars"],
            target_vol=base_cfg["risk"]["target_vol_ann"],
            lookback=base_cfg["risk"]["target_lookback_days"],
            lev_cap=base_cfg["risk"]["leverage_cap"],
            cost_bps=base_cfg["costs"]["turnover_bps"],
        )

        # save a compact daily file for top picks only later if needed; for now, keep metrics light
        rows.append(
            {
                "tag": tag,
                "rsi_length": rsi_len,
                "vol_gate_ratio": vg,
                "early_exit": "on(40-60)" if ee else "off",
                "exec_days": ",".join(ex),
                "all_sharpe": mets["all"]["sharpe"],
                "all_ann_return": mets["all"]["ann_return"],
                "all_ann_vol": mets["all"]["ann_vol"],
                "all_max_dd": mets["all"]["max_dd"],
                "all_trades": mets["all"]["trades"],
                "all_pct_in_pos": mets["all"]["pct_days_in_pos"],
                "is_sharpe": mets["is"]["sharpe"],
                "is_ann_return": mets["is"]["ann_return"],
                "is_max_dd": mets["is"]["max_dd"],
                "oos_sharpe": mets["oos"]["sharpe"],
                "oos_ann_return": mets["oos"]["ann_return"],
                "oos_max_dd": mets["oos"]["max_dd"],
                "oos_trades": mets["oos"]["trades"],
                "oos_pct_in_pos": mets["oos"]["pct_days_in_pos"],
                "non_exec_turnover_days": mets["non_exec_turnover_days"],
            }
        )

    res = pd.DataFrame(rows)

    # Ranking: primary OOS Sharpe, then OOS return, then lower max DD (less negative)
    res["rank_key"] = list(
        zip(
            res["oos_sharpe"].fillna(-9e9),
            res["oos_ann_return"].fillna(-9e9),
            (-res["oos_max_dd"]).fillna(-9e9),
        )
    )
    res = res.sort_values(
        by=["oos_sharpe", "oos_ann_return", "oos_max_dd"],
        ascending=[False, False, True],
    )

    # Persist
    out_csv = os.path.join(run_dir, "summary_results.csv")
    res.to_csv(out_csv, index=False, float_format="%.6f")

    # Print quick top 15
    print("\nTop 15 by OOS Sharpe")
    cols = [
        "tag",
        "exec_days",
        "rsi_length",
        "vol_gate_ratio",
        "early_exit",
        "oos_sharpe",
        "oos_ann_return",
        "oos_max_dd",
        "oos_trades",
    ]
    print(res[cols].head(15).to_string(index=False))

    # Sanity: check all non-exec turnover = 0
    bad = res[res["non_exec_turnover_days"] > 0]
    if len(bad):
        print("\n[WARN] Some configs traded on non-exec days. First few:")
        print(
            bad[["tag", "exec_days", "non_exec_turnover_days"]]
            .head()
            .to_string(index=False)
        )

    print(f"\nSaved results to: {out_csv}")
    print(f"Total configs run: {len(res)}")


if __name__ == "__main__":
    main()
