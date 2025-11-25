# src/signals/trendimpulse.py
"""
TrendImpulse Signal Logic (Layer B)
------------------------------------
Captures short-term momentum bursts using ROC z-score.
Faster and more reactive than TrendCore.
Returns only: pos_raw (±1 or 0)
"""

import numpy as np
import pandas as pd


def generate_trendimpulse_signal(
    df: pd.DataFrame,
    roc_lookback: int = 20,
    zscore_lookback: int = 63,
    entry_threshold: float = 0.5,
    exit_threshold: float = 0.0,
    trend_filter_enabled: bool = True,
    trend_ma_lookback: int = 50,
    ma_shift: int = 1,
) -> pd.Series:
    """
    Generate TrendImpulse position signal.

    Logic:
        1. Calculate Rate of Change (ROC) over lookback period
        2. Normalize ROC by rolling volatility (z-score)
        3. Enter when z-score crosses entry threshold
        4. Exit when z-score crosses exit threshold
        5. Optional: filter trades by medium-term trend

    Args:
        df: DataFrame with 'price' column
        roc_lookback: Days for rate of change calculation
        zscore_lookback: Days for z-score normalization
        entry_threshold: Z-score threshold to enter (e.g., 0.5 = 0.5 std dev)
        exit_threshold: Z-score threshold to exit (e.g., 0.0 = neutral)
        trend_filter_enabled: Only trade in direction of medium-term trend
        trend_ma_lookback: MA period for trend filter
        ma_shift: Shift indicators by N bars (1 = use T-1 data)

    Returns:
        pd.Series with values in {-1, 0, +1}
    """

    df = df.copy()
    price = df["price"]

    # ========== RATE OF CHANGE ==========
    roc = (price / price.shift(roc_lookback)) - 1.0

    # ========== Z-SCORE (NORMALIZED MOMENTUM) ==========
    roc_mean = roc.rolling(zscore_lookback, min_periods=zscore_lookback).mean()
    roc_std = roc.rolling(zscore_lookback, min_periods=zscore_lookback).std(ddof=0)

    # Avoid division by zero
    roc_std = roc_std.replace(0, np.nan)

    zscore = (roc - roc_mean) / roc_std

    # Shift z-score by 1 bar (use info up to T-1)
    if ma_shift > 0:
        zscore = zscore.shift(ma_shift)

    # ========== TREND FILTER (OPTIONAL) ==========
    if trend_filter_enabled:
        trend_ma = price.rolling(
            trend_ma_lookback, min_periods=trend_ma_lookback
        ).mean()
        if ma_shift > 0:
            trend_ma = trend_ma.shift(ma_shift)

        uptrend = price > trend_ma
        downtrend = price < trend_ma
    else:
        # No filter: always allow trades
        uptrend = pd.Series(True, index=df.index)
        downtrend = pd.Series(True, index=df.index)

    # ========== GENERATE SIGNAL ==========
    pos_raw = pd.Series(0.0, index=df.index)

    # Long: positive momentum burst + uptrend
    long_signal = (zscore > entry_threshold) & uptrend

    # Short: negative momentum burst + downtrend
    short_signal = (zscore < -entry_threshold) & downtrend

    # Exit: momentum fades
    exit_long = zscore < exit_threshold
    exit_short = zscore > -exit_threshold

    # Build position series with persistence (hold until exit)
    for i in range(len(df)):
        if i == 0:
            pos_raw.iloc[i] = 0.0
        else:
            prev_pos = pos_raw.iloc[i - 1]

            # Enter long
            if long_signal.iloc[i]:
                pos_raw.iloc[i] = 1.0
            # Enter short
            elif short_signal.iloc[i]:
                pos_raw.iloc[i] = -1.0
            # Exit long
            elif prev_pos > 0 and exit_long.iloc[i]:
                pos_raw.iloc[i] = 0.0
            # Exit short
            elif prev_pos < 0 and exit_short.iloc[i]:
                pos_raw.iloc[i] = 0.0
            # Hold previous position
            else:
                pos_raw.iloc[i] = prev_pos

    return pos_raw
