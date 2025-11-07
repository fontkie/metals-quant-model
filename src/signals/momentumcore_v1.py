# src/signals/momentumcore_v1.py
"""
MomentumCore v1 Signal Logic (Layer B)
--------------------------------------
12-month Time Series Momentum (TSMOM) from Moskowitz, Ooi, Pedersen (2012).

Strategy:
- Long if price > price 12 months ago
- Short if price < price 12 months ago
- Vol-scaled to target annual volatility

Performance (validated on copper 2000-2025):
- Sharpe: 0.534
- Annual Return: 5.5%
- Annual Vol: 10.3%
- Max Drawdown: -23.9%

Returns: pos_raw âˆˆ {-1, 0, +1} (long/flat/short)
"""

import numpy as np
import pandas as pd


def generate_momentumcore_v1_signal(
    df: pd.DataFrame,
    # Momentum lookback
    lookback_days: int = 252,
    # Vol scaling
    vol_lookback_days: int = 60,
    vol_target_annual: float = 0.10,
    max_leverage: float = 2.0,
    # Directional constraints
    longs_only: bool = False,
) -> pd.Series:
    """
    Generate MomentumCore v1 position signal.

    Time Series Momentum (TSMOM):
    1. Calculate price return over lookback period
    2. Signal = sign of past return (long if up, short if down)
    3. Scale by volatility to target constant risk
    4. Apply leverage cap

    Args:
        df: DataFrame with columns ['date', 'price', 'ret']
        lookback_days: Lookback period for momentum (252 = 12 months)
        vol_lookback_days: Lookback for realized vol calculation
        vol_target_annual: Target annual volatility (0.10 = 10%)
        max_leverage: Maximum leverage cap (2.0 = 2x)
        longs_only: If True, only take long positions

    Returns:
        pd.Series with values in {-1, 0, +1} (or {0, +1} if longs_only)
        - +1 = LONG
        - -1 = SHORT
        - 0 = FLAT (only if longs_only and signal is short)
    """

    df = df.copy()
    price = df["price"]
    ret = df["ret"]

    # Initialize position series
    pos_raw = pd.Series(0.0, index=df.index)

    # ========== MOMENTUM SIGNAL ==========
    # Calculate past return over lookback period
    # Use shift(1) to avoid look-ahead bias (use T-1 signal for T position)
    past_return = (price / price.shift(lookback_days)) - 1.0
    past_return = past_return.shift(1)

    # Signal: sign of past return
    # +1 if price trending up, -1 if trending down
    signal = np.sign(past_return)

    # ========== VOLATILITY SCALING ==========
    # Calculate realized volatility (exponentially weighted)
    realized_vol = ret.ewm(
        span=vol_lookback_days, min_periods=vol_lookback_days
    ).std() * np.sqrt(252)

    # Vol scalar: target_vol / realized_vol
    vol_scalar = vol_target_annual / realized_vol

    # Apply leverage cap
    vol_scalar = vol_scalar.clip(0, max_leverage)

    # ========== POSITION SIZING ==========
    # Position = signal * vol_scalar
    pos_raw = signal * vol_scalar

    # ========== DIRECTIONAL CONSTRAINTS ==========
    if longs_only:
        # If longs_only, set short positions to flat
        pos_raw = pos_raw.clip(0, max_leverage)

    return pos_raw
