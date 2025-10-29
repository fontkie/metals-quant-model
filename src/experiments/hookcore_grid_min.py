import os, math, json
import itertools as it
import pandas as pd
import numpy as np

# --- Try to import your live builder so we don't duplicate logic
import sys

sys.path.append("src")
try:
    from build_hookcore_v12 import run_strategy
except Exception as e:
    print("[WARN] Could not import build_hookcore_v12.run_strategy:", e)
    print("       Falling back to an internal minimal engine (RSI=3).")

    # --- Minimal fall-back (kept very close to your v1.2 logic) ---
    def rsi(series: pd.Series, length: int = 3) -> pd.Series:
        delta = series.diff()
        up = delta.clip(lower=0).rolling(length).mean()
        down = (-delta.clip(upper=0)).rolling(length).mean()
        rs = up / down.replace(0, np.nan)
        out = 100 - (100 / (1 + rs))
        return out.fillna(50.0)

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
        cost_bps: float,
    ):
        # returns: dict with IS/OOS/ALL fields (sharpe, dd, trades, etc.)
        idx = df.index
        ret = df["ret"]
        price = df["Price"]

        # Signal (RSI=3 crosses)
        r = rsi(price, 3)
        cross_up = (r.shift(1) <= low_th) & (r > low_th)
        cross_dn = (r.shift(1) >= high_th) & (r < high_th)
        signal = pd.Series(0.0, index=idx)
        signal[cross_up] = 1.0
        signal[cross_dn] = -1.0

        # Vol gate (10/60)
        vol10 = ret.rolling(10).std()
        vol60 = ret.rolling(60).std()
        quiet = (vol10 / vol60) < volratio_cap

        # Exec cadence mask
        if cadence == "biweekly":  # Tue/Fri
            is_exec_day = idx.day_name().str[:3].isin(["Tue", "Fri"])
        elif cadence == "weekly":  # Fri only
            is_exec_day = idx.day_name().str[:3].eq("Fri")
        else:  # "event" == any day
            is_exec_day = pd.Series(True, index=idx)

        allow = quiet.fillna(False) & is_exec_day

        # Execution timing
        sig_use = signal if exec_mode.upper() == "T" else signal.shift(1)
        sig_use = sig_use.fillna(0.0)

        # Vol targeting (28d), cap
        rolling_vol = ret.rolling(vol_lb).std() * np.sqrt(252.0)
        scale = (
            (vol_target / rolling_vol.replace(0, np.nan))
            .clip(lower=0, upper=lev_cap)
            .fillna(0.0)
        )

        # State machine with time-based exit at next allowed exec day on/after T+hold
        pos_dir = 0
        exit_due_dt = pd.NaT
        pos = pd.Series(0.0, index=idx)

        for i, t in enumerate(idx):
            can_trade = bool(allow.iloc[i])

            # Flatten when due and allowed
            if (
                pos_dir != 0
                and pd.notna(exit_due_dt)
                and (t >= exit_due_dt)
                and can_trade
            ):
                pos_dir = 0
                exit_due_dt = pd.NaT

            # Entry only from flat & allowed
            if pos_dir == 0 and can_trade:
                if sig_use.iloc[i] > 0:
                    pos_dir = +1
                    tpos = i
                    exit_due_dt = idx[min(tpos + hold_bars, len(idx) - 1)]
                elif sig_use.iloc[i] < 0:
                    pos_dir = -1
                    tpos = i
                    exit_due_dt = idx[min(tpos + hold_bars, len(idx) - 1)]

            pos.iloc[i] = pos_dir * scale.iloc[i]

        # Correct PnL timing + costs only on exec Δpos
        pos_prev = pos.shift(1).fillna(0.0)
        delta = (pos - pos_prev).abs()
        costs = (cost_bps * 1e-4) * delta * is_exec_day.astype(float)
        strat_ret = pos_prev * ret - costs

        def eq(s):
            return (1 + s.fillna(0)).cumprod()

        def mdd(curve):
            peak = curve.cummax()
            return float((curve / peak - 1).min())

        def sharpe(s):
            mu = s.mean() * 252.0
            sd = s.std(ddof=0) * math.sqrt(252.0)
            return 0.0 if sd == 0 else float(mu / sd)

        def seg(mask):
            s = strat_ret[mask].dropna()
            if s.empty:
                return dict(
                    sharpe=np.nan,
                    max_dd=np.nan,
                    trades=0,
                    ann_return=np.nan,
                    pct_days_in_pos=0.0,
                )
            curve = eq(s)
            trades = int(
                ((delta[mask] > 1e-12) & is_exec_day[mask]).astype(int).sum() // 2
            )
            ann_ret = s.mean() * 252.0
            return dict(
                sharpe=sharpe(s),
                max_dd=mdd(curve),
                trades=trades,
                ann_return=ann_ret,
                pct_days_in_pos=float((pos[mask].abs() > 1e-9).mean()),
            )

        IS_CUTOFF = pd.Timestamp("2018-01-01")
        IS = seg(idx < IS_CUTOFF)
        OOS = seg(idx >= IS_CUTOFF)
        ALL = seg(pd.Series(True, index=idx))

        return {
            "signal": signal,
            "position": pos,
            "position_prev": pos_prev,
            "strat_ret": strat_ret,
            "costs": costs,
            "IS": IS,
            "OOS": OOS,
            "ALL": ALL,
        }


