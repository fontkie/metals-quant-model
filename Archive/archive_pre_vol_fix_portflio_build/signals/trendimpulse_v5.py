# src/signals/trendimpulse_v5.py
"""
TrendImpulse v5 Signal Generator - PURE SIGNAL
----------------------------------------------
Quality momentum with regime specialization.

**4-LAYER ARCHITECTURE (Layer 1: Signal Generation)**
- Outputs pure strategy logic (no vol targeting, no calibration)
- Vol targeting applied separately in Layer 2
- Costs applied once on net portfolio in Layer 4

Key Strategy Features:
- 20-day momentum with asymmetric entry/exit thresholds
- Regime-based position scaling (overweight low vol, underweight medium vol)
- Weekly updates to reduce turnover
- Continuous positions (not just -1/0/+1)

Expected Performance (after vol targeting to 10%):
  Gross Sharpe ~0.48, Net Sharpe ~0.42 @ 3bps
"""

import numpy as np
import pandas as pd


def generate_trendimpulse_signal(
    df: pd.DataFrame,
    momentum_window: int = 20,
    entry_threshold: float = 0.010,
    exit_threshold: float = 0.003,
    weekly_vol_updates: bool = True,
    update_frequency: int = 5,
    use_regime_scaling: bool = True,
    vol_window: int = 63,
    vol_percentile_window: int = 252,
    low_vol_threshold: float = 0.40,
    medium_vol_threshold: float = 0.75,
    low_vol_scale: float = 1.5,
    medium_vol_scale: float = 0.4,
    high_vol_scale: float = 0.7,
) -> pd.Series:
    """
    Generate TrendImpulse v5 position signal - PURE STRATEGY LOGIC.

    Logic:
        1. Calculate 20-day momentum (price[t] / price[t-20] - 1)
        2. Asymmetric entry/exit thresholds:
           - Enter: |momentum| > 1.0% (need conviction)
           - Exit: |momentum| < 0.3% (be patient)
        3. Regime-based position scaling:
           - Low vol (best edge): 1.5x
           - Medium vol (weak edge): 0.4x
           - High vol (moderate edge): 0.7x
        4. Weekly updates (not daily) to reduce turnover
        
    NO CALIBRATION - This is pure strategy logic.
    Vol targeting applied separately in build script.

    Args:
        df: DataFrame with 'price' column
        momentum_window: Lookback for momentum calculation (default: 20)
        entry_threshold: Minimum |momentum| to enter (default: 0.010 = 1.0%)
        exit_threshold: Minimum |momentum| to stay in (default: 0.003 = 0.3%)
        weekly_vol_updates: Update vol/regime weekly vs daily (default: True)
        update_frequency: Days between updates (default: 5)
        use_regime_scaling: Enable regime-based scaling (default: True)
        vol_window: Window for vol calculation (default: 63 days)
        vol_percentile_window: Window for percentile ranking (default: 252 days)
        low_vol_threshold: Percentile for low vol regime (default: 0.40)
        medium_vol_threshold: Percentile for medium vol regime (default: 0.75)
        low_vol_scale: Position scale in low vol (default: 1.5)
        medium_vol_scale: Position scale in medium vol (default: 0.4)
        high_vol_scale: Position scale in high vol (default: 0.7)

    Returns:
        pd.Series: Raw position signal (continuous, -1.5 to +1.5 range after scaling)
    """

    df = df.copy()
    price = df["price"]
    returns = price.pct_change()

    # ========== STEP 1: CALCULATE MOMENTUM ==========
    momentum = price / price.shift(momentum_window) - 1

    # ========== STEP 2: GENERATE POSITION WITH ASYMMETRIC THRESHOLDS ==========
    n = len(df)
    position_raw = np.zeros(n)
    current_state = 0  # -1 = short, 0 = flat, +1 = long

    for i in range(momentum_window, n):
        mom = momentum.iloc[i]

        if np.isnan(mom):
            position_raw[i] = 0
            continue

        if current_state == 0:  # FLAT - need strong signal to enter
            if mom > entry_threshold:
                current_state = 1  # Enter LONG
            elif mom < -entry_threshold:
                current_state = -1  # Enter SHORT

        elif current_state == 1:  # LONG - patient exit
            if mom < -entry_threshold:  # Strong reversal
                current_state = -1  # Flip to SHORT
            elif mom < exit_threshold:  # Weak momentum
                current_state = 0  # Exit to FLAT

        elif current_state == -1:  # SHORT - patient exit
            if mom > entry_threshold:  # Strong reversal
                current_state = 1  # Flip to LONG
            elif mom > -exit_threshold:  # Weak momentum
                current_state = 0  # Exit to FLAT

        position_raw[i] = current_state

    # ========== STEP 3: REGIME-BASED POSITION SCALING ==========
    # This is STRATEGIC logic (part of Layer 1), not calibration
    # It's a decision about WHEN to be aggressive, not HOW to scale to vol
    
    if use_regime_scaling:
        # Calculate rolling volatility
        vol = returns.rolling(vol_window, min_periods=vol_window).std() * np.sqrt(252)

        # Calculate percentile rank
        vol_percentile = vol.rolling(
            vol_percentile_window, min_periods=vol_window
        ).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else 0.5,
            raw=False,
        )

        # Apply regime scaling
        regime_scale = np.ones(n)

        if weekly_vol_updates:
            # Update only every N days (reduce turnover)
            last_scale = 1.0
            for i in range(n):
                if i % update_frequency == 0 or i < vol_window:
                    # Recalculate regime
                    if np.isnan(vol_percentile.iloc[i]):
                        last_scale = 1.0
                    elif vol_percentile.iloc[i] < low_vol_threshold:
                        last_scale = low_vol_scale  # Overweight low vol
                    elif vol_percentile.iloc[i] < medium_vol_threshold:
                        last_scale = medium_vol_scale  # Underweight medium vol
                    else:
                        last_scale = high_vol_scale  # Reduce high vol

                regime_scale[i] = last_scale
        else:
            # Daily updates
            for i in range(n):
                if np.isnan(vol_percentile.iloc[i]):
                    regime_scale[i] = 1.0
                elif vol_percentile.iloc[i] < low_vol_threshold:
                    regime_scale[i] = low_vol_scale
                elif vol_percentile.iloc[i] < medium_vol_threshold:
                    regime_scale[i] = medium_vol_scale
                else:
                    regime_scale[i] = high_vol_scale

        position_final = position_raw * regime_scale
    else:
        position_final = position_raw

    # Convert to series
    position_final = pd.Series(position_final, index=df.index)

    # Expected range: -1.5 to +1.5 (due to regime scaling)
    # Vol targeting will scale this to hit 10% vol

    return position_final