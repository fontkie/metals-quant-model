# src/signals/hookcore_v5.py
"""
HookCore v5.0 Signal Logic
--------------------------
Longs-only mean reversion with regime filtering.
Uses V4's PROVEN BB parameters (20d/2.0σ from diagnostics).

Evolution:
- V4: 20d/2.0σ, longs-only, all regimes → Sharpe 0.26
- V5 attempt 1: 5d/1.5σ → FAILED (longs Sharpe -0.05)
- V5 final: 20d/2.0σ + regime filter → Expected 0.40-0.60

Strategy:
1. BB 20d/2.0σ (v4 proven parameters)
2. Longs-only (shorts tested: -0.79 Sharpe)
3. Regime filter (uptrends OR medium vol)
4. Volume confirmation (1.3x spike)

V4 Regime Performance:
- Uptrends: Sharpe 3.27 ⚡
- Medium vol: Sharpe 0.90 ✓
- Low vol: Sharpe -0.67 ❌
- Downtrends: Sharpe -5.42 ❌

Returns: pos_raw ∈ {0, +1}
"""

import numpy as np
import pandas as pd


def generate_hookcore_v5_signal(
    df: pd.DataFrame,
    # Bollinger bands (V4 PROVEN parameters)
    bb_lookback: int = 20,  # CHANGED: 5 → 20 (v4 actual)
    bb_sigma: float = 2.0,  # CHANGED: 1.5 → 2.0 (v4 actual)
    bb_shift: int = 1,
    # Volume confirmation
    volume_spike_threshold: float = 1.3,
    volume_lookback: int = 20,
    # Regime filter parameters
    uptrend_lookback: int = 100,
    uptrend_threshold: float = 1.05,  # Price > 1.05x price 100d ago
    vol_lookback: int = 63,
    vol_percentile_window: int = 252,
    medium_vol_low: float = 0.30,  # 30th percentile
    medium_vol_high: float = 0.70,  # 70th percentile
    # Hold period
    hold_days: int = 3,
    # Unused (compatibility)
    stocks: pd.Series = None,
    iv_1mo: pd.Series = None,
    curve_spread_pct: pd.Series = None,
    stocks_tight_threshold: float = 0.40,
    iv_shutdown: float = 30.0,
    curve_extreme_backwardation: float = 3.0,
    curve_weak_contango: float = -3.0,
    trend_lookback: int = 10,
    trend_thresh: float = 0.05,
    vol_thresh: float = 0.025,
    autocorr_lookback: int = 10,
    autocorr_thresh: float = -0.05,
) -> pd.Series:
    """
    Generate HookCore v5.0 signal (longs-only with regime filtering).

    Uses V4's PROVEN parameters:
    - BB: 20d/2.0σ (from v4 diagnostics - what actually worked)
    - Longs-only (shorts: -0.79 Sharpe, removed)
    - Regime filter: Only trade in uptrends OR medium vol
    - Volume confirmation
    - Target: Sharpe 0.40-0.60 (v4's 0.26 + regime filtering)

    Args:
        df: DataFrame with ['date', 'price', 'ret', 'volume']
        bb_lookback: Bollinger lookback (20 days - v4 proven)
        bb_sigma: Bollinger sigma (2.0 - v4 proven)
        uptrend_lookback: Days for trend check (100)
        uptrend_threshold: Min ratio for uptrend (1.05 = 5% gain)
        vol_lookback: Days for vol calculation (63)
        vol_percentile_window: Window for vol ranking (252)
        medium_vol_low: Low percentile for medium vol (0.30)
        medium_vol_high: High percentile for medium vol (0.70)
        hold_days: Hold period (3 days)

    Returns:
        pd.Series in {0, +1} (longs-only)
    """

    df = df.copy()
    price = df["price"]
    ret = df["ret"]

    # Initialize
    pos_raw = pd.Series(0.0, index=df.index)

    # ========== REGIME FILTER ==========
    # 1. Uptrend: price / price 100d ago > 1.05
    price_ratio = price / price.shift(uptrend_lookback)
    is_uptrend = price_ratio > uptrend_threshold

    # 2. Medium vol: between 30th-70th percentile
    realized_vol = ret.rolling(vol_lookback, min_periods=vol_lookback).std(
        ddof=0
    ) * np.sqrt(252)
    vol_rank = realized_vol.rolling(
        vol_percentile_window, min_periods=vol_percentile_window
    ).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False)
    is_medium_vol = (vol_rank >= medium_vol_low) & (vol_rank <= medium_vol_high)

    # Trade when: uptrend OR medium vol
    good_regime = is_uptrend | is_medium_vol

    # ========== BOLLINGER BANDS ==========
    mu = price.rolling(bb_lookback, min_periods=bb_lookback).mean()
    sd = price.rolling(bb_lookback, min_periods=bb_lookback).std(ddof=0)

    if bb_shift > 0:
        mu = mu.shift(bb_shift)
        sd = sd.shift(bb_shift)

    upper_band = mu + bb_sigma * sd
    lower_band = mu - bb_sigma * sd

    # ========== VOLUME CONFIRMATION ==========
    has_volume = "volume" in df.columns
    if has_volume:
        volume = df["volume"]
        avg_volume = volume.rolling(volume_lookback, min_periods=volume_lookback).mean()
        volume_spike = (volume / avg_volume) > volume_spike_threshold
    else:
        volume_spike = pd.Series(True, index=df.index)

    # ========== ENTRY SIGNALS ==========
    # Long: oversold + volume + good regime
    long_entry = (price < lower_band) & volume_spike & good_regime

    # SHORTS REMOVED: Testing showed Sharpe -0.79 vs Longs +1.00
    # Copper mean reversion shorts don't work (supply constraints → rallies persist)

    # Entry signal (longs only)
    entry_signal = pd.Series(0.0, index=df.index)
    entry_signal[long_entry] = +1.0

    # ========== NON-OVERLAPPING HOLDS ==========
    hold_remaining = 0
    current_pos = 0.0

    for i in range(len(df)):
        if hold_remaining > 0:
            pos_raw.iloc[i] = current_pos
            hold_remaining -= 1
        elif entry_signal.iloc[i] != 0:
            current_pos = entry_signal.iloc[i]
            pos_raw.iloc[i] = current_pos
            hold_remaining = hold_days - 1
        else:
            pos_raw.iloc[i] = 0.0
            current_pos = 0.0

    return pos_raw
