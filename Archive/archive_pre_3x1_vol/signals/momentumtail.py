# src/signals/momentumtail.py
"""
MomentumTail Signal Logic (Layer B)
------------------------------------
Targets extreme directional "tail" events — high-conviction crisis alpha.
Combines volatility regime detection with trend breakouts.
Returns only: pos_raw (±1 or 0)
"""

import numpy as np
import pandas as pd


def generate_momentumtail_signal(
    df: pd.DataFrame,
    # Volatility regime (IV-based)
    iv_ma_lookback: int = 63,
    iv_spike_threshold: float = 1.5,  # IV must be 1.5x its average
    # Trend confirmation (Donchian)
    donchian_lookback: int = 20,
    # Momentum persistence (ATR)
    atr_lookback: int = 14,
    atr_ma_lookback: int = 63,
    atr_threshold: float = 1.2,  # ATR must be 1.2x its average
    # Risk controls
    signal_shift: int = 1,  # Use data up to T-1
) -> pd.Series:
    """
    Generate MomentumTail position signal.

    Logic:
        1. IV Spike: Current IV > MA(IV) * threshold
        2. Donchian Breakout: Price at 20-day high (long) or low (short)
        3. ATR Elevated: ATR > MA(ATR) * threshold (vol persistence)
        4. Enter: All 3 conditions true
        5. Exit: When IV normalizes or trend breaks

    Args:
        df: DataFrame with 'price' and 'iv' columns
        iv_ma_lookback: Days for IV moving average
        iv_spike_threshold: Multiplier for IV spike detection
        donchian_lookback: Days for Donchian channel
        atr_lookback: Days for ATR calculation
        atr_ma_lookback: Days for ATR moving average
        atr_threshold: Multiplier for ATR elevation detection
        signal_shift: Shift indicators by N bars (1 = use T-1 data)

    Returns:
        pd.Series with values in {-1, 0, +1}
    """

    df = df.copy()
    price = df["price"]
    iv = df["iv"]

    # ========== 1. VOLATILITY REGIME (IV SPIKE) ==========
    iv_ma = iv.rolling(iv_ma_lookback, min_periods=iv_ma_lookback).mean()
    iv_spike = iv > (iv_ma * iv_spike_threshold)

    # Shift by 1 bar (use info up to T-1)
    if signal_shift > 0:
        iv_spike = iv_spike.shift(signal_shift)

    # ========== 2. TREND CONFIRMATION (DONCHIAN BREAKOUT) ==========
    rolling_high = price.rolling(donchian_lookback, min_periods=donchian_lookback).max()
    rolling_low = price.rolling(donchian_lookback, min_periods=donchian_lookback).min()

    breakout_high = price >= rolling_high
    breakout_low = price <= rolling_low

    if signal_shift > 0:
        breakout_high = breakout_high.shift(signal_shift)
        breakout_low = breakout_low.shift(signal_shift)

    # ========== 3. MOMENTUM PERSISTENCE (ATR FILTER) ==========
    # True Range
    high = price  # Using price as proxy (proper ATR needs high/low/close)
    low = price
    prev_close = price.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # ATR (smoothed true range)
    atr = true_range.rolling(atr_lookback, min_periods=atr_lookback).mean()
    atr_ma = atr.rolling(atr_ma_lookback, min_periods=atr_ma_lookback).mean()

    atr_elevated = atr > (atr_ma * atr_threshold)

    if signal_shift > 0:
        atr_elevated = atr_elevated.shift(signal_shift)

    # ========== 4. COMBINE FILTERS ==========
    # Long: IV spike + breakout high + ATR elevated
    long_entry = iv_spike & breakout_high & atr_elevated

    # Short: IV spike + breakout low + ATR elevated
    short_entry = iv_spike & breakout_low & atr_elevated

    # Exit: IV normalizes (back below threshold)
    iv_normalized = iv < (iv_ma * 1.1)  # Exit when IV drops to 1.1x average

    if signal_shift > 0:
        iv_normalized = iv_normalized.shift(signal_shift)

    # ========== 5. BUILD POSITION SERIES WITH PERSISTENCE ==========
    pos_raw = pd.Series(0.0, index=df.index)

    for i in range(len(df)):
        if i == 0:
            pos_raw.iloc[i] = 0.0
        else:
            prev_pos = pos_raw.iloc[i - 1]

            # Enter long
            if long_entry.iloc[i]:
                pos_raw.iloc[i] = 1.0
            # Enter short
            elif short_entry.iloc[i]:
                pos_raw.iloc[i] = -1.0
            # Exit when IV normalizes
            elif prev_pos != 0 and iv_normalized.iloc[i]:
                pos_raw.iloc[i] = 0.0
            # Hold previous position
            else:
                pos_raw.iloc[i] = prev_pos

    return pos_raw
