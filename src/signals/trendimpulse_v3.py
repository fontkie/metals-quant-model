# src/signals/trendimpulse_v3.py
"""
TrendImpulse v3 Signal Generator - FINAL
-----------------------------------------
20-day momentum with minimal filtering.
Complementary to TrendCore's 30/100d dual MA system.

Philosophy: In copper, short-term momentum works but trying to be
selective destroys the signal. Keep it simple - trade the momentum
with light filters to avoid the worst whipsaws.

Expected: Sharpe 0.4-0.6 unconditional
"""

import numpy as np
import pandas as pd


def generate_trendimpulse_signal(
    df: pd.DataFrame,
    momentum_window: int = 20,
    min_momentum_pct: float = 0.005,  # Only trade if |momentum| > 0.5%
    vol_filter: bool = True,
    vol_window: int = 63,
    vol_percentile_threshold: float = 0.85,  # Reduce size in top 15% vol
) -> pd.Series:
    """
    Generate TrendImpulse v3 position signal.

    Logic:
        1. Calculate 20-day momentum
        2. Go long/short based on momentum direction
        3. Filter out tiny momentum values (noise)
        4. Scale down in extreme volatility regimes
        5. Nearly always-on otherwise

    Args:
        df: DataFrame with 'price' column
        momentum_window: Lookback for momentum (default: 20 days)
        min_momentum_pct: Minimum |momentum| to trade (default: 0.005 = 0.5%)
        vol_filter: Apply volatility regime filter (default: True)
        vol_window: Vol calculation window (default: 63 days)
        vol_percentile_threshold: Scale down above this vol percentile (default: 0.85)

    Returns:
        pd.Series: Position signal (-1 to +1) for contract.py
    """

    df = df.copy()
    price = df["price"]
    returns = price.pct_change()

    # ========== MOMENTUM SIGNAL ==========
    # Simple 20-day rate of change
    momentum = price / price.shift(momentum_window) - 1

    # Base signal: Long if positive momentum, short if negative
    position = np.sign(momentum)

    # ========== FILTER 1: MINIMUM MOMENTUM ==========
    # Don't trade if momentum is too weak (likely noise/chop)
    position = np.where(
        np.abs(momentum) < min_momentum_pct, 0, position  # Flat if momentum too weak
    )

    # ========== FILTER 2: VOLATILITY REGIME ==========
    # Scale down position in extreme vol (top 15%)
    if vol_filter:
        vol_60d = returns.rolling(vol_window, min_periods=vol_window).std() * np.sqrt(
            252
        )

        # Calculate rolling percentile
        vol_percentile = vol_60d.rolling(252, min_periods=vol_window).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else 0.5,
            raw=False,
        )

        # Scale: 0.5x in top 15% vol, 1.0x otherwise
        vol_scale = np.where(vol_percentile > vol_percentile_threshold, 0.5, 1.0)

        position = position * vol_scale

    # Convert to series
    position = pd.Series(position, index=df.index)

    return position
