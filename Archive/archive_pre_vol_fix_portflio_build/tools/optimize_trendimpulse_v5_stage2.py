#!/usr/bin/env python3
"""
TrendImpulse V5 - Stage 2 Optimization
======================================
Vol Regime Scaling Optimization (Given Best Core Params from Stage 1)

CRITICAL RULES:
1. Uses best parameters from Stage 1
2. Optimizes ONLY on in-sample data (2000-2018)
3. Tests regime scaling on top of core momentum
4. Out-of-sample (2019-2025) never touched until Stage 3

Stage 2: Vol Regime Scaling Parameters
- low_vol_threshold: [0.35, 0.40, 0.45]
- medium_vol_threshold: [0.70, 0.75, 0.80]
- low_vol_scale: [1.3, 1.5, 1.7]
- medium_vol_scale: [0.6, 0.8, 1.0]  # NOT 0.4!
- high_vol_scale: [0.5, 0.7, 0.9]

Expected Results:
- IS Sharpe: 0.45-0.55 (improvement over Stage 1)
- 243 combinations tested
- Best params saved for Stage 3 OOS validation

Time: ~15-20 minutes
"""

import sys
import json
import itertools
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd
import numpy as np

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))


def calculate_simple_metrics(
    positions: pd.Series,
    returns: pd.Series,
    target_vol: float = 0.10,
    cost_bps: float = 3.0,
) -> Dict:
    """Calculate strategy metrics (same as Stage 1)"""
    # Vol targeting (simplified)
    pos_abs = positions.abs()
    strategy_returns_raw = positions.shift(1) * returns
    realized_vol = strategy_returns_raw.rolling(63).std() * np.sqrt(252)
    scale = np.where(realized_vol > 0.01, target_vol / realized_vol, 1.0)
    scale = np.clip(scale, 0.2, 3.0)
    positions_scaled = positions * scale
    
    # Strategy returns
    strategy_returns = positions_scaled.shift(1) * returns
    
    # Transaction costs
    turnover = positions_scaled.diff().abs()
    costs = turnover * (cost_bps / 10000)
    strategy_returns_net = strategy_returns - costs
    
    # Metrics
    valid_returns = strategy_returns_net.dropna()
    if len(valid_returns) < 252:
        return {
            'sharpe': 0.0,
            'annual_return': 0.0,
            'annual_vol': 0.0,
            'max_drawdown': 0.0,
            'annual_turnover': 0.0,
            'pct_active': 0.0,
        }
    
    annual_return = valid_returns.mean() * 252
    annual_vol = valid_returns.std() * np.sqrt(252)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0.0
    
    # Max drawdown
    cum_returns = (1 + valid_returns).cumprod()
    running_max = cum_returns.expanding().max()
    drawdown = (cum_returns - running_max) / running_max
    max_drawdown = drawdown.min()
    
    # Turnover
    annual_turnover = turnover.sum() * 252 / len(turnover)
    
    # Activity
    pct_active = (pos_abs > 0.01).mean() * 100
    
    return {
        'sharpe': sharpe,
        'annual_return': annual_return,
        'annual_vol': annual_vol,
        'max_drawdown': max_drawdown,
        'annual_turnover': annual_turnover,
        'pct_active': pct_active,
    }


