# src/signals/trendmedium.py
"""
TrendMedium Signal Generator
-----------------------------
Dual MA system optimized for medium-term trends (25/70 MAs).

Faster than TrendCore (30/100), targets trends lasting 2-4 months.
More responsive to regime changes while maintaining trend quality.

Expected Performance: Sharpe ~0.45-0.55 unconditional
"""

import numpy as np
import pandas as pd


def generate_trendmedium_signal(
    df: pd.DataFrame,
    fast_ma: int = 25,
    slow_ma: int = 70,
    vol_lookback: int = 63,
    range_threshold: float = 0.10,
    range_lookback: int = 70,
    trend_quality_lookback: int = 15,
) -> pd.Series:
    """
    Generate TrendMedium position signal.

    Logic:
        1. Dual MA crossover: +1 if fast > slow, -1 if fast < slow
        2. Rangebound filter: Reduce position when price range is narrow
        3. Trend quality: Scale by directional consistency
        4. Vol regime: Reduce position in high volatility

    Args:
        df: DataFrame with 'price' column
        fast_ma: Fast moving average window (default: 25)
        slow_ma: Slow moving average window (default: 70)
        vol_lookback: Lookback for volatility calculation (default: 63)
        range_threshold: Threshold for rangebound detection (default: 0.10)
        range_lookback: Lookback for price range (default: 70)
        trend_quality_lookback: Lookback for trend quality (default: 15)

    Returns:
        pd.Series: Scaled position signal (-1 to +1) for contract.py
    """

    df = df.copy()
    price = df["price"]
    returns = price.pct_change()

    # ========== DUAL MOVING AVERAGE ==========
    # 25/70 vs TrendCore's 30/100
    # Faster response to regime changes
    ma_fast = price.rolling(fast_ma, min_periods=fast_ma).mean().shift(1)
    ma_slow = price.rolling(slow_ma, min_periods=slow_ma).mean().shift(1)

    # Base signal: Fast vs Slow
    pos_raw = pd.Series(0.0, index=df.index)
    pos_raw[ma_fast > ma_slow] = 1.0  # Uptrend
    pos_raw[ma_fast < ma_slow] = -1.0  # Downtrend

    # ========== RANGEBOUND DETECTION ==========
    # Use shorter lookback (70d vs 100d) for medium-term focus
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
    # Shorter lookback (15d vs 20d) for faster adaptation
    recent_rets = returns.rolling(trend_quality_lookback).apply(
        lambda x: (x > 0).sum() / len(x) if len(x) > 0 else 0.5
    )

    # Convert to quality measure (0 = random, 1 = strong trend)
    trend_quality = (recent_rets - 0.5).abs() * 2

    # Scale: 0.5x for weak trends, 1.0x for strong trends
    quality_scale = 0.5 + 0.5 * trend_quality

    # ========== VOLATILITY REGIME ==========
    # Same as TrendCore - reduce in high vol
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