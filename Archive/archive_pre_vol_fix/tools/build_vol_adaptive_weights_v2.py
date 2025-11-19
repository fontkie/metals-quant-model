#!/usr/bin/env python3
"""
Build Adaptive Vol Weights v2
==============================

Config-driven optimizer for N sleeves with PER-REGIME optimization.
Uses 3x1 IV percentile classification (Low/Med/High volatility only).

Key features:
  - Reads sleeves from config YAML (not hardcoded)
  - Classifies days by IV percentile regime (3 regimes)
  - Optimizes weights independently per regime
  - Same constraints apply within each regime
  - No forward bias (rolling lookback for percentiles)
  - Outputs regime-indexed weight matrix

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


def load_iv_data(iv_path: str) -> pd.DataFrame:
    """
    Load implied volatility data.
    
    Expected format: date, iv
    """
    df = pd.read_csv(iv_path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    
    print(f"  ✓ Loaded IV data: {len(df)} days ({df['date'].min().date()} to {df['date'].max().date()})")
    
    return df


def classify_iv_regimes(iv_df: pd.DataFrame, lookback: int = 252, 
                        low_pct: float = 0.33, high_pct: float = 0.67,
                        regime_lag: int = 1) -> pd.DataFrame:
    """
    Classify days into IV regimes using rolling percentile.
    
    Uses EXPANDING window initially, then rolling lookback.
    No forward bias - percentile calculated on historical data only.
    
    PUBLICATION TIMING:
        regime_lag = 1 (default): Use T-1's regime for T's weights (conservative)
        regime_lag = 0: Use T's regime for T's weights (assumes same-day execution)
        
        *** TO TEST T vs T-1: Change regime_lag parameter ***
    
    Regimes:
        LOW:    IV percentile <= low_pct (e.g., bottom 33%)
        MEDIUM: low_pct < IV percentile <= high_pct
        HIGH:   IV percentile > high_pct (e.g., top 33%)
    
    Args:
        iv_df: DataFrame with 'date' and 'iv' columns
        lookback: Rolling window size for percentile calculation
        low_pct: Percentile threshold for LOW regime (default 0.33)
        high_pct: Percentile threshold for HIGH regime (default 0.67)
        regime_lag: Days to lag regime classification (default 1 for T-1)
    
    Returns:
        DataFrame with added 'iv_percentile' and 'vol_regime' columns
    """
    df = iv_df.copy()
    
    # Calculate rolling percentile (no forward bias)
    # Use expanding window until we have enough history, then rolling
    iv_pct = []
    
    for i in range(len(df)):
        if i < 20:  # Minimum history requirement
            iv_pct.append(np.nan)
        else:
            # Use min(lookback, available history) for expanding start
            window_size = min(lookback, i + 1)
            historical_iv = df['iv'].iloc[max(0, i + 1 - window_size):i + 1]
            current_iv = df['iv'].iloc[i]
            
            # Percentile: what fraction of historical values are <= current
            pct = (historical_iv <= current_iv).sum() / len(historical_iv)
            iv_pct.append(pct)
    
    df['iv_percentile'] = iv_pct
    
    # Classify regime
    def classify_regime(pct):
        if pd.isna(pct):
            return np.nan
        elif pct <= low_pct:
            return 'LOW'
        elif pct <= high_pct:
            return 'MEDIUM'
        else:
            return 'HIGH'
    
    df['vol_regime'] = df['iv_percentile'].apply(classify_regime)
    
    # Apply regime lag (T-1 conservative approach)
    # This means: use yesterday's regime classification for today's weights
    if regime_lag > 0:
        df['vol_regime'] = df['vol_regime'].shift(regime_lag)
        df['iv_percentile'] = df['iv_percentile'].shift(regime_lag)
        print(f"\n  ⏰ Regime lag: T-{regime_lag} (using {regime_lag}-day lagged classification)")
    else:
        print(f"\n  ⏰ Regime lag: T (same-day classification)")
    
    # Summary statistics
    regime_counts = df['vol_regime'].value_counts()
    print(f"\n  Regime distribution (full period):")
    for regime in ['LOW', 'MEDIUM', 'HIGH']:
        if regime in regime_counts:
            count = regime_counts[regime]
            pct = count / len(df) * 100
            print(f"    {regime:8s}: {count:6d} days ({pct:5.1f}%)")
    
    return df


def load_sleeve_returns(config: dict, start_date: str = None, end_date: str = None) -> tuple:
    """
    Load sleeve returns from config-specified paths.
    
    Handles sleeves with different start dates by using OUTER join and 
    filling missing returns with 0 (sleeve inactive before data starts).
    
    Returns:
        tuple: (returns_df, sleeve_info)
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
            
            # Get return column
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
    
    # Merge all sleeves using OUTER join
    sleeve_names = list(dfs.keys())
    merged = dfs[sleeve_names[0]]
    
    for name in sleeve_names[1:]:
        merged = merged.merge(dfs[name], on='date', how='outer')
    
    merged = merged.sort_values('date').reset_index(drop=True)
    
    # Fill missing returns with 0
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
    
    return merged, sleeve_info