def generate_trendimpulse_v5_signal_with_regime(
    df: pd.DataFrame,
    momentum_window: int,
    entry_threshold: float,
    exit_threshold: float,
    low_vol_threshold: float,
    medium_vol_threshold: float,
    low_vol_scale: float,
    medium_vol_scale: float,
    high_vol_scale: float,
    vol_window: int = 63,
    vol_percentile_window: int = 252,
    weekly_updates: bool = True,
    update_frequency: int = 5,
) -> pd.Series:
    """
    TrendImpulse signal WITH vol regime scaling.
    """
    price = df['price'].values
    n = len(price)
    
    # Calculate returns for vol
    returns = df['price'].pct_change().values
    
    # Calculate momentum
    momentum = np.zeros(n)
    for i in range(momentum_window, n):
        momentum[i] = price[i] / price[i - momentum_window] - 1
    
    # Generate base position
    position_raw = np.zeros(n)
    current_state = 0
    
    for i in range(momentum_window, n):
        mom = momentum[i]
        
        if current_state == 0:  # FLAT
            if mom > entry_threshold:
                current_state = 1
            elif mom < -entry_threshold:
                current_state = -1
        elif current_state == 1:  # LONG
            if mom < -entry_threshold:
                current_state = -1
            elif mom < exit_threshold:
                current_state = 0
        elif current_state == -1:  # SHORT
            if mom > entry_threshold:
                current_state = 1
            elif mom > -exit_threshold:
                current_state = 0
        
        position_raw[i] = current_state
    
    # Calculate rolling vol
    vol = pd.Series(returns).rolling(vol_window, min_periods=vol_window).std() * np.sqrt(252)
    vol = vol.values
    
    # Calculate percentile rank
    vol_percentile = np.zeros(n)
    for i in range(vol_percentile_window, n):
        window = vol[i - vol_percentile_window + 1:i + 1]
        window = window[~np.isnan(window)]
        if len(window) > 0:
            vol_percentile[i] = (window < vol[i]).sum() / len(window)
    
    # Apply regime scaling
    regime_scale = np.ones(n)
    
    if weekly_updates:
        last_scale = 1.0
        for i in range(n):
            if i % update_frequency == 0 or i < vol_window:
                if np.isnan(vol_percentile[i]) or i < vol_percentile_window:
                    last_scale = 1.0
                elif vol_percentile[i] < low_vol_threshold:
                    last_scale = low_vol_scale
                elif vol_percentile[i] < medium_vol_threshold:
                    last_scale = medium_vol_scale
                else:
                    last_scale = high_vol_scale
            regime_scale[i] = last_scale
    else:
        for i in range(n):
            if np.isnan(vol_percentile[i]) or i < vol_percentile_window:
                regime_scale[i] = 1.0
            elif vol_percentile[i] < low_vol_threshold:
                regime_scale[i] = low_vol_scale
            elif vol_percentile[i] < medium_vol_threshold:
                regime_scale[i] = medium_vol_scale
            else:
                regime_scale[i] = high_vol_scale
    
    position_final = position_raw * regime_scale
    
    return pd.Series(position_final, index=df.index)


def optimize_stage2(
    df_is: pd.DataFrame,
    best_stage1_params: Dict,
    output_dir: Path,
) -> Tuple[Dict, pd.DataFrame]:
    """
    Stage 2: Optimize vol regime scaling given best Stage 1 params.
    
    Returns:
        best_params: Dict with full best parameters
        results_df: DataFrame with all results
    """
    print(f"\n{'='*70}")
    print("TRENDIMPULSE V5 - STAGE 2 OPTIMIZATION")
    print("Vol Regime Scaling Parameters")
    print(f"{'='*70}")
    print(f"In-Sample Period: {df_is['date'].min()} to {df_is['date'].max()}")
    print(f"Observations: {len(df_is)}")
    print()
    
    print("Stage 1 Best Parameters (Fixed):")
    for k, v in best_stage1_params.items():
        print(f"  {k}: {v}")
    print()
    
    # Parameter grid
    grid = {
        'low_vol_threshold': [0.35, 0.40, 0.45],
        'medium_vol_threshold': [0.70, 0.75, 0.80],
        'low_vol_scale': [1.3, 1.5, 1.7],
        'medium_vol_scale': [0.6, 0.8, 1.0],  # NOT 0.4!
        'high_vol_scale': [0.5, 0.7, 0.9],
    }
    
    # Generate all combinations
    param_names = list(grid.keys())
    param_values = [grid[name] for name in param_names]
    combinations = list(itertools.product(*param_values))
    
    print(f"Testing {len(combinations)} parameter combinations...")
    print(f"Grid:")
    for name, values in grid.items():
        print(f"  {name}: {values}")
    print()
    
    # Test all combinations
    results = []
    returns = df_is['price'].pct_change()
    
    for i, combo in enumerate(combinations, 1):
        params = dict(zip(param_names, combo))
        
        # Combine with Stage 1 params (exclude non-parameter keys like 'sharpe')
        stage1_signal_params = {k: v for k, v in best_stage1_params.items() 
                                if k in ['momentum_window', 'entry_threshold', 'exit_threshold']}
        
        # Ensure integer parameters are integers
        if 'momentum_window' in stage1_signal_params:
            stage1_signal_params['momentum_window'] = int(stage1_signal_params['momentum_window'])
        
        full_params = {**stage1_signal_params, **params}
        
        # Generate signal
        signal = generate_trendimpulse_v5_signal_with_regime(df_is, **full_params)
        
        # Calculate metrics
        metrics = calculate_simple_metrics(
            positions=signal,
            returns=returns,
            target_vol=0.10,
            cost_bps=3.0,
        )
        
        # Store results
        result = {**params, **metrics}
        results.append(result)
        
        if i % 50 == 0:
            print(f"  Tested {i}/{len(combinations)}... Best Sharpe so far: {max(r['sharpe'] for r in results):.3f}")
    
    # Convert to DataFrame
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('sharpe', ascending=False)
    
    # Get best parameters
    best_regime_params = results_df.iloc[0][param_names].to_dict()
    best_metrics = results_df.iloc[0][list(metrics.keys())].to_dict()
    
    # Build full params (exclude non-parameter keys like 'sharpe')
    stage1_signal_params = {k: v for k, v in best_stage1_params.items() 
                            if k in ['momentum_window', 'entry_threshold', 'exit_threshold']}
    
    # Ensure integer parameters are integers
    if 'momentum_window' in stage1_signal_params:
        stage1_signal_params['momentum_window'] = int(stage1_signal_params['momentum_window'])
    
    best_params_full = {**stage1_signal_params, **best_regime_params}
    
    print(f"\n{'='*70}")
    print("STAGE 2 RESULTS")
    print(f"{'='*70}")
    print(f"\nBest Regime Parameters:")
    for k, v in best_regime_params.items():
        print(f"  {k}: {v}")
    
    print(f"\nBest Performance (In-Sample):")
    print(f"  Sharpe:         {best_metrics['sharpe']:+.3f}")
    print(f"  Annual Return:  {best_metrics['annual_return']*100:+.2f}%")
    print(f"  Annual Vol:     {best_metrics['annual_vol']*100:.2f}%")
    print(f"  Max Drawdown:   {best_metrics['max_drawdown']*100:.2f}%")
    print(f"  Turnover:       {best_metrics['annual_turnover']:.1f}x")
    print(f"  Activity:       {best_metrics['pct_active']:.1f}%")
    
    # Compare to Stage 1
    stage1_sharpe = best_stage1_params.get('sharpe', 0.0)
    improvement = best_metrics['sharpe'] - stage1_sharpe
    print(f"\nImprovement vs Stage 1:")
    print(f"  Stage 1 Sharpe: {stage1_sharpe:+.3f}")
    print(f"  Stage 2 Sharpe: {best_metrics['sharpe']:+.3f}")
    print(f"  Improvement:    {improvement:+.3f} ({improvement/stage1_sharpe*100:+.1f}%)")
    
    # Top 5 combinations
    print(f"\nTop 5 Regime Parameter Combinations:")
    print(results_df.head(5)[['low_vol_scale', 'medium_vol_scale', 'high_vol_scale', 'sharpe', 'annual_return']].to_string(index=False))
    
    # Save results
    results_path = output_dir / 'stage2_full_results.csv'
    results_df.to_csv(results_path, index=False)
    print(f"\nFull results saved: {results_path}")
    
    best_params_output = {
        'stage1_params': best_stage1_params,
        'stage2_params': best_regime_params,
        'full_params': best_params_full,
        'best_metrics': best_metrics,
        'improvement_vs_stage1': improvement,
        'optimization_date': pd.Timestamp.now().isoformat(),
        'in_sample_period': f"{df_is['date'].min()} to {df_is['date'].max()}",
        'combinations_tested': len(combinations),
    }
    
    params_path = output_dir / 'stage2_best_params.json'
    with open(params_path, 'w') as f:
        json.dump(best_params_output, f, indent=2)
    print(f"Best parameters saved: {params_path}")
    
    print(f"\n{'='*70}")
    print("Next Step: Run Stage 3 OOS Validation (ONE TIME ONLY!)")
    print(f"{'='*70}\n")
    
    return best_params_full, results_df


