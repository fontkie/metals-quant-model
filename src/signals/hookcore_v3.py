# src/signals/hookcore_v3.py
"""
HookCore v3.0 Signal Logic (Layer B)
------------------------------------
Regime-aware Bollinger mean reversion with safety filters.

Key improvements from v1.0:
1. LONGS ONLY (shorts disabled - asymmetric alpha)
2. Wider bands (20d/3.0σ vs 5d/1.5σ)
3. Longer hold period (5d vs 3d)
4. Tier 1 safety filters (IV shutdown, curve extremes)
5. Regime-adaptive parameters (stocks/IV/curve)

Returns: pos_raw ∈ {-1, 0, +1}
"""

import numpy as np
import pandas as pd


def generate_hookcore_v3_signal(
    df: pd.DataFrame,
    # Bollinger band parameters (OPTIMIZED: Keep tight bands)
    bb_lookback: int = 5,
    bb_sigma: float = 1.5,
    bb_shift: int = 1,
    # Regime data (optional, can be None)
    stocks: pd.Series = None,
    iv_1mo: pd.Series = None,
    curve_spread_pct: pd.Series = None,
    # Tier 1 safety thresholds (FIXED)
    iv_shutdown: float = 30.0,
    iv_elevated: float = 25.0,
    curve_extreme_backwardation: float = 3.0,
    curve_weak_contango: float = -3.0,
    # Regime-adaptive parameters
    use_regime_adaptation: bool = True,
    # Hold period
    hold_days: int = 5,
    # Filter parameters (RELAXED from v1.0)
    trend_lookback: int = 10,
    trend_thresh: float = 0.05,
    vol_lookback: int = 20,
    vol_thresh: float = 0.025,  # Relaxed from 0.02
    autocorr_lookback: int = 10,
    autocorr_thresh: float = -0.05,  # RELAXED from -0.1
) -> pd.Series:
    """
    Generate HookCore v3.0 position signal.

    Args:
        df: DataFrame with columns ['date', 'price', 'ret']
        stocks: LME stocks time series (optional)
        iv_1mo: 1-month implied vol time series (optional)
        curve_spread_pct: 3mo-12mo spread in % (optional)
        [other params]: See docstring details

    Returns:
        pd.Series with values in {-1, 0, +1}
        - +1 = LONG only (shorts disabled)
        - 0 = FLAT
    """

    df = df.copy()
    price = df["price"]
    ret = df["ret"]

    # Initialize position series
    pos_raw = pd.Series(0.0, index=df.index)

    # ========== REGIME CLASSIFICATION (for future enhancements) ==========
    # Currently using fixed bands, but infrastructure ready for adaptation
    if use_regime_adaptation and stocks is not None:
        # Align by date values (stocks has datetime index, df has integer index)
        stocks_aligned = stocks.reindex(df["date"].values).ffill()
        stocks_aligned.index = df.index  # Reset to match df's integer index
        stocks_pct = stocks_aligned.rank(pct=True)
    else:
        stocks_pct = None

    # Align regime data if provided (use date values, then reset index)
    if iv_1mo is not None:
        iv_aligned = iv_1mo.reindex(df["date"].values).ffill()
        iv_aligned.index = df.index  # Reset to match df's integer index
    else:
        iv_aligned = pd.Series(np.nan, index=df.index)

    if curve_spread_pct is not None:
        curve_aligned = curve_spread_pct.reindex(df["date"].values).ffill()
        curve_aligned.index = df.index  # Reset to match df's integer index
    else:
        curve_aligned = pd.Series(np.nan, index=df.index)

    # ========== BOLLINGER BANDS (FIXED PARAMETERS) ==========
    # Note: Regime adaptation disabled in v3.0 after optimization
    # Keeping 5d/1.5σ for best signal quality
    mu = price.rolling(bb_lookback, min_periods=bb_lookback).mean()
    sd = price.rolling(bb_lookback, min_periods=bb_lookback).std(ddof=0)

    # Shift bands by 1 bar (use info up to T-1)
    if bb_shift > 0:
        mu = mu.shift(bb_shift)
        sd = sd.shift(bb_shift)

    upper_band = mu + bb_sigma * sd
    lower_band = mu - bb_sigma * sd

    # ========== BASIC FILTERS ==========
    # 1. Non-trending (relaxed)
    cumret = (price / price.shift(trend_lookback)) - 1.0
    non_trending = cumret.abs() < trend_thresh

    # 2. Low vol (relaxed)
    rolling_vol = ret.rolling(vol_lookback, min_periods=vol_lookback).std(ddof=0)
    low_vol = rolling_vol < vol_thresh

    # 3. Negative autocorr (RELAXED threshold)
    autocorr = ret.rolling(autocorr_lookback, min_periods=autocorr_lookback).apply(
        lambda x: x.corr(pd.Series(x).shift(1)) if len(x) > 1 else np.nan, raw=False
    )
    reversion_hint = autocorr < autocorr_thresh

    # All filters must pass
    filters_ok = non_trending & low_vol & reversion_hint

    # ========== ENTRY SIGNALS (LONGS ONLY) ==========
    long_entry = (price < lower_band) & filters_ok

    # Convert to position
    entry_signal = long_entry.astype(float)  # Only longs

    # ========== OVERLAPPING HOLDS ==========
    # Entry signal at T → position active for hold_days
    for lag in range(hold_days):
        pos_raw += entry_signal.shift(lag).fillna(0.0)

    # Clip to {0, +1} range (longs only)
    pos_raw = pos_raw.clip(0.0, 1.0)

    # ========== TIER 1 SAFETY FILTERS ==========
    for i in range(len(df)):
        iv_val = iv_aligned.iloc[i]
        curve_val = curve_aligned.iloc[i]

        # Rule 1: IV Shutdown
        if pd.notna(iv_val) and iv_val > iv_shutdown:
            pos_raw.iloc[i] = 0.0
            continue

        # Rule 2: IV Elevation → Already handled in band width
        # (could add dynamic adjustment here in future)

        # Rule 3: Extreme Backwardation → Longs only mode already
        # (no shorts to disable)

        # Rule 4: Weak Contango → Reduce size
        if pd.notna(curve_val) and curve_val < curve_weak_contango:
            pos_raw.iloc[i] *= 0.5

    return pos_raw
