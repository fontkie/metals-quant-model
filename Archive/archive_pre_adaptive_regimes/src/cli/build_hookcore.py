# --- Policy header (paste near the top of each build_*.py) ---
from __future__ import annotations
from utils.policy import load_execution_policy, policy_banner, warn_if_mismatch
import yaml

# >>> EDIT ME per sleeve <<<
SLEEVE_NAME = "HookCore"  # e.g., "TrendCore", "TrendImpulse", "HookCore", "StocksScore"
CONFIG_PATH = "docs/copper/hookcore/config.yaml"  # path to THIS sleeve's YAML

POLICY = load_execution_policy()
print(policy_banner(POLICY, sleeve_name=SLEEVE_NAME))


def _read_exec_days(path: str):
    """Hookcore executes DAILY; keep interface parity with Trend builder."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            y = yaml.safe_load(f) or {}
        # If someone later adds a cadence in YAML, respect it. Otherwise, daily.
        run = y.get("run") or {}
        cad = (run.get("cadence") or "").lower()
        if cad == "monwed":
            return (0, 2)
        if cad == "tuefri":
            return (1, 4)
        return (0, 1, 2, 3, 4)  # default: daily weekdays
    except FileNotFoundError:
        return (0, 1, 2, 3, 4)


_exec_days = _read_exec_days(CONFIG_PATH)

# Hookcore uses rolling scale clamp [0.5, 1.5] rather than a leverage cap, but we pass 1.5 here for banner harmony.
msgs = warn_if_mismatch(
    POLICY,
    exec_weekdays=_exec_days,
    fill_timing="close_T",
    vol_info="T-1",  # scale uses returns up to T-1
    leverage_cap=1.5,  # analogous to scale clamp max
    one_way_bps=1.5,
)
for _m in msgs:
    print(_m)
# --- end policy header ---


#!/usr/bin/env python
# HookCore v1.5 — Copper mean-reversion (T-close execution; PnL from T+1)
# Bollinger(5, 1.5σ) with regime filters (non-trend, low-vol, neg autocorr)
# Hold 3 trading days with overlaps; entry cost on T only; no exit cost
# Rolling 63D vol target to 10% with clamp [0.5, 1.5] using info up to T-1

import argparse, json
from pathlib import Path

import numpy as np
import pandas as pd


# ---------- IO ----------


def load_prices_excel_source_dates(
    path, sheet, date_col, price_col, symbol
) -> pd.Series:
    """
    Use *only* source trading dates (no weekday reindex; no forward-fill across holidays).
    """
    df = pd.read_excel(path, sheet_name=sheet)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns={date_col: "dt", price_col: symbol})[["dt", symbol]]
    # Date may be Excel serial; let pandas infer + fallback for numeric
    try:
        if np.issubdtype(df["dt"].dtype, np.number):
            df["dt"] = pd.to_datetime("1899-12-30") + pd.to_timedelta(
                df["dt"].astype(float), unit="D"
            )
        else:
            df["dt"] = pd.to_datetime(df["dt"])
    except Exception:
        df["dt"] = pd.to_datetime(df["dt"])
    df = df.dropna().sort_values("dt").drop_duplicates("dt").set_index("dt")
    return df[symbol].rename(symbol)


# ---------- Indicators ----------


def rolling_mean_std(px: pd.Series, lb: int):
    mu = px.rolling(lb, min_periods=lb).mean()
    sd = px.rolling(lb, min_periods=lb).std(ddof=0)
    return mu, sd


def cumret_window(px: pd.Series, lb: int) -> pd.Series:
    return (px / px.shift(lb)) - 1.0


def rolling_std_ret(ret: pd.Series, lb: int) -> pd.Series:
    return ret.rolling(lb, min_periods=lb).std(ddof=0)


def rolling_autocorr_lag1(ret: pd.Series, lb: int) -> pd.Series:
    return ret.rolling(lb, min_periods=lb).corr(ret.shift(1))


# ---------- Signal (bands + filters) ----------


def hookcore_signal(
    px: pd.Series,
    bb_lb: int = 5,
    sigma: float = 1.5,
    shift_bars: int = 1,  # 1 = use bands from T-1 (no look-ahead)
    trend_lb: int = 10,
    trend_thresh: float = 0.05,
    vol_lb: int = 20,
    vol_thresh: float = 0.02,
    autoc_lb: int = 10,
    autoc_thresh: float = -0.1,
) -> pd.DataFrame:
    ret = px.pct_change().fillna(0.0)

    mu, sd = rolling_mean_std(px, bb_lb)
    if shift_bars:
        mu = mu.shift(shift_bars)
        sd = sd.shift(shift_bars)

    upper = mu + sigma * sd
    lower = mu - sigma * sd

    non_trending = cumret_window(px, trend_lb).abs() < trend_thresh
    low_vol = rolling_std_ret(ret, vol_lb) < vol_thresh
    reversion_hint = rolling_autocorr_lag1(ret, autoc_lb) < autoc_thresh

    filters_ok = (non_trending & low_vol & reversion_hint).astype(bool)

    long_sig = (px < lower) & filters_ok
    short_sig = (px > upper) & filters_ok

    signal_T = pd.Series(0.0, index=px.index, dtype=float)
    signal_T[long_sig.fillna(False)] = 1.0
    signal_T[short_sig.fillna(False)] = -1.0

    return pd.DataFrame(
        {
            "price": px,
            "ret": ret,
            "upper": upper,
            "lower": lower,
            "filters_ok": filters_ok.astype(float),
            "signal_T": signal_T,
        }
    )


# ---------- Position + PnL mechanics ----------


def build_exposure_and_returns(
    sig_df: pd.DataFrame,
    hold_days: int = 3,
    entry_bps: float = 1.5,
    tplus1_exec: bool = False,  # default False => T execution
):
    """
    T execution: entry at T, PnL accrues T+1 and T+2 for a 3-day hold from entry (no same-day PnL).
    T+1 execution: entry at T+1, PnL accrues T+2 and T+3 (latency realism variant).
    """
    idx = sig_df.index
    signal_T = sig_df["signal_T"].astype(float)
    ret = sig_df["ret"].astype(float)

    if tplus1_exec:
        entry_sig = signal_T.shift(1).fillna(0.0)
    else:
        entry_sig = signal_T.copy()

    # Exposure for PnL is the sum of active entries after they start accruing.
    # For 3 trading days from entry, PnL accrues on the 2 days AFTER entry:
    exposure_for_pnl = entry_sig.shift(1).fillna(0.0) + entry_sig.shift(2).fillna(0.0)

    # Costs: charged on entry day only, per |entry| (no exit cost)
    costs = -(entry_bps * 1e-4) * entry_sig.abs()

    raw_pnl = exposure_for_pnl * ret
    ret_unscaled = raw_pnl + costs

    out = pd.DataFrame(
        {
            "entry_signal": entry_sig,
            "exposure_for_pnl": exposure_for_pnl,
            "raw_pnl": raw_pnl,
            "entry_cost": costs,
            "ret_unscaled": ret_unscaled,
        },
        index=idx,
    )
    return out


# ---------- Rolling vol targeting ----------


def apply_vol_target(
    ret_unscaled: pd.Series,
    ann_target: float = 0.10,
    roll_win_days: int = 63,
    clamp_min: float = 0.5,
    clamp_max: float = 1.5,
):
    # Use information up to T-1
    rolling_std = (
        ret_unscaled.shift(1)
        .rolling(roll_win_days, min_periods=roll_win_days)
        .std(ddof=0)
    )
    realized_vol_ann = rolling_std * np.sqrt(252.0)
    scale_t = (ann_target / realized_vol_ann).clip(lower=clamp_min, upper=clamp_max)
    scale_t = scale_t.fillna(1.0)
    ret_scaled = ret_unscaled * scale_t
    return scale_t, ret_scaled


# ---------- Stats ----------


def sharpe_252(s: pd.Series) -> float:
    s = s.dropna()
    sd = s.std(ddof=0)
    return float("nan") if sd == 0 else float((s.mean() / sd) * np.sqrt(252.0))


# ---------- Runner ----------


def run_hookcore(
    px: pd.Series,
    # Bands & filters
    bb_lb: int = 5,
    sigma: float = 1.5,
    shift_bars: int = 1,
    trend_lb: int = 10,
    trend_thresh: float = 0.05,
    vol_lb: int = 20,
    vol_thresh: float = 0.02,
    autoc_lb: int = 10,
    autoc_thresh: float = -0.1,
    # Holds, costs, scaling
    hold_days: int = 3,
    entry_bps: float = 1.5,
    tplus1_exec: bool = False,
    ann_target: float = 0.10,
    roll_win_days: int = 63,
    clamp_min: float = 0.5,
    clamp_max: float = 1.5,
):
    sig = hookcore_signal(
        px=px,
        bb_lb=bb_lb,
        sigma=sigma,
        shift_bars=shift_bars,
        trend_lb=trend_lb,
        trend_thresh=trend_thresh,
        vol_lb=vol_lb,
        vol_thresh=vol_thresh,
        autoc_lb=autoc_lb,
        autoc_thresh=autoc_thresh,
    )
    mech = build_exposure_and_returns(
        sig_df=sig,
        hold_days=hold_days,
        entry_bps=entry_bps,
        tplus1_exec=tplus1_exec,
    )
    scale_t, ret_scaled = apply_vol_target(
        ret_unscaled=mech["ret_unscaled"],
        ann_target=ann_target,
        roll_win_days=roll_win_days,
        clamp_min=clamp_min,
        clamp_max=clamp_max,
    )

    signals = pd.concat(
        [sig, mech[["entry_signal", "exposure_for_pnl"]], scale_t.rename("scale_t")],
        axis=1,
    )
    pnl = pd.DataFrame(
        {
            "ret": sig["ret"],
            "raw_pnl": mech["raw_pnl"],
            "entry_cost": mech["entry_cost"],
            "ret_unscaled": mech["ret_unscaled"],
            "scale_t": scale_t,
            "ret_scaled": ret_scaled,
        }
    )
    return signals, pnl


def main():
    ap = argparse.ArgumentParser(
        description="Build HookCore v1.5 (Copper) — T execution; PnL from T+1; 63D rolling vol target."
    )
    # IO
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default="Raw")
    ap.add_argument("--date-col", default="Date")
    ap.add_argument("--price-col", default="copper_lme_3mo")
    ap.add_argument("--symbol", default="COPPER")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--oos-start", default="2018-01-01")
    ap.add_argument("--schema-path", default="Config/schema.yaml")

    # Bands & filters
    ap.add_argument("--bb-lb", type=int, default=5)
    ap.add_argument("--sigma", type=float, default=1.5)
    ap.add_argument(
        "--bands-shift", type=int, default=1
    )  # 1 = shift bands by 1 bar (no look-ahead)
    ap.add_argument("--trend-lb", type=int, default=10)
    ap.add_argument("--trend-thresh", type=float, default=0.05)
    ap.add_argument("--vol-lb", type=int, default=20)
    ap.add_argument("--vol-thresh", type=float, default=0.02)
    ap.add_argument("--autoc-lb", type=int, default=10)
    ap.add_argument("--autoc-thresh", type=float, default=-0.1)

    # Holds, costs, scaling, exec
    ap.add_argument("--hold-days", type=int, default=3)
    ap.add_argument("--bps", type=float, default=1.5)
    ap.add_argument(
        "--tplus1-exec",
        action="store_true",
        help="If set, execute at T+1 (latency realism variant).",
    )
    ap.add_argument("--ann-target", type=float, default=0.10)
    ap.add_argument("--roll-win", type=int, default=63)
    ap.add_argument("--scale-min", type=float, default=0.5)
    ap.add_argument("--scale-max", type=float, default=1.5)

    args = ap.parse_args()

    policy = load_execution_policy(args.schema_path)
    print(policy_banner(policy, sleeve_name="HookCore-Cu-v1.5-Tclose"))
    for w in warn_if_mismatch(
        policy,
        exec_weekdays=(0, 1, 2, 3, 4),
        fill_timing="close_T",
        vol_info="T-1",
        leverage_cap=args.scale_max,
        one_way_bps=args.bps,
    ):
        print(w)

    px = load_prices_excel_source_dates(
        args.excel, args.sheet, args.date_col, args.price_col, args.symbol
    )

    signals, pnl = run_hookcore(
        px=px,
        bb_lb=args.bb_lb,
        sigma=args.sigma,
        shift_bars=args.bands_shift,
        trend_lb=args.trend_lb,
        trend_thresh=args.trend_thresh,
        vol_lb=args.vol_lb,
        vol_thresh=args.vol_thresh,
        autoc_lb=args.autoc_lb,
        autoc_thresh=args.autoc_thresh,
        hold_days=args.hold_days,
        entry_bps=args.bps,
        tplus1_exec=args.tplus1_exec,
        ann_target=args.ann_target,
        roll_win_days=args.roll_win,
        clamp_min=args.scale_min,
        clamp_max=args.scale_max,
    )

    # --- Outputs ---
    out_root = Path(args.outdir) / "copper" / "pricing" / "hookcore_v15_Tclose"
    out_root.mkdir(parents=True, exist_ok=True)
    signals.to_csv(out_root / "signals.csv", index_label="dt")
    pnl.to_csv(out_root / "pnl_daily.csv", index_label="dt")

    # IS/OOS split
    oos_start = pd.Timestamp(args.oos_start)
    is_ret = pnl.loc[pnl.index < oos_start, "ret_scaled"].dropna()
    oos_ret = pnl.loc[pnl.index >= oos_start, "ret_scaled"].dropna()

    summary = {
        "params": {
            "bb_lb": args.bb_lb,
            "sigma": args.sigma,
            "bands_shift": args.bands_shift,
            "trend_lb": args.trend_lb,
            "trend_thresh": args.trend_thresh,
            "vol_lb": args.vol_lb,
            "vol_thresh": args.vol_thresh,
            "autoc_lb": args.autoc_lb,
            "autoc_thresh": args.autoc_thresh,
            "hold_days": args.hold_days,
            "bps": args.bps,
            "ann_target": args.ann_target,
            "roll_win": args.roll_win,
            "scale_min": args.scale_min,
            "scale_max": args.scale_max,
            "execution": (
                "Daily T close; PnL from T+1"
                if not args.tplus1_exec
                else "Daily T+1 execution; PnL from T+2"
            ),
        },
        "ALL": {
            "sharpe_252": sharpe_252(pnl["ret_scaled"]),
            "n": int(pnl["ret_scaled"].size),
        },
        "IS": {"sharpe_252": sharpe_252(is_ret), "n": int(is_ret.size)},
        "OOS": {"sharpe_252": sharpe_252(oos_ret), "n": int(oos_ret.size)},
    }
    with open(out_root / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"[hookcore] wrote → {out_root}")


if __name__ == "__main__":
    main()
