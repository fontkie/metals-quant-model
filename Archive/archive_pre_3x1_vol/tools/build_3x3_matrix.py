#!/usr/bin/env python3
r"""
3×3 Performance Matrix Calculator
==================================
Combine Vol Regime + Trend State → Analyze sleeve performance in each regime.

Calculates on IN-SAMPLE period ONLY (2000-2018) to avoid forward bias.

9 Regime States:
  LOW × RANGING        LOW × TRANSITIONAL      LOW × TRENDING
  MEDIUM × RANGING     MEDIUM × TRANSITIONAL   MEDIUM × TRENDING  
  HIGH × RANGING       HIGH × TRANSITIONAL     HIGH × TRENDING

Author: Ex-Renaissance Quant
Date: November 12, 2025
Location: C:\Code\Metals\tools\build_3x3_matrix.py
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys

# ============================================================================
# CONFIGURATION
# ============================================================================

# IS/OOS split
IS_START = '2000-01-01'
IS_END = '2018-12-31'
OOS_START = '2019-01-01'
OOS_END = '2025-12-31'

# Determine base directory
if hasattr(sys, 'frozen'):
    BASE_DIR = Path(sys.executable).parent.parent
else:
    BASE_DIR = Path(__file__).parent.parent

# Input paths
VOL_REGIME_PATH = BASE_DIR / 'outputs' / 'Copper' / 'VolRegime' / 'vol_regimes.csv'
ADX_REGIME_PATH = BASE_DIR / 'outputs' / 'Copper' / 'VolRegime' / 'adx_trend_regimes.csv'

# Sleeve paths
SLEEVE_DIR = BASE_DIR / 'outputs' / 'Copper'
TM_PATH = SLEEVE_DIR / 'TrendMedium' / 'daily_series.csv'
TI_PATH = SLEEVE_DIR / 'TrendImpulse_v4' / 'daily_series.csv'
MC_PATH = SLEEVE_DIR / 'MomentumCore_v1' / 'daily_series.csv'

# Output path
OUTPUT_DIR = BASE_DIR / 'outputs' / 'Copper' / 'VolRegime'

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def calculate_sharpe(returns, periods_per_year=252):
    """Calculate annualized Sharpe ratio."""
    if len(returns) < 2:
        return 0.0
    mean_ret = returns.mean()
    std_ret = returns.std()
    if std_ret == 0:
        return 0.0
    sharpe = (mean_ret / std_ret) * np.sqrt(periods_per_year)
    return sharpe

def calculate_annual_return(returns, periods_per_year=252):
    """Calculate annualized return."""
    if len(returns) < 1:
        return 0.0
    return returns.mean() * periods_per_year

def calculate_annual_vol(returns, periods_per_year=252):
    """Calculate annualized volatility."""
    if len(returns) < 2:
        return 0.0
    return returns.std() * np.sqrt(periods_per_year)

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n" + "="*80)
    print("3×3 PERFORMANCE MATRIX CALCULATOR")
    print("="*80 + "\n")
    
    # Load regime classifications
    print("Loading regime classifications...")
    vol_df = pd.read_csv(VOL_REGIME_PATH)
    vol_df['date'] = pd.to_datetime(vol_df['date'])
    
    adx_df = pd.read_csv(ADX_REGIME_PATH)
    adx_df['date'] = pd.to_datetime(adx_df['date'])
    
    print(f"  ✓ Vol regimes: {len(vol_df)} days")
    print(f"  ✓ ADX regimes: {len(adx_df)} days\n")
    
    # Merge regimes
    print("Combining Vol + Trend regimes...")
    regimes = vol_df[['date', 'vol_regime']].merge(
        adx_df[['date', 'trend_state']],
        on='date',
        how='inner'
    )
    
    # Create combined regime label
    regimes['combined_regime'] = (regimes['vol_regime'] + '_' + 
                                  regimes['trend_state'])
    
    print(f"  Combined: {len(regimes)} days\n")
    
    # Load sleeve data
    print("Loading sleeve data...")
    tm = pd.read_csv(TM_PATH)
    tm['date'] = pd.to_datetime(tm['date'])
    
    ti = pd.read_csv(TI_PATH)
    ti['date'] = pd.to_datetime(ti['date'])
    
    mc = pd.read_csv(MC_PATH)
    mc['date'] = pd.to_datetime(mc['date'])
    
    print(f"  ✓ TrendMedium: {len(tm)} days")
    print(f"  ✓ TrendImpulse: {len(ti)} days")
    print(f"  ✓ MomentumCore: {len(mc)} days\n")
    
    # Merge all data
    print("Merging all data...")
    data = regimes.copy()
    data = data.merge(tm[['date', 'pnl_net']].rename(columns={'pnl_net': 'tm_ret'}), 
                     on='date', how='inner')
    data = data.merge(ti[['date', 'pnl_net']].rename(columns={'pnl_net': 'ti_ret'}), 
                     on='date', how='inner')
    data = data.merge(mc[['date', 'pnl_net']].rename(columns={'pnl_net': 'mc_ret'}), 
                     on='date', how='inner')
    
    print(f"  Merged: {len(data)} days\n")
    
    # Filter to IS period
    print(f"Filtering to IS period ({IS_START} to {IS_END})...")
    is_data = data[(data['date'] >= IS_START) & (data['date'] <= IS_END)].copy()
    print(f"  IS period: {len(is_data)} days\n")
    
    # Calculate performance matrix
    print("="*80)
    print("CALCULATING 3×3 PERFORMANCE MATRIX (IN-SAMPLE ONLY)")
    print("="*80 + "\n")
    
    results = []
    
    # Define regime order for nice output
    vol_regimes = ['LOW', 'MEDIUM', 'HIGH']
    trend_states = ['RANGING', 'TRANSITIONAL', 'TRENDING']
    
    for vol_reg in vol_regimes:
        for trend_st in trend_states:
            regime = f"{vol_reg}_{trend_st}"
            
            # Filter to regime
            regime_data = is_data[is_data['combined_regime'] == regime]
            
            if len(regime_data) == 0:
                print(f"{regime:25s}: NO DATA")
                continue
            
            n_days = len(regime_data)
            pct_time = (n_days / len(is_data)) * 100
            
            print(f"\n{regime:25s}: {n_days:4d} days ({pct_time:4.1f}%)")
            print("-" * 80)
            
            # Calculate metrics for each sleeve
            for sleeve_name, ret_col in [('TrendMedium', 'tm_ret'),
                                         ('TrendImpulse', 'ti_ret'),
                                         ('MomentumCore', 'mc_ret')]:
                
                sleeve_rets = regime_data[ret_col]
                
                sharpe = calculate_sharpe(sleeve_rets)
                annual_ret = calculate_annual_return(sleeve_rets)
                annual_vol = calculate_annual_vol(sleeve_rets)
                
                print(f"  {sleeve_name:15s}: Sharpe {sharpe:6.3f}  "
                      f"Ret {annual_ret*100:6.2f}%  Vol {annual_vol*100:5.2f}%")
                
                results.append({
                    'regime': regime,
                    'vol_regime': vol_reg,
                    'trend_state': trend_st,
                    'sleeve': sleeve_name,
                    'days': n_days,
                    'pct_of_is': pct_time,
                    'sharpe': sharpe,
                    'annual_return': annual_ret,
                    'annual_vol': annual_vol
                })
    
    # Save results
    print("\n" + "="*80)
    print("Saving results...")
    
    results_df = pd.DataFrame(results)
    
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save performance matrix
    matrix_path = output_dir / 'sleeve_performance_3x3_matrix.csv'
    results_df.to_csv(matrix_path, index=False)
    print(f"  ✓ Saved: {matrix_path}")
    
    # Save regime classification
    regime_path = output_dir / 'regime_classification_vol_trend.csv'
    data[['date', 'vol_regime', 'trend_state', 'combined_regime']].to_csv(
        regime_path, index=False
    )
    print(f"  ✓ Saved: {regime_path}")
    
    # Print summary pivot tables
    print("\n" + "="*80)
    print("SHARPE RATIO BY REGIME (IN-SAMPLE)")
    print("="*80 + "\n")
    
    for sleeve in ['TrendMedium', 'TrendImpulse', 'MomentumCore']:
        sleeve_data = results_df[results_df['sleeve'] == sleeve]
        pivot = sleeve_data.pivot(index='vol_regime', 
                                  columns='trend_state', 
                                  values='sharpe')
        
        # Reorder
        pivot = pivot.reindex(vol_regimes)
        pivot = pivot[trend_states]
        
        print(f"{sleeve}:")
        print(pivot.to_string())
        print()
    
    print("="*80)
    print("✓ 3×3 MATRIX CALCULATION COMPLETE")
    print("="*80 + "\n")
    
    print("Next step: Use this matrix to derive optimal weights per regime.")
    print("Weights will be set based on relative Sharpe ratios.\n")
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)