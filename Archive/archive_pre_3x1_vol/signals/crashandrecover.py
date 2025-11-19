# src/signals/crashandrecover.py
"""
CrashAndRecover Signal Logic (Layer B)
---------------------------------------
Swing structure detection with volume confirmation.
Detects "higher lows" (recovery) and "lower highs" (crashes).
Returns only: pos_raw (±1 or 0)
"""

import numpy as np
import pandas as pd


def generate_crashandrecover_signal(
    df: pd.DataFrame,
    # Swing structure detection
    structure_window: int = 60,
    atr_lookback: int = 20,
    atr_tolerance: float = 0.5,  # 0.5x ATR buffer
    # Volume confirmation
    volume_lookback: int = 20,
    volume_threshold: float = 2.0,  # Volume > 2x average
    # Exit logic
    exit_timeout_days: int = 90,
    # Risk controls
    signal_shift: int = 1,
) -> pd.Series:
    """
    Generate CrashAndRecover position signal.

    Logic (Swing Structure with Volume):
        1. Detect 60-day swing high and swing low
        2. Calculate ATR buffer (0.5x 20-day ATR)
        3. "Higher Low": Price crosses above (swing_low + ATR), volume > 2x → LONG
        4. "Lower High": Price crosses below (swing_high - ATR), volume > 2x → SHORT
        5. Hold until timeout (90 days) or opposite signal

    Args:
        df: DataFrame with 'price' and 'volume' columns
        structure_window: Days for swing high/low detection
        atr_lookback: Days for ATR calculation
        atr_tolerance: ATR multiplier for buffer
        volume_lookback: Days for volume moving average
        volume_threshold: Volume spike multiplier (2x = high threshold)
        exit_timeout_days: Days to hold before auto-exit
        signal_shift: Shift indicators by N bars (1 = use T-1 data)

    Returns:
        pd.Series with values in {-1, 0, +1}
    """

    df = df.copy()
    price = df["price"]
    volume = df["volume"]

    # ========== 1. SWING STRUCTURE (60-DAY HIGH/LOW) ==========
    swing_high = price.rolling(structure_window, min_periods=structure_window).max()
    swing_low = price.rolling(structure_window, min_periods=structure_window).min()

    # Shift by 1 bar (no look-ahead)
    if signal_shift > 0:
        swing_high = swing_high.shift(signal_shift)
        swing_low = swing_low.shift(signal_shift)

    # ========== 2. ATR BUFFER ==========
    # True Range (simplified - using price only as proxy)
    high = price
    low = price
    prev_close = price.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(atr_lookback, min_periods=atr_lookback).mean()

    # ATR buffer
    atr_buffer = atr * atr_tolerance

    if signal_shift > 0:
        atr_buffer = atr_buffer.shift(signal_shift)

    # ========== 3. VOLUME SPIKE CONFIRMATION ==========
    volume_ma = volume.rolling(volume_lookback, min_periods=volume_lookback).mean()
    volume_spike = volume > (volume_ma * volume_threshold)

    if signal_shift > 0:
        volume_spike = volume_spike.shift(signal_shift)

    # ========== 4. STRUCTURE BREAK EVENTS ==========
    # "Higher Low": Price crosses above swing_low + ATR buffer
    higher_low_level = swing_low + atr_buffer
    price_prev = price.shift(1)

    higher_low_event = (
        (price > higher_low_level)  # Above threshold today
        & (
            price_prev <= higher_low_level.shift(1)
        )  # Was below yesterday (edge trigger)
        & volume_spike  # Volume confirms
    )

    # "Lower High": Price crosses below swing_high - ATR buffer
    lower_high_level = swing_high - atr_buffer

    lower_high_event = (
        (price < lower_high_level)  # Below threshold today
        & (
            price_prev >= lower_high_level.shift(1)
        )  # Was above yesterday (edge trigger)
        & volume_spike  # Volume confirms
    )

    # ========== 5. POSITION LOGIC WITH TIMEOUT ==========
    pos_raw = pd.Series(0.0, index=df.index)
    entry_date = pd.Series(pd.NaT, index=df.index)

    # Get dates as array for faster access
    dates = (
        pd.to_datetime(df.index)
        if isinstance(df.index, pd.DatetimeIndex)
        else pd.to_datetime(df["date"].values)
    )

    for i in range(1, len(df)):
        prev_pos = pos_raw.iloc[i - 1]
        prev_entry = entry_date.iloc[i - 1]

        # Check timeout (90 days since entry)
        if pd.notna(prev_entry):
            days_held = (dates[i] - prev_entry).days
            if days_held >= exit_timeout_days:
                # Exit due to timeout
                pos_raw.iloc[i] = 0.0
                entry_date.iloc[i] = pd.NaT
                continue

        # Higher Low event → Enter LONG
        if higher_low_event.iloc[i]:
            pos_raw.iloc[i] = 1.0
            entry_date.iloc[i] = dates[i]

        # Lower High event → Enter SHORT
        elif lower_high_event.iloc[i]:
            pos_raw.iloc[i] = -1.0
            entry_date.iloc[i] = dates[i]

        # Hold previous position
        else:
            pos_raw.iloc[i] = prev_pos
            entry_date.iloc[i] = prev_entry

    return pos_raw
