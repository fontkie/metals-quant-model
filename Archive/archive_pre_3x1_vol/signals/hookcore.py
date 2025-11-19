# src/signals/hookcore.py
"""
HookCore Signal Logic (Layer B)
--------------------------------
Bollinger-band mean reversion with regime filters.
Returns only: pos_raw (±1 or 0)
"""

import numpy as np
import pandas as pd


def generate_hookcore_signal(
    df: pd.DataFrame,
    bb_lookback: int = 5,
    bb_sigma: float = 1.5,
    bb_shift: int = 1,  # 1 = use bands from T-1 (no look-ahead)
    trend_lookback: int = 10,
    trend_thresh: float = 0.05,
    vol_lookback: int = 20,
    vol_thresh: float = 0.02,
    autocorr_lookback: int = 10,
    autocorr_thresh: float = -0.1,
    hold_days: int = 3,
) -> pd.Series:
    """
    Generate HookCore position signal.

    Returns:
        pd.Series with values in {-1, 0, +1}
    """

    df = df.copy()
    price = df["price"]
    ret = df["ret"]

    # ========== BOLLINGER BANDS ==========
    mu = price.rolling(bb_lookback, min_periods=bb_lookback).mean()
    sd = price.rolling(bb_lookback, min_periods=bb_lookback).std(ddof=0)

    # Shift bands by 1 bar (use info up to T-1)
    if bb_shift > 0:
        mu = mu.shift(bb_shift)
        sd = sd.shift(bb_shift)

    upper_band = mu + bb_sigma * sd
    lower_band = mu - bb_sigma * sd

    # ========== REGIME FILTERS ==========
    # 1. Non-trending: |cumulative return over lookback| < threshold
    cumret = (price / price.shift(trend_lookback)) - 1.0
    non_trending = cumret.abs() < trend_thresh

    # 2. Low vol: rolling std of returns < threshold
    rolling_vol = ret.rolling(vol_lookback, min_periods=vol_lookback).std(ddof=0)
    low_vol = rolling_vol < vol_thresh

    # 3. Negative autocorr: mean-reverting behavior
    autocorr = ret.rolling(autocorr_lookback, min_periods=autocorr_lookback).apply(
        lambda x: x.corr(pd.Series(x).shift(1)) if len(x) > 1 else np.nan, raw=False
    )
    reversion_hint = autocorr < autocorr_thresh

    # All filters must pass
    filters_ok = non_trending & low_vol & reversion_hint

    # ========== ENTRY SIGNALS ==========
    long_entry = (price < lower_band) & filters_ok
    short_entry = (price > upper_band) & filters_ok

    # ========== POSITION LOGIC (3-DAY HOLD WITH OVERLAPS) ==========
    # Entry signal at T → position active for T+1, T+2, T+3 (3 days)
    # PnL accrues on T+1 and T+2 (not on T due to T→T+1 accrual in Layer A)

    # Convert entry signals to positions
    pos_long = long_entry.astype(float)
    pos_short = -short_entry.astype(float)
    entry_signal = pos_long + pos_short  # {-1, 0, +1}

    # Overlapping holds: sum positions from last 3 entry signals
    pos_raw = pd.Series(0.0, index=df.index)
    for lag in range(hold_days):
        pos_raw += entry_signal.shift(lag).fillna(0.0)

    # Clip to {-1, 0, +1} range (in case multiple entries stack)
    pos_raw = pos_raw.clip(-1.0, 1.0)

    return pos_raw
