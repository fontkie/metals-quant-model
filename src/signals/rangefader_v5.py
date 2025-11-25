# src/signals/rangefader_v5.py
"""
RangeFader v5 Signal Generator - OHLC ADX FIX
----------------------------------------------
Mean reversion strategy for choppy copper markets.

**CRITICAL FIX FROM V4:**
- V4 used close-only ADX approximation (underestimated by ~6 points)
- V5 uses proper OHLC ADX calculation (requires high, low, close)
- This changes regime classification significantly (26% → 13% choppy)

**4-LAYER ARCHITECTURE (Layer 1: Signal Generation)**
- Outputs pure strategy logic (no vol targeting, no calibration)
- Vol targeting applied separately in Layer 2
- Costs applied once on net portfolio in Layer 4

Key Strategy Features:
- Configurable lookback window (default: 70 days, per optimization)
- Configurable entry/exit thresholds (default: 0.6/0.2 std)
- ADX < threshold regime filter (default: 17, only truly choppy)
- Daily position updates for fast mean reversion capture
- Binary positions (-1/0/+1, no regime scaling)

Expected Performance (after optimization & vol targeting to 10%):
  Net Sharpe ~0.30 overall
  In choppy markets (ADX < 17): Sharpe ~0.60-0.80 (target)
"""

import numpy as np
import pandas as pd


def calculate_adx_ohlc(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 14
) -> pd.Series:
    """
    Calculate ADX properly from OHLC data.
    
    CRITICAL: This is the CORRECT way to calculate ADX.
    Using close-only (like V4) underestimates ADX by ~6 points.
    
    ADX measures trend strength (not direction):
        0-15:  Very weak trend / choppy
        15-20: Weak trend / ranging  
        20-25: Emerging trend
        25-40: Strong trend
        40+:   Very strong trend
        
    Args:
        high: High prices
        low: Low prices  
        close: Close prices
        window: ADX calculation window (standard: 14)
        
    Returns:
        pd.Series: ADX values (higher = stronger trend)
    """
    # True Range (uses actual high-low spread)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window).mean()
    
    # Directional Movement (uses actual high-low directional changes)
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    
    plus_dm = pd.Series(0.0, index=high.index)
    minus_dm = pd.Series(0.0, index=high.index)
    
    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move
    
    # Directional Indicators
    plus_di = 100 * (plus_dm.rolling(window).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window).mean() / atr)
    
    # ADX (average directional index)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    adx = dx.rolling(window).mean()
    
    return adx


