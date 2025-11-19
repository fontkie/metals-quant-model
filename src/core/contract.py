# src/core/contract.py
"""
Layer A: Immutable Execution Contract
--------------------------------------
T→T+1 accrual, costs on Δpos, vol targeting, leverage cap.
ALL sleeves use this. No exceptions.
"""

import numpy as np
import pandas as pd


def build_core(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """
    Build Layer A execution contract.

    Input:
        df: canonical CSV with columns ['date', 'price'] (lowercase)
        cfg: YAML config dict

    Output:
        (daily_df, metrics_dict)
    """

    # ========== 1. VALIDATE INPUT ==========
    assert (
        "date" in df.columns and "price" in df.columns
    ), "Input must have lowercase 'date' and 'price' columns"

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # ========== 2. EXTRACT CONFIG ==========
    policy = cfg["policy"]

    # Sizing
    sizing = policy["sizing"]
    ann_target = sizing["ann_target"]
    vol_lookback = sizing["vol_lookback_days_default"]
    leverage_cap = sizing["leverage_cap_default"]

    # Costs
    costs = policy["costs"]
    one_way_bps = costs["one_way_bps_default"]

    # ========== 3. CALCULATE RETURNS ==========
    df["ret"] = df["price"].pct_change().fillna(0.0)

    # ========== 4. GENERATE RAW SIGNAL (HOOK FOR SLEEVES) ==========
    # HookCore will inject 'pos_raw' here via signal function
    # For now, placeholder (Layer B provides this)
    if "pos_raw" not in df.columns:
        df["pos_raw"] = 0.0  # placeholder

    # ========== 5. VOL TARGETING ==========
    # Realized vol (use returns up to T-1)
    rolling_std = (
        df["ret"].shift(1).rolling(vol_lookback, min_periods=vol_lookback).std(ddof=0)
    )
    realized_vol = rolling_std * np.sqrt(252)

    # Target leverage
    target_lev = (ann_target / realized_vol).clip(upper=leverage_cap).fillna(1.0)

    # Scaled position
    df["pos"] = (df["pos_raw"] * target_lev).clip(
        lower=-leverage_cap, upper=leverage_cap
    )

    # ========== 6. T→T+1 ACCRUAL ==========
    df["pos_for_ret_t"] = df["pos"].shift(1).fillna(0.0)

    # ========== 7. COSTS (ON Δpos ONLY) ==========
    df["trade"] = df["pos"].diff().fillna(0.0)
    df["cost"] = -df["trade"].abs() * (one_way_bps / 10_000)

    # ========== 8. PNL ==========
    df["pnl_gross"] = df["pos_for_ret_t"] * df["ret"]
    df["pnl_net"] = df["pnl_gross"] + df["cost"]

    # ========== 9. METRICS ==========
    pnl_net_clean = df["pnl_net"].dropna()
    N = len(pnl_net_clean)

    # Compounded return
    cum_ret = (1 + pnl_net_clean).prod() - 1
    annual_return = (1 + cum_ret) ** (252 / N) - 1 if N > 0 else 0.0

    # Vol & Sharpe
    annual_vol = pnl_net_clean.std(ddof=0) * np.sqrt(252) if N > 0 else 0.0
    sharpe = (
        (pnl_net_clean.mean() / pnl_net_clean.std(ddof=0)) * np.sqrt(252)
        if N > 0 and pnl_net_clean.std(ddof=0) > 0
        else 0.0
    )

    # Max drawdown
    cum_pnl = (1 + pnl_net_clean).cumprod()
    running_max = cum_pnl.cummax()
    drawdown = (cum_pnl - running_max) / running_max
    max_drawdown = drawdown.min() if N > 0 else 0.0

    metrics = {
        "annual_return": float(annual_return),
        "annual_vol": float(annual_vol),
        "sharpe": float(sharpe),
        "max_drawdown": float(max_drawdown),
        "obs": int(N),
        "cost_bps": float(one_way_bps),
    }

    # ========== 10. OUTPUT DATAFRAME ==========
    output_cols = [
        "date",
        "price",
        "ret",
        "pos",
        "pos_for_ret_t",
        "trade",
        "cost",
        "pnl_gross",
        "pnl_net",
    ]
    daily_df = df[output_cols].copy()

    return daily_df, metrics
