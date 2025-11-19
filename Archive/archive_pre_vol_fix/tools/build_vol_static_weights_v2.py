#!/usr/bin/env python3
"""
Build Static Vol Weights v2
============================

Config-driven optimizer for N sleeves with proper constraints.

Key improvements over v1:
  - Reads sleeves from config YAML (not hardcoded)
  - Supports sleeve types: always_active vs selective
  - Different floor/ceiling constraints per type
  - Outputs both YAML (for code) and CSV (for verification)
  - Timestamps on all output files
  - Full metadata for reproducibility

Author: Claude (ex-Renaissance) + Kieran
Date: November 17, 2025
Version: 2.0
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
from scipy.optimize import minimize
import yaml
import json


def load_config(config_path: str) -> dict:
    """Load portfolio configuration YAML."""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config


def load_sleeve_returns(config: dict, start_date: str = None, end_date: str = None) -> tuple:
    """
    Load sleeve returns from config-specified paths.
    
    Handles sleeves with different start dates by using OUTER join and 
    filling missing returns with 0 (sleeve inactive before data starts).
    
    Returns:
        tuple: (returns_df, sleeve_info)
            - returns_df: DataFrame with date and [sleeve]_ret columns
            - sleeve_info: dict with sleeve metadata (type, constraints, etc.)
    """
    sleeve_info = {}
    dfs = {}
    
    sleeves_cfg = config.get('sleeves', {})
    
    for sleeve_name, sleeve_cfg in sleeves_cfg.items():
        if not sleeve_cfg.get('enabled', True):
            print(f"  Skipping {sleeve_name} (disabled)")
            continue
        
        csv_path = sleeve_cfg.get('path')
        if not csv_path or not Path(csv_path).exists():
            print(f"  WARNING: Path not found for {sleeve_name}: {csv_path}")
            continue
        
        try:
            df = pd.read_csv(csv_path)
            df['date'] = pd.to_datetime(df['date'])
            
            # Get return column (prioritize pnl_net > pnl_gross > ret)
            if 'pnl_net' in df.columns:
                ret_col = 'pnl_net'
            elif 'pnl_gross' in df.columns:
                ret_col = 'pnl_gross'
            elif 'ret' in df.columns:
                ret_col = 'ret'
            else:
                print(f"  WARNING: {sleeve_name} missing return column")
                continue
            
            df = df[['date', ret_col]].rename(columns={ret_col: f'{sleeve_name}_ret'})
            dfs[sleeve_name] = df
            
            # Store sleeve metadata with data availability info
            sleeve_info[sleeve_name] = {
                'type': sleeve_cfg.get('type', 'always_active'),
                'min_weight': sleeve_cfg.get('min_weight', 0.0),
                'max_weight': sleeve_cfg.get('max_weight', 1.0),
                'path': csv_path,
                'data_start': df['date'].min().strftime('%Y-%m-%d'),
                'data_end': df['date'].max().strftime('%Y-%m-%d'),
                'data_days': len(df)
            }
            
            print(f"  ✓ Loaded {sleeve_name}: {len(df)} days ({df['date'].min().date()} to {df['date'].max().date()})")
            
        except Exception as e:
            print(f"  ✗ Failed to load {sleeve_name}: {e}")
    
    if len(dfs) == 0:
        raise ValueError("No sleeves loaded!")
    
    # Merge all sleeves using OUTER join to preserve all dates
    # This allows sleeves with different start dates (e.g., VolCore from 2011)
    sleeve_names = list(dfs.keys())
    merged = dfs[sleeve_names[0]]
    
    for name in sleeve_names[1:]:
        merged = merged.merge(dfs[name], on='date', how='outer')
    
    # Sort by date
    merged = merged.sort_values('date').reset_index(drop=True)
    
    # Fill missing returns with 0 (sleeve inactive before data available)
    # This is economically correct: if VolCore data starts 2011, before that it's "not firing"
    for name in sleeve_names:
        ret_col = f'{name}_ret'
        missing_count = merged[ret_col].isna().sum()
        if missing_count > 0:
            merged[ret_col] = merged[ret_col].fillna(0.0)
            print(f"  ℹ️  {name}: {missing_count} days filled with 0 (before data start)")
    
    # Filter date range
    if start_date:
        merged = merged[merged['date'] >= pd.to_datetime(start_date)]
    if end_date:
        merged = merged[merged['date'] <= pd.to_datetime(end_date)]
    
    # Final check: ensure no NaNs remain
    nan_check = merged.isna().sum().sum()
    if nan_check > 0:
        print(f"  ⚠️  WARNING: {nan_check} NaN values remain in merged data")
    
    return merged, sleeve_info


def calculate_portfolio_metrics(returns_df: pd.DataFrame, weights: dict, sleeve_info: dict) -> dict:
    """Calculate portfolio metrics for given weights."""
    sleeve_names = list(weights.keys())
    ret_cols = [f'{name}_ret' for name in sleeve_names]
    
    returns = returns_df[ret_cols].values
    w = np.array([weights[name] for name in sleeve_names])
    
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
    
    # Individual sleeve metrics - ONLY using periods where sleeve has actual data
    sleeve_metrics = {}
    for i, name in enumerate(sleeve_names):
        sleeve_rets = returns[:, i]
        
        # For selective sleeves with late start dates, only calc metrics on active period
        # Identify non-zero return periods (zeros before data start don't count)
        data_start = pd.to_datetime(sleeve_info[name].get('data_start', '2000-01-01'))
        
        # Find rows where date >= data_start
        sleeve_start_idx = (returns_df['date'] >= data_start).idxmax() if (returns_df['date'] >= data_start).any() else 0
        
        # Use only the active period for this sleeve
        active_rets = sleeve_rets[sleeve_start_idx:]
        
        if len(active_rets) > 0:
            sleeve_mean = active_rets.mean() * 252
            sleeve_vol = active_rets.std() * np.sqrt(252)
            sleeve_sharpe = sleeve_mean / sleeve_vol if sleeve_vol > 0 else 0
        else:
            sleeve_sharpe = 0
            sleeve_mean = 0
            sleeve_vol = 0
        
        # Correlation with portfolio (use full period for fair comparison)
        if portfolio_rets.std() > 0 and sleeve_rets.std() > 0:
            corr = np.corrcoef(portfolio_rets, sleeve_rets)[0, 1]
        else:
            corr = 0.0
        
        sleeve_metrics[name] = {
            'sharpe': float(sleeve_sharpe),
            'annual_return': float(sleeve_mean),
            'annual_vol': float(sleeve_vol),
            'correlation_to_portfolio': float(corr)
        }
    
    return {
        'portfolio': {
            'sharpe': float(sharpe),
            'annual_return': float(mean_ret),
            'annual_vol': float(vol),
            'max_drawdown': float(max_dd)
        },
        'sleeves': sleeve_metrics
    }

def optimize_weights_max_sharpe(returns_df: pd.DataFrame, sleeve_info: dict, config: dict) -> dict:
    """
    Optimize weights to maximize Sharpe ratio with constraints.
    
    Constraints:
        - Weights sum to 1
        - Min/max per sleeve based on type
    """
    sleeve_names = list(sleeve_info.keys())
    n_sleeves = len(sleeve_names)
    
    ret_cols = [f'{name}_ret' for name in sleeve_names]
    returns = returns_df[ret_cols].values
    
    # Annualized mean and covariance
    mean_returns = returns.mean(axis=0) * 252
    cov_matrix = np.cov(returns.T) * 252
    
    def neg_sharpe(weights):
        """Negative Sharpe for minimization."""
        port_ret = weights @ mean_returns
        port_vol = np.sqrt(weights @ cov_matrix @ weights)
        return -port_ret / port_vol if port_vol > 0 else 0
    
    # Constraints: weights sum to 1
    constraints = [{'type': 'eq', 'fun': lambda w: w.sum() - 1}]
    
    # Constraint 2: Total selective weight <= selective_total_max
    portfolio_constraints = config.get('portfolio_constraints', {})
    selective_total_max = portfolio_constraints.get('selective_total_max', 1.0)
    
    selective_indices = [i for i, name in enumerate(sleeve_names) 
                        if sleeve_info[name]['type'] == 'selective']
    
    if selective_indices and selective_total_max < 1.0:
        def selective_cap(w):
            return selective_total_max - sum(w[i] for i in selective_indices)
        constraints.append({'type': 'ineq', 'fun': selective_cap})
        print(f"  ✓ Combined selective cap: {selective_total_max:.0%}")

    # Bounds: per-sleeve min/max
    bounds = []
    for name in sleeve_names:
        info = sleeve_info[name]
        bounds.append((info['min_weight'], info['max_weight']))
    
    # Initial guess: equal weight (respecting bounds)
    x0 = np.ones(n_sleeves) / n_sleeves
    
    # Adjust initial guess to respect bounds
    for i in range(n_sleeves):
        x0[i] = max(bounds[i][0], min(bounds[i][1], x0[i]))
    
    # Renormalize if needed
    if x0.sum() != 1.0:
        x0 = x0 / x0.sum()
    
    print(f"\n  Optimizing {n_sleeves} sleeves with constraints:")
    for i, name in enumerate(sleeve_names):
        print(f"    {name}: [{bounds[i][0]:.2f}, {bounds[i][1]:.2f}]")
    
    result = minimize(
        neg_sharpe, 
        x0, 
        method='SLSQP', 
        bounds=bounds, 
        constraints=constraints,
        options={'maxiter': 1000}
    )
    
    if not result.success:
        print(f"  ⚠️  Optimization warning: {result.message}")
    
    optimal_weights = {name: float(result.x[i]) for i, name in enumerate(sleeve_names)}
    optimal_sharpe = -result.fun
    
    print(f"\n  ✓ Optimization complete")
    print(f"    Maximum Sharpe: {optimal_sharpe:.4f}")
    
    return optimal_weights


def save_outputs(weights: dict, sleeve_info: dict, metrics: dict, 
                config: dict, args, output_dir: Path) -> tuple:
    """
    Save weights to YAML and CSV with timestamps.
    
    Returns:
        tuple: (yaml_path, csv_path)
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    # 1. Save YAML (machine-readable with full metadata)
    yaml_filename = f'vol_static_weights_{timestamp}.yaml'
    yaml_path = output_dir / yaml_filename
    
    yaml_content = {
        'optimization_metadata': {
            'date_generated': date_str,
            'timestamp': timestamp,
            'script_version': '2.0',
            'config_file': str(args.config),
            'is_start': args.start_date,
            'is_end': args.end_date,
            'objective': 'max_sharpe',
            'method': args.method
        },
        'constraints': {
            sleeve_name: {
                'type': info['type'],
                'min_weight': info['min_weight'],
                'max_weight': info['max_weight']
            }
            for sleeve_name, info in sleeve_info.items()
        },
        'data_availability': {
            sleeve_name: {
                'data_start': info.get('data_start', 'unknown'),
                'data_end': info.get('data_end', 'unknown'),
                'data_days': info.get('data_days', 0)
            }
            for sleeve_name, info in sleeve_info.items()
        },
        'optimal_weights': weights,
        'performance_at_optimization': metrics['portfolio'],
        'sleeve_contributions': {
            name: {
                'weight': weights[name],
                'individual_sharpe': metrics['sleeves'][name]['sharpe'],
                'correlation_to_portfolio': metrics['sleeves'][name]['correlation_to_portfolio']
            }
            for name in weights.keys()
        }
    }
    
    with open(yaml_path, 'w') as f:
        yaml.dump(yaml_content, f, default_flow_style=False, sort_keys=False)
    
    # 2. Save CSV (human-readable for verification)
    csv_filename = f'vol_static_weights_{timestamp}.csv'
    csv_path = output_dir / csv_filename
    
    csv_rows = []
    for name in weights.keys():
        csv_rows.append({
            'sleeve': name,
            'weight': weights[name],
            'weight_pct': weights[name] * 100,
            'type': sleeve_info[name]['type'],
            'min_weight': sleeve_info[name]['min_weight'],
            'max_weight': sleeve_info[name]['max_weight'],
            'data_start': sleeve_info[name].get('data_start', 'unknown'),
            'data_end': sleeve_info[name].get('data_end', 'unknown'),
            'individual_sharpe': metrics['sleeves'][name]['sharpe'],
            'correlation_to_portfolio': metrics['sleeves'][name]['correlation_to_portfolio']
        })
    
    csv_df = pd.DataFrame(csv_rows)
    csv_df.to_csv(csv_path, index=False)
    
    # 3. Also save "latest" symlinks for easy access
    latest_yaml = output_dir / 'vol_static_weights_latest.yaml'
    latest_csv = output_dir / 'vol_static_weights_latest.csv'
    
    # Copy content to latest (Windows-friendly, no symlinks)
    with open(latest_yaml, 'w') as f:
        yaml.dump(yaml_content, f, default_flow_style=False, sort_keys=False)
    csv_df.to_csv(latest_csv, index=False)
    
    return yaml_path, csv_path


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Calculate optimal static weights for N sleeves from config"
    )
    
    parser.add_argument(
        '--config',
        required=True,
        help='Path to portfolio configuration YAML'
    )
    
    parser.add_argument(
        '--outdir',
        default='outputs/Copper/VolStatic',
        help='Output directory for weights files'
    )
    
    parser.add_argument(
        '--method',
        default='max_sharpe',
        choices=['max_sharpe'],
        help='Weight optimization method (currently only max_sharpe)'
    )
    
    parser.add_argument(
        '--start-date',
        default='2003-01-01',
        help='Optimization start date (IS period)'
    )
    
    parser.add_argument(
        '--end-date',
        default='2018-12-31',
        help='Optimization end date (IS period)'
    )
    
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Print header
    print("\n" + "=" * 80)
    print("STATIC VOL WEIGHTS BUILDER v2.0")
    print("=" * 80)
    print(f"Config:      {args.config}")
    print(f"Method:      {args.method}")
    print(f"IS Period:   {args.start_date} to {args.end_date}")
    print(f"Output:      {args.outdir}")
    print(f"Timestamp:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Step 1: Load configuration
        print("\n📋 Loading configuration...")
        config = load_config(args.config)
        
        commodity = config.get('io', {}).get('commodity', 'Unknown')
        print(f"  Commodity: {commodity}")
        
        # Step 2: Load sleeve data
        print("\n📂 Loading sleeve returns...")
        returns_df, sleeve_info = load_sleeve_returns(
            config, 
            start_date=args.start_date, 
            end_date=args.end_date
        )
        
        print(f"\n  ✓ Loaded {len(sleeve_info)} sleeve(s)")
        print(f"  ✓ {len(returns_df)} common trading days")
        print(f"  ✓ Date range: {returns_df['date'].min().date()} to {returns_df['date'].max().date()}")
        
        # Step 3: Optimize weights
        print(f"\n⚖️  Optimizing weights ({args.method})...")
        
        if args.method == 'max_sharpe':
            weights = optimize_weights_max_sharpe(returns_df, sleeve_info, config)

        print(f"\n  Optimal weights:")
        for name, weight in weights.items():
            print(f"    {name:20s}: {weight:.4f} ({weight*100:.2f}%)")
        
        weight_sum = sum(weights.values())
        print(f"  Weight sum: {weight_sum:.6f}")
        
        # Step 4: Calculate metrics
        print(f"\n📈 Calculating portfolio metrics...")
        metrics = calculate_portfolio_metrics(returns_df, weights, sleeve_info)
        
        print(f"  Portfolio Sharpe:  {metrics['portfolio']['sharpe']:.4f}")
        print(f"  Annual Return:     {metrics['portfolio']['annual_return']*100:.2f}%")
        print(f"  Annual Vol:        {metrics['portfolio']['annual_vol']*100:.2f}%")
        print(f"  Max Drawdown:      {metrics['portfolio']['max_drawdown']*100:.2f}%")
        
        print(f"\n  Sleeve contributions:")
        for name in weights.keys():
            s = metrics['sleeves'][name]
            print(f"    {name:20s}: Sharpe={s['sharpe']:.3f}, Corr={s['correlation_to_portfolio']:.3f}")
        
        # Step 5: Save outputs
        print(f"\n💾 Saving outputs to {args.outdir}...")
        output_dir = Path(args.outdir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        yaml_path, csv_path = save_outputs(
            weights, sleeve_info, metrics, config, args, output_dir
        )
        
        print(f"  ✓ Saved {yaml_path.name}")
        print(f"  ✓ Saved {csv_path.name}")
        print(f"  ✓ Saved vol_static_weights_latest.yaml")
        print(f"  ✓ Saved vol_static_weights_latest.csv")
        
        # Final summary
        print("\n" + "=" * 80)
        print("BUILD COMPLETE")
        print("=" * 80)
        print(f"✅ Optimized {len(weights)} sleeves")
        print(f"✅ Portfolio Sharpe: {metrics['portfolio']['sharpe']:.4f}")
        print(f"✅ IS Period: {args.start_date} to {args.end_date}")
        print(f"\nOutput files:")
        print(f"  {yaml_path}")
        print(f"  {csv_path}")
        print(f"\nFor portfolio builder, use:")
        print(f"  vol_static_weights_latest.yaml")
        print("=" * 80)
        
        return 0
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)