# --- Adapter so either run_strategy signature works (cost_bps vs cost_per_abs_delta) ---
import inspect


def run_strategy_adapter(df, **kwargs):
    """
    Calls whichever run_strategy is available:
    - If it accepts cost_bps -> pass through
    - If it accepts cost_per_abs_delta -> convert cost_bps / 10000
    """
    sig = inspect.signature(run_strategy)
    if "cost_bps" in sig.parameters:
        return run_strategy(df=df, **kwargs)
    elif "cost_per_abs_delta" in sig.parameters:
        kw = kwargs.copy()
        cost_bps = kw.pop("cost_bps")
        kw["cost_per_abs_delta"] = cost_bps / 10000.0
        return run_strategy(df=df, **kw)
    else:
        raise TypeError(f"run_strategy() signature not recognised: {sig}")


# ----------------- CONFIG -----------------
EXCEL = r"Data\copper\pricing\pricing_values.xlsx"
PRICE_COL = "copper_lme_3mo"
DATE_COL = None  # set to "Date" if your sheet has an explicit date column
SHEET = 0  # or "Raw"
IS_OOS_SPLIT = pd.Timestamp("2018-01-01")

GRID_VOLRATIO = [1.10, 1.15, 1.20]
GRID_HOLD = [3, 4]
GRID_CADENCE = ["biweekly", "weekly", "event"]  # Tue/Fri, Fri, All
LOW_HIGH = (30.0, 70.0)
VOL_TARGET = 0.10
VOL_LB = 28
LEV_CAP = 2.5
COST_BPS = 1.5
EXEC_MODE = "T"


# ----------------- RUN -----------------
def main():
    # --- load data ---
    df_raw = pd.read_excel(EXCEL, sheet_name=SHEET)
    if DATE_COL and (DATE_COL in df_raw.columns):
        df_raw[DATE_COL] = pd.to_datetime(df_raw[DATE_COL])
        df_raw = df_raw.set_index(DATE_COL).sort_index()
    else:
        # assume the index is date-like if no explicit date col
        df_raw.index = pd.to_datetime(df_raw.index)

    price = df_raw[PRICE_COL].astype(float).rename("Price")
    df = pd.DataFrame({"Price": price})
    df["ret"] = df["Price"].pct_change().fillna(0.0)
    df.index = pd.to_datetime(df.index, utc=False).tz_localize(None)

    # --- sweep the grid ---
    rows = []
    for vr, hold, cad in it.product(GRID_VOLRATIO, GRID_HOLD, GRID_CADENCE):
        res = run_strategy_adapter(
            df=df.copy(),
            low_th=LOW_HIGH[0],
            high_th=LOW_HIGH[1],
            volratio_cap=vr,
            cadence=cad,
            exec_mode=EXEC_MODE,
            hold_bars=hold,
            vol_target=VOL_TARGET,
            vol_lb=VOL_LB,
            lev_cap=LEV_CAP,
            cost_bps=COST_BPS,
        )
        IS, OOS, ALL = res["IS"], res["OOS"], res["ALL"]
        rows.append(
            {
                "vol_gate_ratio": vr,
                "hold_bars": hold,
                "cadence": cad,
                "all_sharpe": ALL["sharpe"],
                "all_ann_return": ALL["ann_return"],
                "all_max_dd": ALL["max_dd"],
                "is_sharpe": IS["sharpe"],
                "is_ann_return": IS["ann_return"],
                "is_max_dd": IS["max_dd"],
                "oos_sharpe": OOS["sharpe"],
                "oos_ann_return": OOS["ann_return"],
                "oos_max_dd": OOS["max_dd"],
                "oos_trades": OOS["trades"],
                "oos_pct_in_pos": OOS["pct_days_in_pos"],
            }
        )

    resdf = pd.DataFrame(rows).sort_values(
        ["oos_sharpe", "oos_ann_return", "oos_max_dd"], ascending=[False, False, True]
    )

    outdir = os.path.join("outputs", "Copper", "hookcore", "experiments_min")
    os.makedirs(outdir, exist_ok=True)
    out_csv = os.path.join(outdir, "summary_results_min.csv")
    resdf.to_csv(out_csv, index=False, float_format="%.6f")

    print("\nTop 10 by OOS Sharpe")
    print(
        resdf[
            [
                "cadence",
                "vol_gate_ratio",
                "hold_bars",
                "oos_sharpe",
                "oos_ann_return",
                "oos_max_dd",
                "oos_trades",
            ]
        ]
        .head(10)
        .to_string(index=False)
    )
    print("\nSaved:", out_csv)


if __name__ == "__main__":
    main()
