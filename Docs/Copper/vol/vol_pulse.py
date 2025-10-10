from __future__ import annotations
import math, yaml
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional

@dataclass
class VolPulseConfig:
    target_vol: float = 0.10
    size_floor: float = 0.3
    size_cap: float = 3.0
    percentile_window_days: int = 252
    guardrails_window_days: int = 756
    calm_percentile_in: float = 0.30
    calm_percentile_out: float = 0.34
    high_percentile_in: float = 0.70
    high_percentile_out: float = 0.66
    calm_quantile: float = 0.20
    high_quantile: float = 0.90
    crisis_exit_percentile: float = 0.60
    crisis_use_three_day_exit: bool = True
    spike_rvjump_sigma: float = 2.0
    spike_pctl_jump: float = 0.25
    spike_ret_sigma: float = 3.0
    drv5_epsilon: float = 0.002
    col_date: str = "Date"
    col_price: str = "Price"

def _clipped_size_mult(rv21: float, target: float, floor: float, cap: float) -> float:
    if rv21 is None or not np.isfinite(rv21) or rv21 <= 0:
        return floor
    return float(np.clip(target / rv21, floor, cap))

def _rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    values = series.values
    n = len(values)
    out = np.full(n, np.nan, dtype=float)
    for i in range(n):
        if i < window:
            continue
        prev = values[i-window:i]
        x = values[i]
        if not np.isfinite(x) or np.isnan(prev).any():
            continue
        lo, hi = np.nanmin(prev), np.nanmax(prev)
        if x <= lo:
            out[i] = 0.0
        elif x >= hi:
            out[i] = 1.0
        else:
            out[i] = (np.sum(prev <= x) - 1) / (window - 1)
    return pd.Series(out, index=series.index)