def optimize_weights_for_regime(returns_df: pd.DataFrame, sleeve_info: dict, 
                                 config: dict, regime_name: str) -> dict:
    """
    Optimize weights for a single regime.
    
    Same constraint structure as static optimizer:
      - Weights sum to 1
      - Min/max per sleeve based on type
      - Combined selective cap
    """
    sleeve_names = list(sleeve_info.keys())
    n_sleeves = len(sleeve_names)
    
    if len(returns_df) < 50:  # Minimum days for reliable optimization
        print(f"    ⚠️  {regime_name}: Only {len(returns_df)} days, using equal weights")
        # Return equal weights respecting constraints
        weights = {}
        for name in sleeve_names:
            min_w = sleeve_info[name]['min_weight']
            max_w = sleeve_info[name]['max_weight']
            weights[name] = (min_w + max_w) / 2
        
        # Normalize to sum to 1
        total = sum(weights.values())
        weights = {k: v / total for k, v in weights.items()}
        return weights
    
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
    
    # Combined selective cap constraint
    portfolio_constraints = config.get('portfolio_constraints', {})
    selective_total_max = portfolio_constraints.get('selective_total_max', 1.0)
    
    selective_indices = [i for i, name in enumerate(sleeve_names) 
                        if sleeve_info[name]['type'] == 'selective']
    
    if selective_indices and selective_total_max < 1.0:
        def selective_cap(w):
            return selective_total_max - sum(w[i] for i in selective_indices)
        constraints.append({'type': 'ineq', 'fun': selective_cap})
    
    # Bounds: per-sleeve min/max
    bounds = []
    for name in sleeve_names:
        info = sleeve_info[name]
        bounds.append((info['min_weight'], info['max_weight']))
    
    # Initial guess: equal weight (respecting bounds)
    x0 = np.ones(n_sleeves) / n_sleeves
    
    # Adjust to respect bounds
    for i in range(n_sleeves):
        x0[i] = max(bounds[i][0], min(bounds[i][1], x0[i]))
    
    # Renormalize
    if x0.sum() != 1.0:
        x0 = x0 / x0.sum()
    
    result = minimize(
        neg_sharpe, 
        x0, 
        method='SLSQP', 
        bounds=bounds, 
        constraints=constraints,
        options={'maxiter': 1000}
    )
    
    if not result.success:
        print(f"    ⚠️  {regime_name} optimization warning: {result.message}")
    
    optimal_weights = {name: float(result.x[i]) for i, name in enumerate(sleeve_names)}
    optimal_sharpe = -result.fun
    
    return optimal_weights


def calculate_regime_metrics(returns_df: pd.DataFrame, weights: dict, regime_name: str) -> dict:
    """Calculate performance metrics for a single regime."""
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
    
    return {
        'sharpe': float(sharpe),
        'annual_return': float(mean_ret),
        'annual_vol': float(vol),
        'max_drawdown': float(max_dd),
        'days': len(returns_df)
    }


def optimize_all_regimes(returns_df: pd.DataFrame, regime_df: pd.DataFrame,
                          sleeve_info: dict, config: dict) -> dict:
    """
    Optimize weights for each regime independently.
    
    Returns:
        dict: {regime_name: {sleeve: weight}}
    """
    # Merge returns with regime classification
    merged = returns_df.merge(regime_df[['date', 'vol_regime']], on='date', how='inner')
    
    print(f"\n  Data with regime labels: {len(merged)} days")
    
    # Filter to valid regime classifications only
    merged = merged[merged['vol_regime'].notna()].copy()
    print(f"  Valid regime classifications: {len(merged)} days")
    
    regime_weights = {}
    regime_metrics = {}
    
    regimes = ['LOW', 'MEDIUM', 'HIGH']
    
    for regime in regimes:
        regime_data = merged[merged['vol_regime'] == regime].copy()
        n_days = len(regime_data)
        
        print(f"\n  📊 Optimizing {regime} regime ({n_days} days)...")
        
        if n_days == 0:
            print(f"    ⚠️  No data for {regime} regime, skipping")
            continue
        
        # Optimize weights for this regime
        weights = optimize_weights_for_regime(regime_data, sleeve_info, config, regime)
        regime_weights[regime] = weights
        
        # Calculate metrics
        metrics = calculate_regime_metrics(regime_data, weights, regime)
        regime_metrics[regime] = metrics
        
        # Display results
        print(f"    Optimal weights:")
        for name, weight in weights.items():
            print(f"      {name:20s}: {weight:.4f} ({weight*100:.2f}%)")
        print(f"    Portfolio Sharpe: {metrics['sharpe']:.4f}")
        print(f"    Annual Return:    {metrics['annual_return']*100:.2f}%")
        print(f"    Annual Vol:       {metrics['annual_vol']*100:.2f}%")
    
    return regime_weights, regime_metrics, merged


