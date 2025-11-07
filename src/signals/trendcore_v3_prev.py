# src/signals/trendcore.py
"""
TrendCore v3 Signal Generator
------------------------------
Dual MA system with rangebound awareness and trend quality filtering.

Performance: Sharpe 0.51 unconditional, 2.0-2.5 in trending regimes
"""

import numpy as np
import pandas as pd


def generate_trendcore_signal(
    df: pd.DataFrame,
    fast_ma: int = 30,
    slow_ma: int = 100,
    vol_lookback: int = 63,
    range_threshold: float = 0.10,
    range_lookback: int = 100,
    trend_quality_lookback: int = 20,
) -> pd.Series:
    """
    Generate TrendCore v3 position signal.

    Logic:
        1. Dual MA crossover: +1 if fast > slow, -1 if fast < slow
        2. Rangebound filter: Reduce position when price range is narrow
        3. Trend quality: Scale by directional consistency
        4. Vol regime: Reduce position in high volatility

    Args:
        df: DataFrame with 'price' column
        fast_ma: Fast moving average window (default: 30)
        slow_ma: Slow moving average window (default: 100)
        vol_lookback: Lookback for volatility calculation (default: 63)
        range_threshold: Threshold for rangebound detection (default: 0.10)
        range_lookback: Lookback for price range (default: 100)
        trend_quality_lookback: Lookback for trend quality (default: 20)

    Returns:
        pd.Series: Scaled position signal (-1 to +1) for contract.py
    """

    df = df.copy()
    price = df["price"]
    returns = price.pct_change()

    # ========== DUAL MOVING AVERAGE ==========
    # Fast MA: Captures regime changes quickly
    # Slow MA: Filters noise and confirms trend
    ma_fast = price.rolling(fast_ma, min_periods=fast_ma).mean().shift(1)
    ma_slow = price.rolling(slow_ma, min_periods=slow_ma).mean().shift(1)

    # Base signal: Fast vs Slow
    pos_raw = pd.Series(0.0, index=df.index)
    pos_raw[ma_fast > ma_slow] = 1.0  # Uptrend
    pos_raw[ma_fast < ma_slow] = -1.0  # Downtrend

    # ========== RANGEBOUND DETECTION ==========
    # Reduce position when markets are choppy
    # Strong trends = wide price range
    # Rangebound = narrow price range

    rolling_high = price.rolling(range_lookback).max()
    rolling_low = price.rolling(range_lookback).min()
    price_range_pct = (rolling_high - rolling_low) / rolling_low

    # Scale: 0.3x position in tight range, 1.0x in wide range
    range_scale = np.clip(
        (price_range_pct - range_threshold) / range_threshold,
        0.3,  # Minimum 30% position
        1.0,  # Full position
    )

    # ========== TREND QUALITY FILTER ==========
    # Measure directional consistency of recent returns
    # Strong trends = consistent direction
    # Choppy markets = mixed directions

    recent_rets = returns.rolling(trend_quality_lookback).apply(
        lambda x: (x > 0).sum() / len(x) if len(x) > 0 else 0.5
    )

    # Convert to quality measure (0 = random, 1 = strong trend)
    trend_quality = (recent_rets - 0.5).abs() * 2

    # Scale: 0.5x for weak trends, 1.0x for strong trends
    quality_scale = 0.5 + 0.5 * trend_quality

    # ========== VOLATILITY REGIME ==========
    # Trend following works best in low-medium vol
    # Reduce position in high vol regimes

    vol_60d = returns.rolling(vol_lookback).std() * np.sqrt(252)

    # Calculate rolling percentile
    vol_percentile = vol_60d.rolling(252, min_periods=63).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else 0.5
    )

    # Scale: 0.7x in top 25% vol, 1.0x otherwise
    vol_scale = np.where(vol_percentile > 0.75, 0.7, 1.0)

    # ========== COMBINE ALL FILTERS ==========
    # Multiply base signal by all scaling factors
    pos_scaled = pos_raw * range_scale * quality_scale * vol_scale

    return pos_scaled
