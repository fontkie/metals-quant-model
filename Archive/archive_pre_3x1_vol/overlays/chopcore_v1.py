#!/usr/bin/env python3
# src/overlays/chopcore_v1.py
"""
CHOPCORE V1 - Pure Macro Confusion Detector
Detects range-bound, directionless markets where trend strategies underperform

CRITICAL: ChopCore ONLY operates when VIX in [15-25] range
          NO crisis detection (separate CrisisCore system)

Multi-layer detection:
- Layer 1: Opposition (60% weight) - USD vs China forces
- Layer 2: Uncertainty (40% weight) - VIX & CNY spread
- Layer 3: Copper ADX confirmation - Reduces false positives

Three-tier regime classification:
- NORMAL: Full exposure (1.0x)
- MILD_CHOP: Moderate defense (0.75x)
- HIGH_CHOP: Significant defense (0.50x)

Usage: Overlay to reduce exposure during macro confusion periods

Author: Ex-Renaissance + Fundamentals PM
Date: November 10, 2025
Version: 1.0
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple


def calculate_opposition_score(
    dxy: pd.Series,
    csi300: pd.Series,
    china_10y: pd.Series,
    config: Dict
) -> pd.DataFrame:
    """
    Layer 1: Calculate opposition score from USD vs China forces.
    
    Logic: When DXY and China markets move in opposite directions,
    copper faces opposing macro forces (chop). When aligned, trends emerge.
    
    Args:
        dxy: USD index
        csi300: China stock index
        china_10y: China 10Y bond yield
        config: Configuration dict
        
    Returns:
        DataFrame with opposition signals and score
    """
    opposition_config = config['opposition']
    window = opposition_config['correlation_window']
    weights = opposition_config['weights']
    
    df = pd.DataFrame(index=dxy.index)
    
    # Calculate returns for correlation
    dxy_returns = dxy.pct_change()
    csi300_returns = csi300.pct_change()
    china10y_returns = china_10y.pct_change()
    
    # Rolling correlations
    df['dxy_csi300_corr'] = dxy_returns.rolling(window).corr(csi300_returns)
    df['dxy_china10y_corr'] = dxy_returns.rolling(window).corr(china10y_returns)
    
    # Opposition score: negative correlation = opposition (0-1 scale)
    # corr = -1 → opposition = 1.0 (max)
    # corr = 0 → opposition = 0.5 (neutral)
    # corr = +1 → opposition = 0.0 (aligned)
    df['equity_opposition'] = (1 - df['dxy_csi300_corr']) / 2
    df['bond_opposition'] = (1 - df['dxy_china10y_corr']) / 2
    
    # Clip to 0-1 range
    df['equity_opposition'] = df['equity_opposition'].clip(0, 1)
    df['bond_opposition'] = df['bond_opposition'].clip(0, 1)
    
    # Combined opposition score (weighted)
    df['opposition_score'] = (
        df['equity_opposition'] * weights['equity'] +
        df['bond_opposition'] * weights['bond']
    )
    
    return df


def calculate_uncertainty_score(
    vix: pd.Series,
    cny_spread: pd.Series,
    config: Dict
) -> pd.DataFrame:
    """
    Layer 2: Calculate uncertainty score from VIX and CNY spread.
    
    Logic: High VIX + wide CNY spreads = market uncertainty and
    capital flow stress, often creating choppy conditions.
    
    Args:
        vix: VIX index
        cny_spread: CNY onshore-offshore spread (basis points)
        config: Configuration dict
        
    Returns:
        DataFrame with uncertainty signals and score
    """
    uncertainty_config = config['uncertainty']
    weights = uncertainty_config['weights']
    lookback = uncertainty_config['percentile_window']
    
    df = pd.DataFrame(index=vix.index)
    
    # VIX percentile (where are we vs recent history?)
    vix_percentile = vix.rolling(lookback).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
    )
    df['vix_score'] = vix_percentile.fillna(0.5)
    
    # CNY spread percentile (absolute magnitude)
    abs_spread = cny_spread.abs()
    spread_percentile = abs_spread.rolling(lookback).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
    )
    df['cny_score'] = spread_percentile.fillna(0.5)
    
    # Combined uncertainty score (weighted)
    df['uncertainty_score'] = (
        df['vix_score'] * weights['vix'] +
        df['cny_score'] * weights['cny_spread']
    )
    
    return df


def calculate_adx(prices: pd.Series, period: int) -> pd.Series:
    """
    Calculate Average Directional Index (ADX) - measures trend strength.
    
    ADX > 35 = strong trending
    ADX < 25 = range-bound/choppy
    
    Args:
        prices: Price series
        period: Lookback period (default 14)
        
    Returns:
        ADX series (0-100)
    """
    high = prices.rolling(2).max()
    low = prices.rolling(2).min()
    close = prices
    
    # True Range
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Directional Movement
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    
    plus_dm = pd.Series(0.0, index=prices.index)
    minus_dm = pd.Series(0.0, index=prices.index)
    
    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move
    
    # Smooth with Wilder's method
    atr = tr.ewm(span=period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)
    
    # ADX calculation
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.ewm(span=period, adjust=False).mean()
    
    return adx.fillna(25)  # Default to neutral


def calculate_composite_chop_score(
    opposition: pd.DataFrame,
    uncertainty: pd.DataFrame,
    copper_adx: pd.Series,
    config: Dict
) -> pd.DataFrame:
    """
    Integrate Layers 1 & 2 with ADX confirmation.
    
    Logic:
    - Macro score = weighted opposition + uncertainty
    - If copper ADX > threshold, reduce chop signal
    
    Args:
        opposition: Layer 1 results
        uncertainty: Layer 2 results
        copper_adx: Copper ADX indicator
        config: Configuration dict
        
    Returns:
        DataFrame with composite score
    """
    composite_weights = config['composite_weights']
    copper_config = config['copper_confirmation']
    
    df = pd.DataFrame(index=opposition.index)
    
    # Macro score (weighted combination)
    df['opposition_score'] = opposition['opposition_score']
    df['uncertainty_score'] = uncertainty['uncertainty_score']
    
    macro_score = (
        df['opposition_score'] * composite_weights['opposition'] +
        df['uncertainty_score'] * composite_weights['uncertainty']
    )
    
    # ADX adjustment factor
    # If ADX > threshold, reduce chop signal
    adx_threshold = copper_config['adx_trending_threshold']
    adx_end = copper_config['adx_reduction_end']
    max_reduction = copper_config['max_reduction']
    
    adx_adjustment = pd.Series(1.0, index=copper_adx.index)
    trending_mask = copper_adx > adx_threshold
    
    if trending_mask.any():
        # Linear adjustment: ADX [threshold, end] → multiplier [1.0, 1-max_reduction]
        adx_adjustment.loc[trending_mask] = np.maximum(
            1.0 - max_reduction,
            1.0 - ((copper_adx[trending_mask] - adx_threshold) / 
                   (adx_end - adx_threshold)) * max_reduction
        )
    
    # Final composite
    df['composite_chop'] = macro_score * adx_adjustment
    df['composite_chop'] = df['composite_chop'].clip(0, 1)
    
    return df


def classify_chop_regime(
    vix: pd.Series,
    composite_score: pd.Series,
    copper_adx: pd.Series,
    config: Dict
) -> pd.DataFrame:
    """
    Classify market regime based on composite chop score.
    
    CRITICAL VIX FILTER:
    - Only classifies as chop when VIX is in [min, max] range
    - Outside this range, returns NORMAL (1.0x sizing)
    
    Args:
        vix: VIX index values
        composite_score: Composite chop score (0-1)
        copper_adx: Copper ADX indicator
        config: Configuration dict
        
    Returns:
        DataFrame with regime labels and sizing
    """
    vix_config = config['vix_filter']
    thresholds = config['regime_classification']
    sizing = config['sizing']
    smoothing_span = config['smoothing']['span']
    
    df = pd.DataFrame(index=composite_score.index)
    df['composite_score'] = composite_score
    df['copper_adx'] = copper_adx
    df['vix'] = vix
    
    # Initialize as NORMAL
    df['regime'] = 'NORMAL'
    df['sizing'] = sizing['normal']
    
    # CRITICAL: Only detect chop when VIX in range
    vix_in_range = (vix >= vix_config['min']) & (vix <= vix_config['max'])
    
    # High chop classification (when VIX in range)
    high_chop_mask = vix_in_range & (composite_score >= thresholds['high_chop_threshold'])
    df.loc[high_chop_mask, 'regime'] = 'HIGH_CHOP'
    df.loc[high_chop_mask, 'sizing'] = sizing['high_chop']
    
    # Mild chop classification (when VIX in range)
    mild_chop_mask = (
        vix_in_range & 
        (composite_score >= thresholds['mild_chop_threshold']) & 
        (composite_score < thresholds['high_chop_threshold'])
    )
    df.loc[mild_chop_mask, 'regime'] = 'MILD_CHOP'
    df.loc[mild_chop_mask, 'sizing'] = sizing['mild_chop']
    
    # Smooth sizing with exponential moving average
    df['sizing_smooth'] = df['sizing'].ewm(span=smoothing_span, adjust=False).mean()
    
    # Add diagnostic flags
    df['vix_in_range'] = vix_in_range
    df['high_chop_signal'] = (composite_score >= thresholds['high_chop_threshold'])
    df['mild_chop_signal'] = (composite_score >= thresholds['mild_chop_threshold'])
    
    return df


def run_chop_detection(
    data: Dict[str, pd.Series],
    config: Dict
) -> Dict[str, pd.DataFrame]:
    """
    Main entry point: Run complete ChopCore detection.
    
    Args:
        data: Dictionary with required series:
            - dxy: USD index
            - csi300: China stock index
            - china_10y: China 10Y bond yield
            - vix: VIX index
            - cny_spread: CNY onshore-offshore spread (bps)
            - copper_prices: Copper prices (for ADX)
        config: Configuration dictionary
        
    Returns:
        Dictionary with:
            - scores: Component and composite scores
            - regimes: Regime classifications and sizing
            - diagnostics: Full diagnostic data
    """
    # Extract parameters from config
    adx_period = config['parameters']['adx_period']
    
    # Extract data
    dxy = data['dxy']
    csi300 = data['csi300']
    china_10y = data['china_10y']
    vix = data['vix']
    cny_spread = data['cny_spread']
    copper_prices = data['copper_prices']
    
    # Layer 1: Opposition
    opposition = calculate_opposition_score(dxy, csi300, china_10y, config)
    
    # Layer 2: Uncertainty
    uncertainty = calculate_uncertainty_score(vix, cny_spread, config)
    
    # Layer 3: Copper ADX
    copper_adx = calculate_adx(copper_prices, period=adx_period)
    
    # Composite Score
    composite = calculate_composite_chop_score(opposition, uncertainty, copper_adx, config)
    
    # Regime Classification (with VIX filter)
    regimes = classify_chop_regime(vix, composite['composite_chop'], copper_adx, config)
    
    # Compile scores
    scores = pd.DataFrame({
        'opposition_score': opposition['opposition_score'],
        'uncertainty_score': uncertainty['uncertainty_score'],
        'composite_chop': composite['composite_chop']
    })
    
    # Compile diagnostics
    diagnostics = pd.DataFrame({
        'regime': regimes['regime'],
        'sizing': regimes['sizing'],
        'sizing_smooth': regimes['sizing_smooth'],
        'vix': vix,
        'vix_in_range': regimes['vix_in_range'],
        'opposition_score': opposition['opposition_score'],
        'uncertainty_score': uncertainty['uncertainty_score'],
        'composite_chop': composite['composite_chop'],
        'copper_adx': copper_adx,
        'high_chop_signal': regimes['high_chop_signal'],
        'mild_chop_signal': regimes['mild_chop_signal'],
        
        # Detailed components
        'dxy_csi300_corr': opposition['dxy_csi300_corr'],
        'dxy_china10y_corr': opposition['dxy_china10y_corr'],
        'equity_opposition': opposition['equity_opposition'],
        'bond_opposition': opposition['bond_opposition']
    })
    
    return {
        'scores': scores,
        'regimes': regimes[['regime', 'sizing', 'sizing_smooth', 'vix', 'copper_adx']],
        'diagnostics': diagnostics
    }


if __name__ == "__main__":
    print("ChopCore V1 - Pure Macro Confusion Detector")
    print("=" * 80)
    print("Layer 1: Opposition (USD vs China)")
    print("Layer 2: Uncertainty (VIX & CNY spread)")
    print("Layer 3: ADX Confirmation")
    print()
    print("VIX FILTER: Only operates when VIX in [15, 25] range")
    print("Outside this range: Returns NORMAL (1.0x sizing)")
    print()
    print("Use build_chopcore_v1.py to run full calculation")