def generate_rangefader_signal(
    df: pd.DataFrame,
    lookback_window: int = 70,
    zscore_entry: float = 0.6,
    zscore_exit: float = 0.2,
    adx_threshold: float = 17.0,
    adx_window: int = 14,
    update_frequency: int = 1,
) -> pd.Series:
    """
    Generate RangeFader v5 position signal - PURE STRATEGY LOGIC.
    
    CRITICAL CHANGE FROM V4: Uses proper OHLC ADX calculation.
    Requires df to have 'price', 'high', 'low' columns.
    
    Mean Reversion Logic:
        1. Calculate Z-score from N-day MA and std
        2. Enter when |Z| > entry_threshold (price extended)
        3. Exit when |Z| < exit_threshold (back near fair value)
        4. Only trade when ADX < threshold (truly choppy)
        5. Daily position updates (default)
        
    Position States:
        - If ADX >= threshold: FLAT (trending, let trend strategies work)
        - If ADX < threshold and price > +entry: SHORT (overextended up)
        - If ADX < threshold and price < -entry: LONG (overextended down)
        - If |Z| < exit: FLAT (back to fair value)
        
    State Machine:
        FLAT → LONG/SHORT (when |Z| > entry and ADX < threshold)
        LONG → FLAT (when Z > -exit)
        LONG → SHORT (when Z > +entry, flip)
        SHORT → FLAT (when Z < +exit)
        SHORT → LONG (when Z < -entry, flip)
        ANY → FLAT (when ADX >= threshold)
        
    NO CALIBRATION - This is pure strategy logic.
    Vol targeting applied separately in build script.

    Args:
        df: DataFrame with 'price', 'high', 'low' columns
        lookback_window: Window for MA and std (default: 70, optimizable)
        zscore_entry: Z-score to enter position (default: 0.6, optimizable)
        zscore_exit: Z-score to exit position (default: 0.2, optimizable)
        adx_threshold: ADX below this = choppy (default: 17, optimizable)
        adx_window: ADX calculation window (default: 14, standard)
        update_frequency: Days between updates (default: 1, daily)

    Returns:
        pd.Series: Raw position signal (-1 to +1, binary, active only in choppy)
        
    Expected Performance (after vol targeting, requires optimization):
        Overall: +0.25-0.35 Sharpe
        Choppy markets: +0.60-0.80 Sharpe (target)
        Activity: ~10-15% of time
        
    Raises:
        ValueError: If df missing required OHLC columns
    """
    
    # Validate OHLC data
    if 'high' not in df.columns or 'low' not in df.columns:
        raise ValueError(
            "DataFrame must have 'high' and 'low' columns for OHLC ADX. "
            "V5 requires proper OHLC data (not close-only like V4)."
        )
    
    df = df.copy()
    price = df["price"]
    high = df["high"]
    low = df["low"]
    n = len(df)
    
    # ========== STEP 1: CALCULATE ADX (REGIME DETECTOR) - OHLC ==========
    # CRITICAL: This is the fix from V4
    # V4 used calculate_adx(price) which used close as proxy for high/low
    # V5 uses proper OHLC data for accurate ADX
    adx = calculate_adx_ohlc(high, low, price, window=adx_window)
    is_choppy = adx < adx_threshold
    
    # ========== STEP 2: CALCULATE Z-SCORE ==========
    sma = price.rolling(lookback_window, min_periods=lookback_window).mean()
    rolling_std = price.rolling(lookback_window, min_periods=lookback_window).std()
    zscore = (price - sma) / rolling_std
    
    # ========== STEP 3: GENERATE MEAN REVERSION POSITIONS ==========
    position_raw = np.zeros(n)
    current_state = 0  # -1 = short, 0 = flat, +1 = long
    
    for i in range(max(lookback_window, adx_window * 2), n):
        z = zscore.iloc[i]
        choppy = is_choppy.iloc[i]
        
        if np.isnan(z) or np.isnan(choppy):
            position_raw[i] = 0
            continue
        
        # CRITICAL: Only trade in choppy markets
        # This logic is CORRECT - trades when choppy = True (ADX < threshold)
        if not choppy:
            current_state = 0
            position_raw[i] = 0
            continue
        
        # Mean reversion state machine (only when choppy)
        if current_state == 0:  # FLAT - need signal to enter
            if z > zscore_entry:
                current_state = -1  # SHORT (price too high)
            elif z < -zscore_entry:
                current_state = 1  # LONG (price too low)
        
        elif current_state == 1:  # LONG - check for exit or flip
            if z > zscore_entry:  # Price flipped to overextended up
                current_state = -1  # FLIP TO SHORT
            elif z > -zscore_exit:  # Back to fair value
                current_state = 0  # EXIT TO FLAT
        
        elif current_state == -1:  # SHORT - check for exit or flip
            if z < -zscore_entry:  # Price flipped to overextended down
                current_state = 1  # FLIP TO LONG
            elif z < zscore_exit:  # Back to fair value
                current_state = 0  # EXIT TO FLAT
        
        position_raw[i] = current_state
    
    # ========== STEP 4: UPDATE FREQUENCY ==========
    if update_frequency > 1:
        position_final = np.zeros(n)
        last_position = 0
        
        for i in range(n):
            if i % update_frequency == 0 or i < max(lookback_window, adx_window * 2):
                last_position = position_raw[i]
            position_final[i] = last_position
    else:
        position_final = position_raw
    
    # Convert to series
    position_final = pd.Series(position_final, index=df.index)
    
    return position_final


# ========================================================================
# DIAGNOSTIC FUNCTIONS
# ========================================================================

def get_regime_statistics(
    df: pd.DataFrame, 
    adx_threshold: float = 17.0,
    adx_window: int = 14
) -> dict:
    """
    Calculate regime distribution statistics using OHLC ADX.
    
    Args:
        df: DataFrame with 'price', 'high', 'low' columns
        adx_threshold: ADX threshold for choppy regime
        adx_window: ADX calculation window
        
    Returns:
        dict: Regime statistics
    """
    if 'high' not in df.columns or 'low' not in df.columns:
        raise ValueError("DataFrame must have 'high' and 'low' columns")
    
    adx = calculate_adx_ohlc(df["high"], df["low"], df["price"], window=adx_window)
    
    choppy = adx < adx_threshold
    weak_trend = (adx >= adx_threshold) & (adx < 25)
    strong_trend = adx >= 25
    
    return {
        "choppy_pct": float(choppy.mean() * 100),
        "weak_trend_pct": float(weak_trend.mean() * 100),
        "strong_trend_pct": float(strong_trend.mean() * 100),
        "choppy_days": int(choppy.sum()),
        "total_days": int(len(df)),
        "mean_adx": float(adx.mean()),
        "median_adx": float(adx.median()),
    }


