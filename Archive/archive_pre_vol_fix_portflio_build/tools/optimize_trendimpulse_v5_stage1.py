#!/usr/bin/env python3
"""
TrendImpulse V5 - Stage 1 Optimization
======================================
Renaissance-Grade Parameter Optimization with Zero Forward Bias

CRITICAL RULES:
1. Optimize ONLY on in-sample data (2000-2018)
2. Out-of-sample (2019-2025) never touched until Stage 3
3. Test simple momentum first (no regime scaling)
4. Report all results honestly

Stage 1: Core Momentum Parameters
- momentum_window: [15, 20, 25]
- entry_threshold: [0.008, 0.010, 0.012, 0.015]
- exit_threshold: [0.002, 0.003, 0.004, 0.005]
- use_regime_scaling: False (keep simple)

Expected Results:
- IS Sharpe: 0.35-0.45 (baseline momentum)
- 48 combinations tested
- Best params saved for Stage 2

Time: ~5-10 minutes
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
    """
    Calculate strategy metrics without full 4-layer architecture.
    Fast version for optimization.
    """
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


def generate_trendimpulse_v5_signal_simple(
    df: pd.DataFrame,
    momentum_window: int = 20,
    entry_threshold: float = 0.010,
    exit_threshold: float = 0.003,
) -> pd.Series:
    """
    Simplified TrendImpulse signal without regime scaling.
    For Stage 1 optimization only.
    """
    price = df['price'].values
    n = len(price)
    
    # Calculate momentum
    momentum = np.zeros(n)
    for i in range(momentum_window, n):
        momentum[i] = price[i] / price[i - momentum_window] - 1
    
    # Generate position with asymmetric thresholds
    position = np.zeros(n)
    current_state = 0  # -1 = short, 0 = flat, +1 = long
    
    for i in range(momentum_window, n):
        mom = momentum[i]
        
        if current_state == 0:  # FLAT
            if mom > entry_threshold:
                current_state = 1  # Enter LONG
            elif mom < -entry_threshold:
                current_state = -1  # Enter SHORT
        
        elif current_state == 1:  # LONG
            if mom < -entry_threshold:
                current_state = -1  # Flip to SHORT
            elif mom < exit_threshold:
                current_state = 0  # Exit to FLAT
        
        elif current_state == -1:  # SHORT
            if mom > entry_threshold:
                current_state = 1  # Flip to LONG
            elif mom > -exit_threshold:
                current_state = 0  # Exit to FLAT
        
        position[i] = current_state
    
    return pd.Series(position, index=df.index)


def optimize_stage1(
    df_is: pd.DataFrame,
    output_dir: Path,
) -> Tuple[Dict, pd.DataFrame]:
    """
    Stage 1: Optimize core momentum parameters on in-sample data.
    
    Returns:
        best_params: Dict with best parameters
        results_df: DataFrame with all results
    """
    print(f"\n{'='*70}")
    print("TRENDIMPULSE V5 - STAGE 1 OPTIMIZATION")
    print("Core Momentum Parameters (No Regime Scaling)")
    print(f"{'='*70}")
    print(f"In-Sample Period: {df_is['date'].min()} to {df_is['date'].max()}")
    print(f"Observations: {len(df_is)}")
    print()
    
    # Parameter grid
    grid = {
        'momentum_window': [15, 20, 25],
        'entry_threshold': [0.008, 0.010, 0.012, 0.015],
        'exit_threshold': [0.002, 0.003, 0.004, 0.005],
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
        
        # Generate signal
        signal = generate_trendimpulse_v5_signal_simple(df_is, **params)
        
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
        
        if i % 10 == 0:
            print(f"  Tested {i}/{len(combinations)}... Best Sharpe so far: {max(r['sharpe'] for r in results):.3f}")
    
    # Convert to DataFrame
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('sharpe', ascending=False)
    
    # Get best parameters
    best_params = results_df.iloc[0][param_names].to_dict()
    best_metrics = results_df.iloc[0][list(metrics.keys())].to_dict()
    
    print(f"\n{'='*70}")
    print("STAGE 1 RESULTS")
    print(f"{'='*70}")
    print(f"\nBest Parameters:")
    for k, v in best_params.items():
        print(f"  {k}: {v}")
    
    print(f"\nBest Performance (In-Sample):")
    print(f"  Sharpe:         {best_metrics['sharpe']:+.3f}")
    print(f"  Annual Return:  {best_metrics['annual_return']*100:+.2f}%")
    print(f"  Annual Vol:     {best_metrics['annual_vol']*100:.2f}%")
    print(f"  Max Drawdown:   {best_metrics['max_drawdown']*100:.2f}%")
    print(f"  Turnover:       {best_metrics['annual_turnover']:.1f}x")
    print(f"  Activity:       {best_metrics['pct_active']:.1f}%")
    
    # Top 5 combinations
    print(f"\nTop 5 Parameter Combinations:")
    print(results_df.head(5)[['momentum_window', 'entry_threshold', 'exit_threshold', 'sharpe', 'annual_return', 'pct_active']].to_string(index=False))
    
    # Save results
    results_path = output_dir / 'stage1_full_results.csv'
    results_df.to_csv(results_path, index=False)
    print(f"\nFull results saved: {results_path}")
    
    best_params_full = {
        'best_params': best_params,
        'best_metrics': best_metrics,
        'optimization_date': pd.Timestamp.now().isoformat(),
        'in_sample_period': f"{df_is['date'].min()} to {df_is['date'].max()}",
        'combinations_tested': len(combinations),
    }
    
    params_path = output_dir / 'stage1_best_params.json'
    with open(params_path, 'w') as f:
        json.dump(best_params_full, f, indent=2)
    print(f"Best parameters saved: {params_path}")
    
    print(f"\n{'='*70}")
    print("Next Step: Run Stage 2 with regime scaling optimization")
    print(f"{'='*70}\n")
    
    return best_params, results_df


def main():
    # Paths
    data_path = Path('Data/copper/pricing/canonical/copper_lme_3mo.canonical.csv')
    output_dir = Path('outputs/Copper/TrendImpulse_v5/optimization')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load data
    print("Loading canonical data...")
    df = pd.read_csv(data_path, parse_dates=['date'])
    print(f"Loaded {len(df)} observations from {df['date'].min()} to {df['date'].max()}")
    
    # Split in-sample / out-of-sample
    IS_END = '2018-12-31'
    df_is = df[df['date'] <= IS_END].copy()
    
    print(f"\nIn-Sample: {df_is['date'].min()} to {df_is['date'].max()} ({len(df_is)} obs)")
    print(f"Out-Sample: Reserved for Stage 3 validation (NEVER touched in optimization)")
    
    # Run optimization
    best_params, results_df = optimize_stage1(df_is, output_dir)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())