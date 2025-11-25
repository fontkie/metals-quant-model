# src/signals/momentumcore_v2.py
"""
MomentumCore v2 Signal Generator - PURE SIGNAL
-----------------------------------------------
12-month Time Series Momentum (TSMOM) from Moskowitz, Ooi, Pedersen (2012).

**4-LAYER ARCHITECTURE (Layer 1: Signal Generation)**
- Outputs pure strategy logic (no vol targeting, no calibration)
- Vol targeting applied separately in Layer 2
- Costs applied once on net portfolio in Layer 4

Classic long-term momentum (12-month lookback) for copper markets.
Captures persistent directional trends.

Expected Performance (after vol targeting to 10%): 
  Sharpe ~0.50-0.55 unconditional
"""

import numpy as np
import pandas as pd


def generate_momentum_signal(
    df: pd.DataFrame,
    lookback_days: int = 252,
) -> pd.Series:
    """
    Generate MomentumCore v2 position signal - PURE STRATEGY LOGIC.

    Logic:
        1. Calculate 12-month return (252 trading days)
        2. Signal = sign(past_return): +1 if up, -1 if down
        3. NO additional filters (pure momentum)
        
    NO CALIBRATION - This is pure strategy logic.
    Vol targeting applied separately in build script.

    Args:
        df: DataFrame with 'price' column
        lookback_days: Lookback period for momentum (default: 252 = 12 months)

    Returns:
        pd.Series: Raw position signal (+1, 0, or -1)
    """

    df = df.copy()
    price = df["price"]

    # Initialize position series
    pos_raw = pd.Series(0.0, index=df.index)

    # ========== MOMENTUM SIGNAL ==========
    # Calculate past return over lookback period
    # Use shift(1) to avoid look-ahead bias (use T-1 signal for T position)
    past_return = (price / price.shift(lookback_days)) - 1.0
    past_return = past_return.shift(1)

    # Signal: sign of past return
    # +1 if price trending up, -1 if trending down, 0 if no data
    pos_raw = np.sign(past_return)
    
    # Replace NaN with 0 (no position during warmup)
    pos_raw = pos_raw.fillna(0)

    # Expected output: +1, 0, or -1
    # No filters, no scaling - pure momentum
    # Vol targeting will scale this to hit 10% vol

    return pos_raw
