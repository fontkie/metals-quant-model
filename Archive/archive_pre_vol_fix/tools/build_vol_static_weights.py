#!/usr/bin/env python3
"""
Build Static Vol Weights
=========================

Calculates optimal STATIC (fixed) weights for the three-sleeve portfolio.
Saves weights to CSV for use by vol_static.py.

This separates weight CALCULATION from weight APPLICATION - if sleeves change,
just re-run this script to recalculate optimal static weights.

Methods available:
  - equal_weight: 33.3% each (naive baseline)
  - min_variance: Minimize portfolio volatility
  - max_sharpe: Maximize Sharpe ratio
  - inverse_vol: Weight inversely to sleeve volatility (risk parity lite)
  - grid_search: Grid search over weight space for best Sharpe

Author: Claude (ex-Renaissance) + Kieran
Date: November 13, 2025
Version: 1.0
"""

import argparse
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from itertools import product
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_sleeve_returns(sleeve_paths, start_date=None, end_date=None):
    """
    Load sleeve returns and align on common dates.
    
    Returns:
        DataFrame with columns: date, TrendMedium_ret, TrendImpulse_ret, MomentumCore_ret
    """
    # Load each sleeve
    dfs = {}
    for name, path in sleeve_paths.items():
        df = pd.read_csv(path)
        df['date'] = pd.to_datetime(df['date'])
        
        # Handle different column names - prioritize pnl_net (net portfolio return after costs)
        if 'pnl_net' in df.columns:
            df = df[['date', 'pnl_net']].rename(columns={'pnl_net': f'{name}_ret'})
        elif 'portfolio_ret' in df.columns:
            df = df[['date', 'portfolio_ret']].rename(columns={'portfolio_ret': f'{name}_ret'})
        elif 'ret' in df.columns:
            df = df[['date', 'ret']].rename(columns={'ret': f'{name}_ret'})
        else:
            raise ValueError(f"Sleeve {name} missing return column (pnl_net, portfolio_ret, or ret)")
        
        dfs[name] = df
    
    # Merge on date
    merged = dfs['TrendMedium']
    for name in ['TrendImpulse', 'MomentumCore']:
        merged = merged.merge(dfs[name], on='date', how='inner')
    
    # Filter date range if specified
    if start_date:
        merged = merged[merged['date'] >= start_date]
    if end_date:
        merged = merged[merged['date'] <= end_date]
    
    return merged


def calculate_equal_weight():
    """Simple equal weight: 33.3% each."""
    return {
        'TrendMedium': 1/3,
        'TrendImpulse': 1/3,
        'MomentumCore': 1/3
    }


def calculate_inverse_vol(returns_df):
    """
    Inverse volatility weighting (risk parity lite).
    Weight inversely proportional to volatility.
    """
    sleeve_cols = ['TrendMedium_ret', 'TrendImpulse_ret', 'MomentumCore_ret']
    
    # Calculate volatilities
    vols = returns_df[sleeve_cols].std()
    
    # Inverse volatility
    inv_vols = 1.0 / vols
    
    # Normalize to sum to 1
    weights = inv_vols / inv_vols.sum()
    
    return {
        'TrendMedium': weights['TrendMedium_ret'],
        'TrendImpulse': weights['TrendImpulse_ret'],
        'MomentumCore': weights['MomentumCore_ret']
    }


def calculate_min_variance(returns_df):
    """
    Minimum variance portfolio.
    Minimize portfolio volatility.
    """
    sleeve_cols = ['TrendMedium_ret', 'TrendImpulse_ret', 'MomentumCore_ret']
    returns = returns_df[sleeve_cols].values
    
    # Covariance matrix
    cov_matrix = np.cov(returns.T)
    
    # Inverse of covariance matrix
    inv_cov = np.linalg.inv(cov_matrix)
    
    # Min variance weights: w = inv(Σ) * 1 / (1' * inv(Σ) * 1)
    ones = np.ones(len(sleeve_cols))
    weights = inv_cov @ ones
    weights = weights / weights.sum()
    
    return {
        'TrendMedium': weights[0],
        'TrendImpulse': weights[1],
        'MomentumCore': weights[2]
    }


