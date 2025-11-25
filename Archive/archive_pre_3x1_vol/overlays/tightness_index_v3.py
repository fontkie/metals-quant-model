"""
TIGHTNESS INDEX V3 - Multi-Layer Physical Market Tightness
Complete physical market tightness framework with global stocks and divergence detection

ARCHITECTURE:
Layer 1A: LME Micro Tightness (Exchange-specific signals)
  - LME on-warrant stocks (level & velocity)
  - LME 3mo-12mo spread (backwardation strength)
  - Days of consumption (LME only)

Layer 1B: Global Macro Tightness (Absolute availability)
  - Total visible stocks (LME + COMEX + SHFE)
  - Global weeks coverage (vs annual demand)
  - Cross-exchange coordination
  - Historical percentile ranking

Layer 1C: Divergence Detection (Relocation filter)
  - LME vs Global trend divergence
  - Flags relocation scenarios (2018, 2025) vs genuine tightness (2021)
  - Confidence multiplier based on alignment

OUTPUT: Tightness score (0-100) + diagnostics + confidence level

Author: Renaissance-style physical fundamentals
Date: November 7, 2025
Version: 3.0
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple
from pathlib import Path
import yaml


def load_config(config_path: str = None) -> Dict:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = Path(__file__).parent / 'tightness_index_v3.yaml'
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    return config


def calculate_lme_micro_tightness(
    lme_stocks: pd.Series,
    spread_3mo_12mo: pd.Series,
    annual_demand_kt: float,
    config: Dict
) -> pd.DataFrame:
    """
    Layer 1A: Calculate LME-specific micro tightness signals.
    
    Components:
    1. Stock level (absolute + percentile)
    2. Days of consumption
    3. Forward curve spread (backwardation)
    4. Stock velocity
    
    Args:
        lme_stocks: LME on-warrant stocks (tonnes)
        spread_3mo_12mo: 3mo-12mo spread (% backwardation)
        annual_demand_kt: Annual global demand (kt)
        config: Configuration dict
        
    Returns:
        DataFrame with LME micro signals and score
    """
    layer_config = config['layer_1a_lme_micro']
    
    df = pd.DataFrame(index=lme_stocks.index)
    
    # 1. Stock level score (percentile-based)
    stock_percentile = lme_stocks.rolling(252).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
    )
    # Invert: low stocks = high tightness
    df['stock_level_score'] = (1 - stock_percentile) * 100
    
    # 2. Days of consumption
    daily_demand_kt = annual_demand_kt / 365
    daily_demand_tonnes = daily_demand_kt * 1000
    df['days_consumption'] = lme_stocks / daily_demand_tonnes
    
    # Score days consumption (fewer days = tighter)
    thresholds = layer_config['days_consumption_thresholds']
    df['days_score'] = 50.0  # Default
    df.loc[df['days_consumption'] < thresholds['very_tight'], 'days_score'] = 95
    df.loc[(df['days_consumption'] >= thresholds['very_tight']) & 
           (df['days_consumption'] < thresholds['tight']), 'days_score'] = 75
    df.loc[(df['days_consumption'] >= thresholds['tight']) & 
           (df['days_consumption'] < thresholds['balanced']), 'days_score'] = 50
    df.loc[(df['days_consumption'] >= thresholds['balanced']) & 
           (df['days_consumption'] < thresholds['loose']), 'days_score'] = 30
    df.loc[df['days_consumption'] >= thresholds['loose'], 'days_score'] = 10
    
    # 3. Forward curve spread (backwardation = tightness)
    # Positive spread = backwardation (tight), negative = contango (loose)
    mean_backwardation = layer_config['spread_thresholds']['mean_backwardation']
    
    # Normalize around historical mean
    df['spread_normalized'] = spread_3mo_12mo - mean_backwardation
    
    # Score: deep backwardation = tight, contango = loose
    df['spread_score'] = 50 + (df['spread_normalized'] * 50)  # Rough linear scaling
    df['spread_score'] = df['spread_score'].clip(0, 100)
    
    # 4. Stock velocity (60-day % change)
    df['stock_velocity_60d'] = lme_stocks.pct_change(60) * 100
    
    # Negative velocity (falling stocks) = tightening
    # Positive velocity (rising stocks) = loosening
    df['velocity_score'] = 50 - (df['stock_velocity_60d'] / 2)  # -50% → 75, +50% → 25
    df['velocity_score'] = df['velocity_score'].clip(0, 100)
    
    # Combined LME micro score
    weights = layer_config['component_weights']
    df['lme_micro_score'] = (
        df['stock_level_score'] * weights['stock_level'] +
        df['days_score'] * weights['days_consumption'] +
        df['spread_score'] * weights['spread'] +
        df['velocity_score'] * weights['velocity']
    )
    
    return df


def calculate_global_macro_tightness(
    lme_stocks: pd.Series,
    comex_stocks: pd.Series,
    shfe_stocks: pd.Series,
    annual_demand_kt: float,
    config: Dict
) -> pd.DataFrame:
    """
    Layer 1B: Calculate global macro tightness based on total visible stocks.
    
    Components:
    1. Total visible stocks (LME + COMEX + SHFE)
    2. Weeks of global coverage
    3. Historical percentile
    4. Cross-exchange coordination
    
    Args:
        lme_stocks: LME on-warrant stocks
        comex_stocks: COMEX stocks
        shfe_stocks: SHFE on-warrant stocks
        annual_demand_kt: Annual global demand (kt)
        config: Configuration dict
        
    Returns:
        DataFrame with global macro signals and score
    """
    layer_config = config['layer_1b_global_macro']
    
    df = pd.DataFrame(index=lme_stocks.index)
    
    # 1. Total visible stocks
    df['global_stocks'] = lme_stocks + comex_stocks.reindex(lme_stocks.index, method='ffill') + shfe_stocks.reindex(lme_stocks.index, method='ffill')
    
    # 2. Weeks of global coverage
    weekly_demand_tonnes = (annual_demand_kt * 1000) / 52
    df['weeks_coverage'] = df['global_stocks'] / weekly_demand_tonnes
    
    # Score weeks coverage (fewer weeks = tighter)
    thresholds = layer_config['weeks_coverage_thresholds']
    df['coverage_score'] = 50.0
    df.loc[df['weeks_coverage'] < thresholds['very_tight'], 'coverage_score'] = 95
    df.loc[(df['weeks_coverage'] >= thresholds['very_tight']) & 
           (df['weeks_coverage'] < thresholds['tight']), 'coverage_score'] = 75
    df.loc[(df['weeks_coverage'] >= thresholds['tight']) & 
           (df['weeks_coverage'] < thresholds['balanced']), 'coverage_score'] = 50
    df.loc[(df['weeks_coverage'] >= thresholds['balanced']) & 
           (df['weeks_coverage'] < thresholds['loose']), 'coverage_score'] = 30
    df.loc[df['weeks_coverage'] >= thresholds['loose'], 'coverage_score'] = 10
    
    # 3. Historical percentile (where are we vs 25-year history?)
    percentile = df['weeks_coverage'].rolling(252*5).apply(  # 5-year lookback
        lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
    )
    # Invert: low coverage = high tightness
    df['percentile_score'] = (1 - percentile) * 100
    
    # 4. Cross-exchange coordination (are trends aligned?)
    lme_trend = lme_stocks.pct_change(60) * 100
    comex_trend = comex_stocks.reindex(lme_stocks.index, method='ffill').pct_change(60) * 100
    shfe_trend = shfe_stocks.reindex(lme_stocks.index, method='ffill').pct_change(60) * 100
    
    # Standard deviation of trends (low = coordinated, high = divergent)
    df['trend_coordination'] = pd.DataFrame({
        'lme': lme_trend,
        'comex': comex_trend,
        'shfe': shfe_trend
    }).std(axis=1)
    
    # Score: low std = high coordination = confident signal
    df['coordination_score'] = 100 - (df['trend_coordination'].clip(0, 50) * 2)
    
    # Combined global macro score
    weights = layer_config['component_weights']
    df['global_macro_score'] = (
        df['coverage_score'] * weights['coverage'] +
        df['percentile_score'] * weights['percentile'] +
        df['coordination_score'] * weights['coordination']
    )
    
    # Store trends for divergence detection
    df['lme_trend_60d'] = lme_trend
    df['global_trend_60d'] = df['global_stocks'].pct_change(60) * 100
    
    return df


def detect_divergence(
    lme_micro_score: pd.Series,
    global_macro_score: pd.Series,
    lme_trend: pd.Series,
    global_trend: pd.Series,
    config: Dict
) -> pd.DataFrame:
    """
    Layer 1C: Detect divergence between LME and global signals.
    
    Flags scenarios:
    - Relocation: LME tight but global stable (2018, 2025)
    - Regional: Global tight but LME loose (metal elsewhere)
    - Aligned: Both agree (2021 - genuine tightness)
    
    Args:
        lme_micro_score: LME micro tightness score
        global_macro_score: Global macro tightness score
        lme_trend: LME 60-day trend (%)
        global_trend: Global 60-day trend (%)
        config: Configuration dict
        
    Returns:
        DataFrame with divergence flags and confidence multipliers
    """
    layer_config = config['layer_1c_divergence']
    
    df = pd.DataFrame(index=lme_micro_score.index)
    
    # Calculate divergences
    df['score_divergence'] = abs(lme_micro_score - global_macro_score)
    df['trend_divergence'] = abs(lme_trend - global_trend)
    
    # Classify divergence level
    df['divergence_level'] = 'LOW'
    df.loc[df['score_divergence'] > layer_config['moderate_threshold'], 'divergence_level'] = 'MODERATE'
    df.loc[df['score_divergence'] > layer_config['high_threshold'], 'divergence_level'] = 'HIGH'
    
    # Determine pattern
    df['pattern'] = 'ALIGNED'
    
    # High divergence patterns
    high_div_mask = df['score_divergence'] > layer_config['high_threshold']
    
    # LME tight but global not = relocation
    lme_squeeze_mask = high_div_mask & (lme_micro_score > global_macro_score)
    df.loc[lme_squeeze_mask, 'pattern'] = 'LME_SQUEEZE_LIKELY_FALSE'
    
    # Global tight but LME not = regional tightness
    regional_mask = high_div_mask & (global_macro_score > lme_micro_score)
    df.loc[regional_mask, 'pattern'] = 'REGIONAL_TIGHTNESS_ELSEWHERE'
    
    # Assign confidence multipliers
    df['confidence_multiplier'] = 1.0
    df.loc[df['pattern'] == 'LME_SQUEEZE_LIKELY_FALSE', 'confidence_multiplier'] = 0.5
    df.loc[df['pattern'] == 'REGIONAL_TIGHTNESS_ELSEWHERE', 'confidence_multiplier'] = 1.2
    df.loc[df['divergence_level'] == 'MODERATE', 'confidence_multiplier'] = 0.8
    
    # Generate diagnostic notes
    df['diagnostic_notes'] = 'Signals aligned - high confidence'
    
    df.loc[df['pattern'] == 'LME_SQUEEZE_LIKELY_FALSE', 'diagnostic_notes'] = (
        'LME appears tight but global stocks stable. Likely relocation scenario.'
    )
    
    df.loc[df['pattern'] == 'REGIONAL_TIGHTNESS_ELSEWHERE', 'diagnostic_notes'] = (
        'Global stocks tight while LME appears loose. Metal likely tight at COMEX/SHFE.'
    )
    
    df.loc[df['divergence_level'] == 'MODERATE', 'diagnostic_notes'] = (
        'Moderate divergence between LME and global - monitor closely'
    )
    
    return df


def calculate_integrated_tightness_score(
    date: pd.Timestamp,
    lme_micro: pd.DataFrame,
    global_macro: pd.DataFrame,
    divergence: pd.DataFrame,
    config: Dict
) -> Dict:
    """
    Integrate all three layers into final tightness score.
    
    Args:
        date: Date to calculate score for
        lme_micro: LME micro signals
        global_macro: Global macro signals
        divergence: Divergence detection results
        config: Configuration dict
        
    Returns:
        Dictionary with final score and full diagnostics
    """
    if date not in lme_micro.index or date not in global_macro.index:
        return None
    
    integration_config = config['integration']
    
    # Base score (weighted combination)
    lme_score = lme_micro.loc[date, 'lme_micro_score']
    global_score = global_macro.loc[date, 'global_macro_score']
    
    base_score = (
        lme_score * integration_config['lme_weight'] +
        global_score * integration_config['global_weight']
    )
    
    # Apply divergence adjustment
    confidence_mult = divergence.loc[date, 'confidence_multiplier']
    adjusted_score = base_score * confidence_mult
    
    # Determine confidence level
    div_level = divergence.loc[date, 'divergence_level']
    if div_level == 'LOW':
        confidence_level = 'HIGH'
    elif div_level == 'MODERATE':
        confidence_level = 'MEDIUM'
    else:
        confidence_level = 'LOW'
    
    # Compile diagnostics
    result = {
        'date': date,
        'lme_micro_score': lme_score,
        'global_macro_score': global_score,
        'base_score': base_score,
        'divergence_adjustment': confidence_mult,
        'final_score': adjusted_score,
        'confidence_level': confidence_level,
        'divergence_pattern': divergence.loc[date, 'pattern'],
        'diagnostic_notes': divergence.loc[date, 'diagnostic_notes'],
        
        # Component details
        'lme_stocks_tonnes': lme_micro.loc[date, 'days_consumption'] * 
                             (config['demand']['annual_demand_kt'] * 1000 / 365),
        'days_consumption': lme_micro.loc[date, 'days_consumption'],
        'weeks_coverage': global_macro.loc[date, 'weeks_coverage'],
        'spread_3mo_12mo': lme_micro.loc[date, 'spread_normalized'],
    }
    
    return result


def run_tightness_index(
    data: Dict[str, pd.Series],
    config: Dict
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Main entry point: Run complete tightness index calculation.
    
    Args:
        data: Dictionary with required series:
            - lme_onwarrant: LME on-warrant stocks
            - comex_stocks: COMEX stocks
            - shfe_stocks: SHFE on-warrant stocks
            - spread_3mo_12mo: 3mo-12mo spread (%)
        config: Configuration dictionary
        
    Returns:
        Tuple of (scores_df, diagnostics_df)
    """
    # Extract data
    lme_stocks = data['lme_onwarrant']
    comex_stocks = data['comex_stocks']
    shfe_stocks = data['shfe_stocks']
    spread = data['spread_3mo_12mo']
    annual_demand = config['demand']['annual_demand_kt']
    
    # Layer 1A: LME Micro
    lme_micro = calculate_lme_micro_tightness(
        lme_stocks, spread, annual_demand, config
    )
    
    # Layer 1B: Global Macro
    global_macro = calculate_global_macro_tightness(
        lme_stocks, comex_stocks, shfe_stocks, annual_demand, config
    )
    
    # Layer 1C: Divergence Detection
    divergence = detect_divergence(
        lme_micro['lme_micro_score'],
        global_macro['global_macro_score'],
        lme_micro['stock_velocity_60d'],
        global_macro['global_trend_60d'],
        config
    )
    
    # Compile scores
    scores = pd.DataFrame({
        'lme_micro_score': lme_micro['lme_micro_score'],
        'global_macro_score': global_macro['global_macro_score'],
        'divergence_adjustment': divergence['confidence_multiplier'],
        'final_tightness_score': (
            (lme_micro['lme_micro_score'] * config['integration']['lme_weight'] +
             global_macro['global_macro_score'] * config['integration']['global_weight']) *
            divergence['confidence_multiplier']
        )
    })
    
    # Compile diagnostics
    diagnostics = pd.DataFrame({
        'confidence_level': divergence['divergence_level'].map({
            'LOW': 'HIGH', 'MODERATE': 'MEDIUM', 'HIGH': 'LOW'
        }),
        'pattern': divergence['pattern'],
        'days_consumption': lme_micro['days_consumption'],
        'weeks_coverage': global_macro['weeks_coverage'],
        'lme_trend_60d': lme_micro['stock_velocity_60d'],
        'global_trend_60d': global_macro['global_trend_60d'],
        'diagnostic_notes': divergence['diagnostic_notes']
    })
    
    return scores, diagnostics


if __name__ == "__main__":
    print("Tightness Index V3 - Three-Layer Physical Market Tightness")
    print("=" * 80)
    print("Layer 1A: LME Micro (exchange-specific)")
    print("Layer 1B: Global Macro (total visible stocks)")
    print("Layer 1C: Divergence Detection (relocation filter)")
    print()
    print("Use build_tightness_index_v3.py to run full calculation")
