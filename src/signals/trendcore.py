# src/signals/trendcore.py
"""
TrendCore Signal Logic (Layer B)
---------------------------------
Simple moving average crossover — the backbone trend-following sleeve.
Returns only: pos_raw (±1 or 0)
"""

import numpy as np
import pandas as pd


def generate_trendcore_signal(
    df: pd.DataFrame,
    ma_lookback: int = 50,
    buffer_pct: float = 0.0,  # Optional buffer to reduce whipsaw
    ma_shift: int = 1,  # 1 = use MA from T-1 (no look-ahead)
) -> pd.Series:
    """
    Generate TrendCore position signal.

    Logic:
        - Long (+1):  price > MA * (1 + buffer)
        - Short (-1): price < MA * (1 - buffer)
        - Flat (0):   price in buffer zone

    Args:
        df: DataFrame with 'price' column
        ma_lookback: Moving average window (days)
        buffer_pct: Buffer zone around MA (e.g., 0.01 = 1%)
        ma_shift: Shift MA by N bars (1 = use T-1 data)

    Returns:
        pd.Series with values in {-1, 0, +1}
    """

    df = df.copy()
    price = df["price"]

    # ========== MOVING AVERAGE ==========
    ma = price.rolling(ma_lookback, min_periods=ma_lookback).mean()

    # Shift MA by 1 bar (use info up to T-1)
    if ma_shift > 0:
        ma = ma.shift(ma_shift)

    # ========== BUFFER ZONES ==========
    upper_threshold = ma * (1 + buffer_pct)
    lower_threshold = ma * (1 - buffer_pct)

    # ========== GENERATE SIGNAL ==========
    pos_raw = pd.Series(0.0, index=df.index)

    # Long: price above upper threshold
    pos_raw[price > upper_threshold] = 1.0

    # Short: price below lower threshold
    pos_raw[price < lower_threshold] = -1.0

    # Flat: price in buffer zone (already initialized to 0)

    return pos_raw
