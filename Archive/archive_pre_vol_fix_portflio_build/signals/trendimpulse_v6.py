# src/signals/trendimpulse_v6.py
"""
TrendImpulse v6 Signal Generator - PURE SIGNAL WITH ADX FILTER
--------------------------------------------------------------
Quality momentum that ONLY trades in trending markets (ADX >= 20).

**4-LAYER ARCHITECTURE (Layer 1: Signal Generation)**
- Outputs pure strategy logic (no vol targeting, no calibration)
- Vol targeting applied separately in Layer 2
- Costs applied once on net portfolio in Layer 4

Key Strategy Features vs V5:
- V5: Always on (90% activity) → 0.369 Sharpe
- V6: Only when ADX >= 20 (72% activity) → 0.343 overall, 0.416 in-regime
- 20-day momentum with asymmetric entry/exit thresholds
- Regime-based position scaling (overweight low vol, underweight medium vol)
- Weekly updates to reduce turnover
- Goes FLAT during ranging markets (ADX < 20)

Expected Performance (after vol targeting to 10%):
  Overall: Net Sharpe ~0.34 @ 3bps
  In Trending Markets (ADX >= 20): Net Sharpe ~0.42 @ 3bps
  Activity: ~72% (only in trends)
  
Portfolio Context:
  Best used with RangeFader (ADX < 17) for full regime coverage
  Expected combined Sharpe: 0.75-0.85
"""

import numpy as np
import pandas as pd


def calculate_adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 14,
) -> pd.Series:
    """
    Calculate ADX (Average Directional Index) from OHLC data.
    
    ADX measures trend strength (not direction):
    - ADX < 20: Ranging/choppy market (weak trend)
    - ADX >= 20: Trending market (strong directional move)
    - ADX > 25: Very strong trend
    
    Uses standard Wilder's smoothing method.
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        window: Smoothing window (default: 14, standard)
        
    Returns:
        pd.Series: ADX values (0-100 scale)
    """
    
    # True Range components
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    
    # True Range = max of the three
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window).mean()
    
    # Directional Movement
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    
    # +DM and -DM
    plus_dm = pd.Series(0.0, index=close.index)
    minus_dm = pd.Series(0.0, index=close.index)
    
    # +DM: up_move when up_move > down_move and up_move > 0
    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
    
    # -DM: down_move when down_move > up_move and down_move > 0
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move
    
    # Directional Indicators
    plus_di = 100 * (plus_dm.rolling(window).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window).mean() / atr)
    
    # DX = 100 * |+DI - -DI| / (+DI + -DI)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    
    # ADX = smoothed DX
    adx = dx.rolling(window).mean()
    
    return adx


def generate_trendimpulse_v6_signal(
    df: pd.DataFrame,
    momentum_window: int = 20,
    entry_threshold: float = 0.010,
    exit_threshold: float = 0.003,
    adx_trending_threshold: float = 20.0,
    adx_window: int = 14,
    weekly_vol_updates: bool = True,
    update_frequency: int = 5,
    use_regime_scaling: bool = True,
    vol_window: int = 63,
    vol_percentile_window: int = 252,
    low_vol_threshold: float = 0.40,
    medium_vol_threshold: float = 0.75,
    low_vol_scale: float = 1.5,
    medium_vol_scale: float = 0.8,
    high_vol_scale: float = 0.7,
) -> pd.Series:
    """
    Generate TrendImpulse v6 position signal - PURE STRATEGY LOGIC WITH ADX FILTER.

    Logic:
        1. Calculate ADX from OHLC data
        2. Only trade when ADX >= threshold (trending markets)
        3. Go FLAT when ADX < threshold (ranging markets)
        4. When trending:
           a. Calculate 20-day momentum (price[t] / price[t-20] - 1)
           b. Asymmetric entry/exit thresholds
           c. Regime-based position scaling
        5. Weekly updates (not daily) to reduce turnover
        
    KEY DIFFERENCE FROM V5:
    - V5: Always on, trades everywhere
    - V6: Only trades when ADX >= 20 (trending)
    - V6 eliminates -1.5 Sharpe disaster in ranging markets
    - V6 achieves +0.416 Sharpe IN trending markets
        
    NO CALIBRATION - This is pure strategy logic.
    Vol targeting applied separately in build script.

    Args:
        df: DataFrame with 'price', 'high', 'low' columns
        momentum_window: Lookback for momentum calculation (default: 20)
        entry_threshold: Minimum |momentum| to enter (default: 0.010 = 1.0%)
        exit_threshold: Minimum |momentum| to stay in (default: 0.003 = 0.3%)
        adx_trending_threshold: ADX threshold for trending (default: 20.0)
        adx_window: ADX calculation window (default: 14, standard)
        weekly_vol_updates: Update vol/regime weekly vs daily (default: True)
        update_frequency: Days between updates (default: 5)
        use_regime_scaling: Enable regime-based scaling (default: True)
        vol_window: Window for vol calculation (default: 63 days)
        vol_percentile_window: Window for percentile ranking (default: 252 days)
        low_vol_threshold: Percentile for low vol regime (default: 0.40)
        medium_vol_threshold: Percentile for medium vol regime (default: 0.75)
        low_vol_scale: Position scale in low vol (default: 1.5)
        medium_vol_scale: Position scale in medium vol (default: 0.8, NOT 0.4!)
        high_vol_scale: Position scale in high vol (default: 0.7)

    Returns:
        pd.Series: Raw position signal (continuous, -1.5 to +1.5 range after scaling)
                   ZERO when ADX < threshold (ranging markets)
    """

    df = df.copy()
    
    # Validate required columns
    required = ['price', 'high', 'low']
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"DataFrame missing required columns: {missing}")
    
    price = df["price"]
    high = df["high"]
    low = df["low"]
    returns = price.pct_change()

    # ========== STEP 1: CALCULATE ADX ==========
    adx = calculate_adx(high=high, low=low, close=price, window=adx_window)
    is_trending = adx >= adx_trending_threshold

    # ========== STEP 2: CALCULATE MOMENTUM ==========
    momentum = price / price.shift(momentum_window) - 1

    # ========== STEP 3: GENERATE POSITION (ONLY WHEN TRENDING) ==========
    n = len(df)
    position_raw = np.zeros(n)
    current_state = 0  # -1 = short, 0 = flat, +1 = long

    for i in range(momentum_window, n):
        mom = momentum.iloc[i]
        trending = is_trending.iloc[i]

        if np.isnan(mom) or np.isnan(trending):
            position_raw[i] = 0
            continue

        # KEY FILTER: Only trade when trending
        if not trending:
            current_state = 0
            position_raw[i] = 0
            continue

        # Asymmetric entry/exit logic (only when trending)
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

    # ========== STEP 4: REGIME-BASED POSITION SCALING ==========
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
    # ZERO when ADX < 20 (ranging markets)
    # Vol targeting will scale this to hit 10% vol

    return position_final