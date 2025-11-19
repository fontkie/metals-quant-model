"""
CRISISCORE V2 - MULTI-DIMENSIONAL CRISIS DETECTOR
Robust crisis detection using credit stress + volatility + velocity

Architecture:
- Layer 1: Credit Stress (HY spreads) - PRIMARY signal
- Layer 2: Volatility (VIX) - CONFIRMATION signal  
- Layer 3: Velocity (HY spread changes) - ACCELERATION/DECELERATION detector

Key Insight: HY spreads (correlation 0.776 with VIX) are more reliable than VIX alone
because they reflect actual credit market stress, not just equity volatility.

Author: Renaissance crisis detection
Date: November 7, 2025
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple


def calculate_hy_credit_stress(
    hy_spread: pd.Series,
    lookback: int,
    config: Dict
) -> Tuple[pd.Series, pd.Series]:
    """
    Calculate credit stress score from HY spreads.
    
    HY spreads are THE premier crisis indicator:
    - Reflect actual credit market conditions
    - More stable than VIX (less jumpy)
    - Lead equity volatility
    
    Args:
        hy_spread: HY spread in basis points
        lookback: Lookback period for percentile ranking (252 = 1 year)
        config: Configuration with thresholds
        
    Returns:
        Tuple of (credit_stress_score, spread_percentile)
    """
    thresholds = config['credit_stress']
    
    # Calculate percentile rank (rolling to avoid look-ahead bias)
    spread_percentile = hy_spread.rolling(lookback).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
    )
    
    # Score based on absolute levels (from historical analysis)
    # Using fixed thresholds + percentile for robustness
    stress_from_level = pd.Series(0.0, index=hy_spread.index)
    
    # Thresholds from 25-year analysis
    normal_threshold = thresholds['normal']       # 495 bps (60th percentile)
    stress_threshold = thresholds['stress']       # 661 bps (80th percentile)
    precrisis_threshold = thresholds['precrisis'] # 760 bps (90th percentile)
    crisis_threshold = thresholds['crisis']       # 850 bps (95th percentile)
    
    # Score: 0.0 (normal) to 1.0 (severe crisis)
    stress_from_level[hy_spread < normal_threshold] = 0.0
    stress_from_level[(hy_spread >= normal_threshold) & (hy_spread < stress_threshold)] = 0.3
    stress_from_level[(hy_spread >= stress_threshold) & (hy_spread < precrisis_threshold)] = 0.6
    stress_from_level[(hy_spread >= precrisis_threshold) & (hy_spread < crisis_threshold)] = 0.8
    stress_from_level[hy_spread >= crisis_threshold] = 1.0
    
    # Combine absolute level with percentile (50/50 weight)
    # This makes it robust to regime shifts
    credit_stress_score = (stress_from_level * 0.5 + spread_percentile * 0.5)
    
    return credit_stress_score, spread_percentile


def calculate_hy_velocity(
    hy_spread: pd.Series,
    config: Dict
) -> pd.Series:
    """
    Calculate HY spread velocity (rate of change).
    
    Rapid widening = crisis accelerating
    Rapid tightening = crisis easing
    
    Args:
        hy_spread: HY spread in basis points
        config: Configuration with velocity thresholds
        
    Returns:
        pd.Series: Velocity score (0 to 1)
    """
    vel_config = config['velocity']
    
    # Calculate 10-day and 30-day changes
    change_10d = hy_spread.diff(10)
    change_30d = hy_spread.diff(30)
    
    # Thresholds from analysis
    rapid_widen_10d = vel_config['rapid_widen_10d']  # 80 bps
    rapid_widen_30d = vel_config['rapid_widen_30d']  # 150 bps
    
    # Velocity score: 0 (stable/tightening) to 1.0 (rapid widening)
    velocity_score = pd.Series(0.0, index=hy_spread.index)
    
    # 10-day velocity (more sensitive)
    velocity_10d = (change_10d / rapid_widen_10d).clip(0, 1.0)
    
    # 30-day velocity (trend confirmation)
    velocity_30d = (change_30d / rapid_widen_30d).clip(0, 1.0)
    
    # Combined: max of two (catch either rapid or sustained widening)
    velocity_score = pd.Series(np.maximum(velocity_10d, velocity_30d * 0.7), index=hy_spread.index)
    
    return velocity_score


def calculate_vix_stress(
    vix: pd.Series,
    lookback: int,
    config: Dict
) -> pd.Series:
    """
    Calculate VIX stress score.
    
    Now used as CONFIRMATION, not primary signal.
    
    Args:
        vix: VIX index values
        lookback: Lookback period for percentile
        config: Configuration with VIX thresholds
        
    Returns:
        pd.Series: VIX stress score (0 to 1)
    """
    vix_config = config['vix_stress']
    
    # Absolute level thresholds
    normal_vix = vix_config['normal']       # 20
    elevated_vix = vix_config['elevated']   # 25
    stress_vix = vix_config['stress']       # 30
    crisis_vix = vix_config['crisis']       # 40
    
    vix_score = pd.Series(0.0, index=vix.index)
    
    vix_score[vix < normal_vix] = 0.0
    vix_score[(vix >= normal_vix) & (vix < elevated_vix)] = 0.2
    vix_score[(vix >= elevated_vix) & (vix < stress_vix)] = 0.4
    vix_score[(vix >= stress_vix) & (vix < crisis_vix)] = 0.7
    vix_score[vix >= crisis_vix] = 1.0
    
    return vix_score


def calculate_composite_crisis_score(
    credit_stress: pd.Series,
    vix_stress: pd.Series,
    velocity: pd.Series,
    config: Dict
) -> pd.Series:
    """
    Combine all crisis indicators into composite score.
    
    Weighting philosophy:
    - Credit stress (HY spreads): 60% - PRIMARY signal, most reliable
    - VIX stress: 25% - CONFIRMATION, catches fast-moving crises
    - Velocity: 15% - ACCELERATION detector, flags deteriorating conditions
    
    Args:
        credit_stress: Credit stress score (0-1)
        vix_stress: VIX stress score (0-1)
        velocity: Velocity score (0-1)
        config: Configuration with weights
        
    Returns:
        pd.Series: Composite crisis score (0-1)
    """
    weights = config['composite_weights']
    
    composite = (
        credit_stress * weights['credit_stress'] +
        vix_stress * weights['vix_stress'] +
        velocity * weights['velocity']
    )
    
    composite = composite.clip(0, 1)
    
    return composite


def classify_crisis_regime(
    composite_score: pd.Series,
    hy_spread: pd.Series,
    vix: pd.Series,
    config: Dict
) -> Tuple[pd.Series, pd.Series]:
    """
    Classify crisis regime and assign sizing.
    
    Four-tier system:
    1. NORMAL: < 0.40 composite â†’ 1.0x sizing
    2. STRESS: 0.40-0.60 composite â†’ 0.75x sizing (mild defense)
    3. PRE_CRISIS: 0.60-0.75 composite â†’ 0.50x sizing (moderate defense)
    4. CRISIS: > 0.75 composite â†’ 0.25x sizing (deep defense)
    
    Args:
        composite_score: Composite crisis score
        hy_spread: HY spread (for diagnostics)
        vix: VIX (for diagnostics)
        config: Configuration with thresholds
        
    Returns:
        Tuple of (regime_labels, sizing_multipliers)
    """
    regime_config = config['regime_classification']
    sizing_config = config['sizing']
    
    regime = pd.Series('NORMAL', index=composite_score.index)
    sizing = pd.Series(1.0, index=composite_score.index)
    
    # Classify based on composite score
    stress_mask = composite_score >= regime_config['stress_threshold']
    precrisis_mask = composite_score >= regime_config['precrisis_threshold']
    crisis_mask = composite_score >= regime_config['crisis_threshold']
    
    # Apply labels (from lowest to highest severity, so highest overwrites)
    regime.loc[stress_mask] = 'STRESS'
    sizing.loc[stress_mask] = sizing_config['stress']
    
    regime.loc[precrisis_mask] = 'PRE_CRISIS'
    sizing.loc[precrisis_mask] = sizing_config['precrisis']
    
    regime.loc[crisis_mask] = 'CRISIS'
    sizing.loc[crisis_mask] = sizing_config['crisis']
    
    return regime, sizing


def run_crisiscore_detection(
    data: Dict[str, pd.Series],
    config: Dict
) -> Dict[str, pd.DataFrame]:
    """
    Main entry point: run CrisisCore v2 detection.
    
    Args:
        data: Dictionary with keys:
            - 'hy_spread': HY spread in basis points
            - 'vix': VIX index
        config: Configuration dictionary
        
    Returns:
        Dictionary with detection results
    """
    lookback = config['parameters']['lookback']
    
    # Layer 1: Credit Stress (HY spreads)
    credit_stress, hy_percentile = calculate_hy_credit_stress(
        data['hy_spread'],
        lookback,
        config
    )
    
    # Layer 2: Velocity (HY spread changes)
    velocity = calculate_hy_velocity(
        data['hy_spread'],
        config
    )
    
    # Layer 3: VIX Stress
    vix_stress = calculate_vix_stress(
        data['vix'],
        lookback,
        config
    )
    
    # Composite Crisis Score
    composite_crisis = calculate_composite_crisis_score(
        credit_stress,
        vix_stress,
        velocity,
        config
    )
    
    # Regime Classification
    regime, sizing = classify_crisis_regime(
        composite_crisis,
        data['hy_spread'],
        data['vix'],
        config
    )
    
    # Package results
    scores = pd.DataFrame({
        'credit_stress': credit_stress,
        'vix_stress': vix_stress,
        'velocity': velocity,
        'composite_crisis': composite_crisis,
        'hy_percentile': hy_percentile
    })
    
    regimes = pd.DataFrame({
        'regime': regime,
        'sizing': sizing,
        'hy_spread': data['hy_spread'],
        'vix': data['vix']
    })
    
    return {
        'scores': scores,
        'regimes': regimes
    }


def load_config(config_path: str) -> Dict:
    """Load configuration from YAML file."""
    import yaml
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config