def get_signal_statistics(positions: pd.Series) -> dict:
    """
    Calculate signal statistics.
    
    Args:
        positions: Position series
        
    Returns:
        dict: Signal statistics
    """
    return {
        "mean": float(positions.mean()),
        "mean_abs": float(positions.abs().mean()),
        "std": float(positions.std()),
        "min": float(positions.min()),
        "max": float(positions.max()),
        "pct_active": float((positions.abs() > 0.01).mean() * 100),
        "pct_long": float((positions > 0.01).mean() * 100),
        "pct_short": float((positions < -0.01).mean() * 100),
        "pct_flat": float((positions.abs() <= 0.01).mean() * 100),
    }


def validate_regime_behavior(
    df: pd.DataFrame,
    positions: pd.Series,
    adx_threshold: float = 17.0,
    adx_window: int = 14,
    verbose: bool = True
) -> dict:
    """
    Validate that RangeFader is behaving correctly in regimes.
    
    Checks:
    1. Mostly active in choppy markets (ADX < threshold)
    2. Mostly inactive in trending markets (ADX >= 25)
    3. Negative correlation between |position| and ADX
    
    Args:
        df: DataFrame with 'price', 'high', 'low' columns
        positions: Position series
        adx_threshold: Choppy threshold
        adx_window: ADX window
        verbose: Print validation results
        
    Returns:
        dict: Validation results with pass/fail flags
    """
    adx = calculate_adx_ohlc(df["high"], df["low"], df["price"], window=adx_window)
    
    # Calculate metrics
    choppy_mask = adx < adx_threshold
    trending_mask = adx >= 25
    
    activity_in_choppy = (positions[choppy_mask].abs() > 0.01).mean()
    activity_in_trending = (positions[trending_mask].abs() > 0.01).mean()
    
    mean_adx_active = adx[positions.abs() > 0.01].mean()
    mean_adx_inactive = adx[positions.abs() <= 0.01].mean()
    
    correlation = positions.abs().corr(adx)
    
    # Pass/fail criteria
    results = {
        "activity_in_choppy": float(activity_in_choppy),
        "activity_in_trending": float(activity_in_trending),
        "mean_adx_active": float(mean_adx_active),
        "mean_adx_inactive": float(mean_adx_inactive),
        "correlation_pos_adx": float(correlation),
        "pass_choppy_activity": bool(activity_in_choppy > 0.60),  # >60% active in choppy
        "pass_trending_activity": bool(activity_in_trending < 0.15),  # <15% active in trending
        "pass_adx_means": bool(mean_adx_active < mean_adx_inactive),
        "pass_correlation": bool(correlation < -0.15),  # Negative correlation
        "all_passed": False,
    }
    
    results["all_passed"] = bool(all([
        results["pass_choppy_activity"],
        results["pass_trending_activity"],
        results["pass_adx_means"],
        results["pass_correlation"],
    ]))
    
    if verbose:
        print("\n" + "=" * 60)
        print("RANGEFADER V5 REGIME VALIDATION")
        print("=" * 60)
        print(f"\nActivity in Choppy (ADX < {adx_threshold}): {activity_in_choppy*100:.1f}%")
        print(f"  {'✓ PASS' if results['pass_choppy_activity'] else '✗ FAIL'} (target: >60%)")
        
        print(f"\nActivity in Trending (ADX >= 25): {activity_in_trending*100:.1f}%")
        print(f"  {'✓ PASS' if results['pass_trending_activity'] else '✗ FAIL'} (target: <15%)")
        
        print(f"\nMean ADX when active: {mean_adx_active:.1f}")
        print(f"Mean ADX when inactive: {mean_adx_inactive:.1f}")
        print(f"  {'✓ PASS' if results['pass_adx_means'] else '✗ FAIL'} (active should be lower)")
        
        print(f"\nCorrelation(|pos|, ADX): {correlation:+.3f}")
        print(f"  {'✓ PASS' if results['pass_correlation'] else '✗ FAIL'} (target: < -0.15)")
        
        print(f"\n{'✓✓ ALL TESTS PASSED' if results['all_passed'] else '✗✗ SOME TESTS FAILED'}")
        print("=" * 60)
    
    return results