def save_outputs(regime_weights: dict, regime_metrics: dict, sleeve_info: dict,
                 config: dict, args, output_dir: Path, regime_df: pd.DataFrame) -> tuple:
    """
    Save regime-specific weights to YAML and CSV.
    
    Returns:
        tuple: (yaml_path, csv_path)
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    # 1. Save YAML (machine-readable)
    yaml_filename = f'vol_adaptive_weights_{timestamp}.yaml'
    yaml_path = output_dir / yaml_filename
    
    yaml_content = {
        'optimization_metadata': {
            'date_generated': date_str,
            'timestamp': timestamp,
            'script_version': '2.0',
            'config_file': str(args.config),
            'iv_file': str(args.iv_file),
            'is_start': args.start_date,
            'is_end': args.end_date,
            'objective': 'max_sharpe_per_regime',
            'regime_type': '3x1_iv_percentile',
            'lookback': args.lookback,
            'low_percentile': args.low_pct,
            'high_percentile': args.high_pct,
            'regime_lag': args.regime_lag,
            'regime_lag_note': f'T-{args.regime_lag} classification ({"conservative - uses prior day IV" if args.regime_lag == 1 else "same-day IV" if args.regime_lag == 0 else f"{args.regime_lag}-day lag"})'
        },
        'constraints': {
            sleeve_name: {
                'type': info['type'],
                'min_weight': info['min_weight'],
                'max_weight': info['max_weight']
            }
            for sleeve_name, info in sleeve_info.items()
        },
        'regime_weights': regime_weights,
        'regime_performance': regime_metrics
    }
    
    with open(yaml_path, 'w') as f:
        yaml.dump(yaml_content, f, default_flow_style=False, sort_keys=False)
    
    # 2. Save CSV (human-readable, flat format for verification)
    csv_filename = f'vol_adaptive_weights_{timestamp}.csv'
    csv_path = output_dir / csv_filename
    
    csv_rows = []
    for regime in ['LOW', 'MEDIUM', 'HIGH']:
        if regime in regime_weights:
            for sleeve_name in sleeve_info.keys():
                weight = regime_weights[regime].get(sleeve_name, 0.0)
                csv_rows.append({
                    'regime': regime,
                    'sleeve': sleeve_name,
                    'weight': weight,
                    'weight_pct': weight * 100,
                    'type': sleeve_info[sleeve_name]['type'],
                    'min_weight': sleeve_info[sleeve_name]['min_weight'],
                    'max_weight': sleeve_info[sleeve_name]['max_weight'],
                    'regime_days': regime_metrics[regime]['days'],
                    'regime_sharpe': regime_metrics[regime]['sharpe'],
                    'regime_return': regime_metrics[regime]['annual_return'],
                    'regime_vol': regime_metrics[regime]['annual_vol']
                })
    
    csv_df = pd.DataFrame(csv_rows)
    csv_df.to_csv(csv_path, index=False)
    
    # 3. Save "latest" versions
    latest_yaml = output_dir / 'vol_adaptive_weights_latest.yaml'
    latest_csv = output_dir / 'vol_adaptive_weights_latest.csv'
    
    with open(latest_yaml, 'w') as f:
        yaml.dump(yaml_content, f, default_flow_style=False, sort_keys=False)
    csv_df.to_csv(latest_csv, index=False)
    
    return yaml_path, csv_path


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Calculate optimal weights per IV regime for N sleeves"
    )
    
    parser.add_argument(
        '--config',
        required=True,
        help='Path to portfolio configuration YAML'
    )
    
    parser.add_argument(
        '--iv-file',
        required=True,
        help='Path to implied volatility CSV (date, iv columns)'
    )
    
    parser.add_argument(
        '--outdir',
        default='outputs/Copper/VolAdaptive',
        help='Output directory for weights files'
    )
    
    parser.add_argument(
        '--start-date',
        default='2011-07-01',  # Start after IV data stabilizes
        help='Optimization start date (IS period)'
    )
    
    parser.add_argument(
        '--end-date',
        default='2018-12-31',
        help='Optimization end date (IS period)'
    )
    
    parser.add_argument(
        '--lookback',
        type=int,
        default=252,
        help='Rolling window for IV percentile calculation (default: 252 days)'
    )
    
    parser.add_argument(
        '--low-pct',
        type=float,
        default=0.33,
        help='Percentile threshold for LOW regime (default: 0.33)'
    )
    
    parser.add_argument(
        '--high-pct',
        type=float,
        default=0.67,
        help='Percentile threshold for HIGH regime (default: 0.67)'
    )
    
    parser.add_argument(
        '--regime-lag',
        type=int,
        default=1,
        help='Days to lag regime classification. 1=T-1 (conservative), 0=T (same-day). Default: 1'
    )
    
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Print header
    print("\n" + "=" * 80)
    print("ADAPTIVE VOL WEIGHTS BUILDER v2.0")
    print("=" * 80)
    print(f"Config:      {args.config}")
    print(f"IV File:     {args.iv_file}")
    print(f"IS Period:   {args.start_date} to {args.end_date}")
    print(f"Lookback:    {args.lookback} days")
    print(f"Regime Thresholds: LOW <= {args.low_pct:.0%}, HIGH > {args.high_pct:.0%}")
    print(f"Regime Lag:  T-{args.regime_lag} ({'T-1 conservative' if args.regime_lag == 1 else 'same-day' if args.regime_lag == 0 else f'{args.regime_lag}-day lag'})")
    print(f"Output:      {args.outdir}")
    print(f"Timestamp:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Step 1: Load configuration
        print("\n📋 Loading configuration...")
        config = load_config(args.config)
        
        commodity = config.get('io', {}).get('commodity', 'Unknown')
        print(f"  Commodity: {commodity}")
        
        # Step 2: Load IV data
        print("\n📈 Loading implied volatility data...")
        iv_df = load_iv_data(args.iv_file)
        
        # Step 3: Classify regimes
        print("\n🏷️  Classifying IV regimes...")
        regime_df = classify_iv_regimes(
            iv_df, 
            lookback=args.lookback,
            low_pct=args.low_pct,
            high_pct=args.high_pct,
            regime_lag=args.regime_lag
        )
        
        # Step 4: Load sleeve data
        print("\n📂 Loading sleeve returns...")
        returns_df, sleeve_info = load_sleeve_returns(
            config, 
            start_date=args.start_date, 
            end_date=args.end_date
        )
        
        print(f"\n  ✓ Loaded {len(sleeve_info)} sleeve(s)")
        print(f"  ✓ {len(returns_df)} trading days")
        print(f"  ✓ Date range: {returns_df['date'].min().date()} to {returns_df['date'].max().date()}")
        
        # Step 5: Optimize per regime
        print("\n⚖️  Optimizing weights per regime...")
        regime_weights, regime_metrics, merged_data = optimize_all_regimes(
            returns_df, regime_df, sleeve_info, config
        )
        
        # Step 6: Calculate overall statistics
        print("\n📊 Overall Statistics:")
        total_days = sum(m['days'] for m in regime_metrics.values())
        weighted_sharpe = sum(
            regime_metrics[r]['sharpe'] * regime_metrics[r]['days'] / total_days
            for r in regime_metrics
        )
        print(f"  Total optimized days: {total_days}")
        print(f"  Weighted average Sharpe: {weighted_sharpe:.4f}")
        
        # Show regime time distribution
        print(f"\n  Regime time distribution (IS period):")
        for regime in ['LOW', 'MEDIUM', 'HIGH']:
            if regime in regime_metrics:
                days = regime_metrics[regime]['days']
                pct = days / total_days * 100
                sharpe = regime_metrics[regime]['sharpe']
                print(f"    {regime:8s}: {days:6d} days ({pct:5.1f}%) | Sharpe: {sharpe:.4f}")
        
        # Step 7: Save outputs
        print(f"\n💾 Saving outputs to {args.outdir}...")
        output_dir = Path(args.outdir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        yaml_path, csv_path = save_outputs(
            regime_weights, regime_metrics, sleeve_info, config, args, output_dir, regime_df
        )
        
        print(f"  ✓ Saved {yaml_path.name}")
        print(f"  ✓ Saved {csv_path.name}")
        print(f"  ✓ Saved vol_adaptive_weights_latest.yaml")
        print(f"  ✓ Saved vol_adaptive_weights_latest.csv")
        
        # Final summary
        print("\n" + "=" * 80)
        print("BUILD COMPLETE")
        print("=" * 80)
        print(f"✅ Optimized {len(sleeve_info)} sleeves across {len(regime_weights)} regimes")
        print(f"✅ Weighted Avg Sharpe: {weighted_sharpe:.4f}")
        print(f"✅ IS Period: {args.start_date} to {args.end_date}")
        print(f"\nOutput files:")
        print(f"  {yaml_path}")
        print(f"  {csv_path}")
        print(f"\nFor portfolio builder, use:")
        print(f"  vol_adaptive_weights_latest.yaml")
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