def main():
    # Paths
    data_path = Path('Data/copper/pricing/canonical/copper_lme_3mo.canonical.csv')
    output_dir = Path('outputs/Copper/TrendImpulse_v5/optimization')
    stage1_params_path = output_dir / 'stage1_best_params.json'
    
    # Check Stage 1 results exist
    if not stage1_params_path.exists():
        print(f"ERROR: Stage 1 results not found at {stage1_params_path}")
        print("Please run Stage 1 optimization first!")
        return 1
    
    # Load Stage 1 best params
    print("Loading Stage 1 best parameters...")
    with open(stage1_params_path, 'r') as f:
        stage1_data = json.load(f)
    
    best_stage1_params = stage1_data['best_params']
    stage1_metrics = stage1_data['best_metrics']
    
    # Convert integer parameters from JSON (they load as floats)
    best_stage1_params['momentum_window'] = int(best_stage1_params['momentum_window'])
    
    # Add metrics to params for comparison
    best_stage1_params['sharpe'] = stage1_metrics['sharpe']
    
    print(f"Stage 1 IS Sharpe: {stage1_metrics['sharpe']:.3f}")
    print()
    
    # Load data
    print("Loading canonical data...")
    df = pd.read_csv(data_path, parse_dates=['date'])
    
    # Split in-sample
    IS_END = '2018-12-31'
    df_is = df[df['date'] <= IS_END].copy()
    
    print(f"In-Sample: {df_is['date'].min()} to {df_is['date'].max()} ({len(df_is)} obs)")
    
    # Run optimization
    best_params, results_df = optimize_stage2(df_is, best_stage1_params, output_dir)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())