def compute_vol_pulse(df: pd.DataFrame, config_path: Optional[str]=None, config: Optional[VolPulseConfig]=None) -> pd.DataFrame:
    if config is None:
        if config_path is None:
            cfg = VolPulseConfig()
        else:
            with open(config_path, "r") as f:
                y = yaml.safe_load(f)
            cols = y.get("columns", {})
            cfg = VolPulseConfig(
                target_vol=y.get("target_vol", 0.10),
                size_floor=y.get("size_floor", 0.3),
                size_cap=y.get("size_cap", 3.0),
                percentile_window_days=y.get("percentile_window_days", 252),
                guardrails_window_days=y.get("guardrails_window_days", 756),
                calm_percentile_in=y.get("calm_percentile_in", 0.30),
                calm_percentile_out=y.get("calm_percentile_out", 0.34),
                high_percentile_in=y.get("high_percentile_in", 0.70),
                high_percentile_out=y.get("high_percentile_out", 0.66),
                calm_quantile=y.get("calm_quantile", 0.20),
                high_quantile=y.get("high_quantile", 0.90),
                crisis_exit_percentile=y.get("crisis_exit_percentile", 0.60),
                crisis_use_three_day_exit=y.get("crisis_use_three_day_exit", True),
                spike_rvjump_sigma=y.get("spike_rvjump_sigma", 2.0),
                spike_pctl_jump=y.get("spike_pctl_jump", 0.25),
                spike_ret_sigma=y.get("spike_ret_sigma", 3.0),
                drv5_epsilon=y.get("drv5_epsilon", 0.002),
            )
            cfg.col_date = cols.get("date", "Date")
            cfg.col_price = cols.get("price", "Price")
    else:
        cfg = config

    df = df.copy().sort_values(cfg.col_date).reset_index(drop=True)
    df["ret_log"] = np.log(df[cfg.col_price] / df[cfg.col_price].shift(1))
    df["rv21"] = df["ret_log"].rolling(21, min_periods=21).std() * math.sqrt(252)

    # Percentile of RV21 vs prior window
    pctl = _rolling_percentile(df["rv21"], cfg.percentile_window_days)
    df["pctl"] = pctl

    df["drv1"] = df["rv21"].diff()
    df["drv5"] = df["rv21"] - df["rv21"].shift(5)

    # Guardrails as rolling quantiles over prior guardrails_window_days
    w = cfg.guardrails_window_days
    df["calm_abs_t"] = df["rv21"].shift(1).rolling(w, min_periods=w).quantile(cfg.calm_quantile)
    df["high_abs_t"] = df["rv21"].shift(1).rolling(w, min_periods=w).quantile(cfg.high_quantile)

    calm = np.zeros(len(df), dtype=int)
    high = np.zeros(len(df), dtype=int)
    rising = np.zeros(len(df), dtype=int)
    falling = np.zeros(len(df), dtype=int)

    for i in range(len(df)):
        rv = df.at[i, "rv21"]
        pct = df.at[i, "pctl"]
        if not np.isfinite(rv) or not np.isfinite(pct):
            continue
        enter_calm = (pct <= cfg.calm_percentile_in) or (
            np.isfinite(df.at[i, "calm_abs_t"]) and rv <= df.at[i, "calm_abs_t"]
        )
        stay_calm = (calm[i-1]==1 if i>0 else False) and (pct <= cfg.calm_percentile_out)
        calm[i] = int(enter_calm or stay_calm)

        enter_high = (pct >= cfg.high_percentile_in) or (
            np.isfinite(df.at[i, "high_abs_t"]) and rv >= df.at[i, "high_abs_t"]
        )
        stay_high = (high[i-1]==1 if i>0 else False) and (pct >= cfg.high_percentile_out)
        high[i] = int(enter_high or stay_high)

        if calm[i]==0 and high[i]==0:
            d5 = df.at[i, "drv5"]
            if np.isfinite(d5):
                if d5 > cfg.drv5_epsilon:
                    rising[i] = 1
                elif d5 < -cfg.drv5_epsilon:
                    falling[i] = 1

    df["calm"] = calm
    df["high"] = high
    df["rising"] = rising
    df["falling"] = falling

    # State label with precedence High > Rising > Calm > Falling; carry-forward if none
    state = []
    last = ""
    for i in range(len(df)):
        if not np.isfinite(df.at[i,"rv21"]) or not np.isfinite(df.at[i,"pctl"]):
            state.append("")
            continue
        lab = ""
        if high[i]==1: lab = "High"
        elif rising[i]==1: lab = "Rising"
        elif calm[i]==1: lab = "Calm"
        elif falling[i]==1: lab = "Falling"
        else: lab = last
        state.append(lab)
        last = lab
    df["state"] = state

    # Spikes
    sigma_drv1 = df["drv1"].rolling(cfg.percentile_window_days, min_periods=cfg.percentile_window_days).std()
    df["spike_rvjump"] = (df["drv1"].abs() > cfg.spike_rvjump_sigma * sigma_drv1).astype("Int64")
    sigma_ret = df["ret_log"].rolling(cfg.percentile_window_days, min_periods=cfg.percentile_window_days).std()
    df["spike_ret"] = (df["ret_log"].abs() > cfg.spike_ret_sigma * sigma_ret).astype("Int64")
    df["spike_pctljump"] = (df["pctl"].diff() > cfg.spike_pctl_jump).astype("Int64")
    df["spike_any"] = pd.concat([df["spike_rvjump"], df["spike_pctljump"], df["spike_ret"]], axis=1).max(axis=1).astype("Int64")

    # Crisis overlay
    crisis = []
    on = False
    for i in range(len(df)):
        rv_ok = np.isfinite(df.at[i,"rv21"])
        p_ok = np.isfinite(df.at[i,"pctl"])
        if not (rv_ok and p_ok):
            crisis.append(np.nan)
            continue
        if df.at[i,"spike_any"]==1 or high[i]==1:
            on = True
        else:
            if cfg.crisis_use_three_day_exit:
                if i>=2 and all(df.loc[i-j, "pctl"] < cfg.crisis_exit_percentile for j in range(0,3)):
                    on = False
            else:
                if df.at[i,"pctl"] < cfg.crisis_exit_percentile:
                    on = False
        crisis.append(int(on))
    df["crisis"] = crisis

    # Controls
    df["size_mult"] = df["rv21"].apply(lambda x: _clipped_size_mult(x, cfg.target_vol, cfg.size_floor, cfg.size_cap))
    df["allow_new"] = ((df["crisis"]!=1) & (df["state"].isin(["Calm","Falling"]))).astype("Int64")
    df["stop_mult"] = np.where((df["crisis"]==1) | (df["state"]=="High"), 0.8, 1.0)

    order = [cfg.col_date, cfg.col_price, "ret_log", "rv21", "pctl", "drv1", "drv5",
             "calm", "high", "rising", "falling", "state", "crisis",
             "size_mult", "allow_new", "stop_mult",
             "spike_rvjump", "spike_pctljump", "spike_ret", "spike_any",
             "calm_abs_t", "high_abs_t"]
    order = [c for c in order if c in df.columns]
    return df[order]