def calculate_max_sharpe(returns_df):
    """
    Maximum Sharpe ratio portfolio.
    Optimize for risk-adjusted returns.
    """
    sleeve_cols = ['TrendMedium_ret', 'TrendImpulse_ret', 'MomentumCore_ret']
    returns = returns_df[sleeve_cols].values
    
    # Mean returns and covariance
    mean_returns = returns.mean(axis=0) * 252  # Annualized
    cov_matrix = np.cov(returns.T) * 252  # Annualized
    
    # Use scipy optimization
    from scipy.optimize import minimize
    
    def neg_sharpe(weights):
        """Negative Sharpe (for minimization)."""
        portfolio_return = weights @ mean_returns
        portfolio_vol = np.sqrt(weights @ cov_matrix @ weights)
        return -portfolio_return / portfolio_vol if portfolio_vol > 0 else 0
    
    # Constraints: weights sum to 1, all weights >= 0
    constraints = {'type': 'eq', 'fun': lambda w: w.sum() - 1}
    bounds = [(0, 1) for _ in range(len(sleeve_cols))]
    
    # Initial guess: equal weight
    x0 = np.ones(len(sleeve_cols)) / len(sleeve_cols)
    
    result = minimize(neg_sharpe, x0, method='SLSQP', bounds=bounds, constraints=constraints)
    
    return {
        'TrendMedium': result.x[0],
        'TrendImpulse': result.x[1],
        'MomentumCore': result.x[2]
    }


def calculate_grid_search(returns_df, step=0.05):
    """
    Grid search over weight space.
    
    Args:
        step: Grid step size (0.05 = 5% increments)
    
    Returns:
        Weights with best Sharpe ratio
    """
    sleeve_cols = ['TrendMedium_ret', 'TrendImpulse_ret', 'MomentumCore_ret']
    returns = returns_df[sleeve_cols].values
    
    # Generate weight grid (weights sum to 1)
    weight_range = np.arange(0, 1 + step, step)
    
    best_sharpe = -np.inf
    best_weights = None
    
    print(f"  Grid searching with step={step}...")
    count = 0
    
    for w1 in weight_range:
        for w2 in weight_range:
            w3 = 1.0 - w1 - w2
            
            # Skip invalid weights
            if w3 < 0 or w3 > 1:
                continue
            
            weights = np.array([w1, w2, w3])
            
            # Calculate portfolio returns
            portfolio_rets = returns @ weights
            
            # Calculate Sharpe
            mean_ret = portfolio_rets.mean() * 252
            vol = portfolio_rets.std() * np.sqrt(252)
            sharpe = mean_ret / vol if vol > 0 else 0
            
            count += 1
            
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_weights = weights
    
    print(f"  Evaluated {count} weight combinations")
    print(f"  Best Sharpe: {best_sharpe:.4f}")
    
    return {
        'TrendMedium': best_weights[0],
        'TrendImpulse': best_weights[1],
        'MomentumCore': best_weights[2]
    }


def calculate_portfolio_metrics(returns_df, weights):
    """Calculate metrics for a given set of weights."""
    sleeve_cols = ['TrendMedium_ret', 'TrendImpulse_ret', 'MomentumCore_ret']
    returns = returns_df[sleeve_cols].values
    
    # Weight array
    w = np.array([weights['TrendMedium'], weights['TrendImpulse'], weights['MomentumCore']])
    
    # Portfolio returns
    portfolio_rets = returns @ w
    
    # Metrics
    mean_ret = portfolio_rets.mean() * 252
    vol = portfolio_rets.std() * np.sqrt(252)
    sharpe = mean_ret / vol if vol > 0 else 0
    
    # Max drawdown
    cumulative = (1 + portfolio_rets).cumprod()
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = (cumulative - running_max) / running_max
    max_dd = drawdowns.min()
    
    return {
        'annual_return': mean_ret,
        'annual_vol': vol,
        'sharpe': sharpe,
        'max_drawdown': max_dd
    }


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Calculate optimal static weights for vol-static baseline"
    )
    
    parser.add_argument(
        '--sleeve-dir',
        default=r'C:\Code\Metals\outputs\Copper',
        help='Base directory for sleeve outputs'
    )
    
    parser.add_argument(
        '--outdir',
        default=r'C:\Code\Metals\outputs\Copper\VolRegime',
        help='Output directory for vol_static_weights.csv'
    )
    
    parser.add_argument(
        '--method',
        default='grid_search',
        choices=['equal_weight', 'inverse_vol', 'min_variance', 'max_sharpe', 'grid_search'],
        help='Weight optimization method'
    )
    
    parser.add_argument(
        '--grid-step',
        type=float,
        default=0.05,
        help='Grid search step size (default: 0.05 = 5%% increments)'
    )
    
    parser.add_argument(
        '--start-date',
        default='2000-01-01',
        help='Optimization start date (IS period)'
    )
    
    parser.add_argument(
        '--end-date',
        default='2018-12-31',
        help='Optimization end date (IS period)'
    )
    
    args = parser.parse_args()
    
    # Print header
    print("\n" + "=" * 80)
    print("STATIC VOL WEIGHTS BUILDER")
    print("=" * 80)
    print(f"Method:      {args.method}")
    print(f"Period:      {args.start_date} to {args.end_date}")
    print(f"Output:      {args.outdir}")
    
    try:
        # Step 1: Load sleeve data
        print("\n📂 Loading sleeve data...")
        sleeve_paths = {
            'TrendMedium': Path(args.sleeve_dir) / 'TrendMedium' / 'daily_series.csv',
            'TrendImpulse': Path(args.sleeve_dir) / 'TrendImpulse_v4' / 'daily_series.csv',
            'MomentumCore': Path(args.sleeve_dir) / 'MomentumCore_v1' / 'daily_series.csv',
        }
        
        returns_df = load_sleeve_returns(
            sleeve_paths,
            start_date=args.start_date,
            end_date=args.end_date
        )
        
        print(f"  ✓ Loaded {len(returns_df)} days of returns")
        print(f"  ✓ Date range: {returns_df['date'].min()} to {returns_df['date'].max()}")
        
        # Step 2: Calculate weights
        print(f"\n⚖️  Calculating weights using {args.method}...")
        
        if args.method == 'equal_weight':
            weights = calculate_equal_weight()
        elif args.method == 'inverse_vol':
            weights = calculate_inverse_vol(returns_df)
        elif args.method == 'min_variance':
            weights = calculate_min_variance(returns_df)
        elif args.method == 'max_sharpe':
            weights = calculate_max_sharpe(returns_df)
        elif args.method == 'grid_search':
            weights = calculate_grid_search(returns_df, step=args.grid_step)
        
        print(f"\n  Calculated weights:")
        for name, weight in weights.items():
            print(f"    {name:15s}: {weight:.4f} ({weight*100:.2f}%)")
        
        # Step 3: Calculate metrics
        print(f"\n📈 Calculating portfolio metrics...")
        metrics = calculate_portfolio_metrics(returns_df, weights)
        
        print(f"  Sharpe:      {metrics['sharpe']:.4f}")
        print(f"  Return:      {metrics['annual_return']*100:.2f}%")
        print(f"  Vol:         {metrics['annual_vol']*100:.2f}%")
        print(f"  Max DD:      {metrics['max_drawdown']*100:.2f}%")
        
        # Step 4: Save outputs
        print(f"\n💾 Saving outputs to {args.outdir}...")
        output_dir = Path(args.outdir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save weights CSV
        weights_df = pd.DataFrame([weights])
        weights_df.to_csv(output_dir / 'vol_static_weights.csv', index=False)
        print(f"  ✓ Saved vol_static_weights.csv")
        
        # Save metadata
        metadata = {
            'method': args.method,
            'optimization_period': {
                'start': args.start_date,
                'end': args.end_date,
                'days': len(returns_df)
            },
            'weights': weights,
            'metrics': {k: float(v) for k, v in metrics.items()},
            'generated_date': pd.Timestamp.now().isoformat()
        }
        
        with open(output_dir / 'vol_static_weights_metadata.json', 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"  ✓ Saved vol_static_weights_metadata.json")
        
        # Print summary
        print("\n" + "=" * 80)
        print("STATIC WEIGHTS CALCULATION COMPLETE")
        print("=" * 80)
        print(f"Weights saved to: {output_dir / 'vol_static_weights.csv'}")
        print(f"\nTo use these weights, run: scripts\\run_vol_static_weights.bat")
        print("=" * 80)
        
        return 0
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)