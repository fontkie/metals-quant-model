#!/usr/bin/env python3
"""
Build Static Portfolio v2
==========================

Applies static weights from YAML with proper portfolio-level costs.
Handles N sleeves from config (not hardcoded).

Key improvements over v1:
  - Reads weights from YAML (with metadata) instead of CSV
  - Handles N sleeves from config
  - Validates weights match config
  - Timestamps on outputs
  - IS/OOS split metrics

Author: Claude (ex-Renaissance) + Kieran
Date: November 17, 2025
Version: 2.0
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np
import yaml


def load_config(config_path: str) -> dict:
    """Load portfolio configuration YAML."""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config


def load_static_weights(weights_yaml_path: str) -> dict:
    """
    Load static weights from YAML.
    
    Returns:
        tuple: (weights_dict, metadata_dict)
    """
    with open(weights_yaml_path, 'r') as f:
        weights_data = yaml.safe_load(f)
    
    weights = weights_data.get('optimal_weights', {})
    metadata = weights_data.get('optimization_metadata', {})
    
    return weights, metadata


def load_sleeves(config: dict) -> dict:
    """
    Load sleeve data with pos and pnl_gross columns.
    
    Returns:
        dict: {sleeve_name: DataFrame with columns [date, pos, pnl_gross]}
    """
    sleeves = {}
    sleeves_cfg = config.get('sleeves', {})
    
    for sleeve_name, sleeve_cfg in sleeves_cfg.items():
        if not sleeve_cfg.get('enabled', True):
            print(f"  Skipping {sleeve_name} (disabled)")
            continue
        
        csv_path = sleeve_cfg.get('path')
        if not csv_path:
            print(f"  WARNING: No path for {sleeve_name}")
            continue
        
        if not Path(csv_path).exists():
            print(f"  ⚠️  File not found for {sleeve_name}: {csv_path}")
            continue
        
        try:
            df = pd.read_csv(csv_path)
            df['date'] = pd.to_datetime(df['date'])
            
            # Validate required columns
            required = ['date', 'pos', 'pnl_gross']
            missing = [col for col in required if col not in df.columns]
            if missing:
                print(f"  ⚠️  {sleeve_name} missing columns: {missing}")
                continue
            
            sleeves[sleeve_name] = df[['date', 'pos', 'pnl_gross']]
            print(f"  ✓ Loaded {sleeve_name}: {len(df)} days")
            
        except Exception as e:
            print(f"  ✗ Failed to load {sleeve_name}: {e}")
    
    return sleeves


def merge_sleeves(sleeves: dict) -> pd.DataFrame:
    """
    Merge sleeves on dates using OUTER join.
    
    Handles sleeves with different start dates by filling missing pos/pnl_gross with 0.
    This is economically correct: missing = sleeve not active yet.
    
    Returns:
        DataFrame with columns: date, [sleeve]_pos, [sleeve]_pnl_gross
    """
    sleeve_names = list(sleeves.keys())
    
    # Start with first sleeve
    merged = sleeves[sleeve_names[0]][['date']].copy()
    merged = sleeves[sleeve_names[0]][['date', 'pos', 'pnl_gross']].rename(columns={
        'pos': f'{sleeve_names[0]}_pos',
        'pnl_gross': f'{sleeve_names[0]}_pnl_gross'
    })
    
    # Add remaining sleeves using OUTER join
    for sleeve_name in sleeve_names[1:]:
        sleeve_data = sleeves[sleeve_name][['date', 'pos', 'pnl_gross']].rename(columns={
            'pos': f'{sleeve_name}_pos',
            'pnl_gross': f'{sleeve_name}_pnl_gross'
        })
        merged = merged.merge(sleeve_data, on='date', how='outer')
    
    # Sort by date
    merged = merged.sort_values('date').reset_index(drop=True)
    
    # Fill missing pos and pnl_gross with 0 (sleeve inactive before data starts)
    for sleeve_name in sleeve_names:
        pos_col = f'{sleeve_name}_pos'
        pnl_col = f'{sleeve_name}_pnl_gross'
        
        missing_pos = merged[pos_col].isna().sum()
        missing_pnl = merged[pnl_col].isna().sum()
        
        if missing_pos > 0 or missing_pnl > 0:
            merged[pos_col] = merged[pos_col].fillna(0.0)
            merged[pnl_col] = merged[pnl_col].fillna(0.0)
            print(f"  ℹ️  {sleeve_name}: {missing_pos} days filled with 0 (before data start)")
    
    return merged


def build_static_portfolio(merged: pd.DataFrame, weights: dict, cost_bp: float) -> pd.DataFrame:
    """
    Build static portfolio with proper portfolio-level costs.
    """
    sleeve_names = list(weights.keys())
    
    # Add constant weights
    for sleeve_name, weight in weights.items():
        merged[f'{sleeve_name}_weight'] = weight
    
    # Calculate portfolio position and PnL
    print("💼 Calculating portfolio position and costs...")
    
    cost_decimal = cost_bp / 10000.0
    
    portfolio_pos = np.zeros(len(merged))
    portfolio_trade = np.zeros(len(merged))
    portfolio_pnl_gross = np.zeros(len(merged))
    portfolio_cost = np.zeros(len(merged))
    
    for i in range(len(merged)):
        pos = 0.0
        pnl_gross = 0.0
        
        for sleeve_name in sleeve_names:
            sleeve_pos = merged.iloc[i][f'{sleeve_name}_pos']
            sleeve_weight = weights[sleeve_name]
            sleeve_pnl_gross = merged.iloc[i][f'{sleeve_name}_pnl_gross']
            
            if pd.notna(sleeve_pos):
                pos += sleeve_pos * sleeve_weight
            
            pnl_gross += sleeve_pnl_gross * sleeve_weight
        
        portfolio_pos[i] = pos
        portfolio_pnl_gross[i] = pnl_gross
        
        if i > 0:
            trade = portfolio_pos[i] - portfolio_pos[i-1]
            portfolio_trade[i] = trade
            
            if trade != 0:
                portfolio_cost[i] = abs(trade) * cost_decimal
    
    portfolio_pnl_net = portfolio_pnl_gross - portfolio_cost
    
    merged['portfolio_pos'] = portfolio_pos
    merged['portfolio_trade'] = portfolio_trade
    merged['portfolio_pnl_gross'] = portfolio_pnl_gross
    merged['portfolio_cost'] = portfolio_cost
    merged['portfolio_pnl_net'] = portfolio_pnl_net
    
    return merged


def calculate_metrics(daily_series: pd.DataFrame, split_date: str = '2019-01-01') -> dict:
    """Calculate portfolio performance metrics with IS/OOS split."""
    
    def calc_period_metrics(returns, costs, label):
        """Calculate metrics for a specific period."""
        if len(returns) == 0:
            return {}
        
        mean_ret = returns.mean() * 252
        vol = returns.std() * np.sqrt(252)
        sharpe = mean_ret / vol if vol > 0 else 0.0
        
        cumulative = (1 + returns).cumprod()
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - running_max) / running_max
        max_dd = drawdowns.min()
        
        calmar = abs(mean_ret / max_dd) if max_dd < 0 else 0.0
        
        total_costs = costs.sum()
        cost_drag_bps = (total_costs / len(returns)) * 252 * 10000 if len(returns) > 0 else 0
        
        return {
            'sharpe': float(sharpe),
            'annual_return': float(mean_ret),
            'annual_vol': float(vol),
            'max_drawdown': float(max_dd),
            'calmar': float(calmar),
            'cost_drag_bps': float(cost_drag_bps),
            'obs': len(returns)
        }
    
    # Full period
    full_returns = daily_series['portfolio_pnl_net'].values
    full_costs = daily_series['portfolio_cost'].values
    full_metrics = calc_period_metrics(full_returns, full_costs, 'Full')
    full_metrics['start_date'] = daily_series['date'].min().strftime('%Y-%m-%d')
    full_metrics['end_date'] = daily_series['date'].max().strftime('%Y-%m-%d')
    
    # IS/OOS split
    split_dt = pd.to_datetime(split_date)
    is_mask = daily_series['date'] < split_dt
    oos_mask = daily_series['date'] >= split_dt
    
    is_returns = daily_series.loc[is_mask, 'portfolio_pnl_net'].values
    is_costs = daily_series.loc[is_mask, 'portfolio_cost'].values
    is_metrics = calc_period_metrics(is_returns, is_costs, 'IS')
    
    oos_returns = daily_series.loc[oos_mask, 'portfolio_pnl_net'].values
    oos_costs = daily_series.loc[oos_mask, 'portfolio_cost'].values
    oos_metrics = calc_period_metrics(oos_returns, oos_costs, 'OOS')
    
    return {
        'full': full_metrics,
        'is': is_metrics,
        'oos': oos_metrics,
        'split_date': split_date
    }


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Build static portfolio with proper portfolio-level costs"
    )
    
    parser.add_argument(
        '--config',
        required=True,
        help='Path to portfolio configuration YAML'
    )
    
    parser.add_argument(
        '--weights',
        default=None,
        help='Path to weights YAML (default: latest in outdir)'
    )
    
    parser.add_argument(
        '--outdir',
        default='outputs/Copper/VolStatic',
        help='Output directory for results'
    )
    
    parser.add_argument(
        '--split-date',
        default='2019-01-01',
        help='IS/OOS split date'
    )
    
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Default weights path to latest
    if args.weights is None:
        args.weights = str(Path(args.outdir) / 'vol_static_weights_latest.yaml')
    
    # Print header
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    print("\n" + "=" * 80)
    print("STATIC PORTFOLIO BUILDER v2.0")
    print("=" * 80)
    print(f"Config:     {args.config}")
    print(f"Weights:    {args.weights}")
    print(f"Output:     {args.outdir}")
    print(f"Split Date: {args.split_date}")
    print(f"Timestamp:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Step 1: Load configuration
        print("\n📋 Loading configuration...")
        config = load_config(args.config)
        
        commodity = config.get('io', {}).get('commodity', 'Unknown')
        cost_bp = config.get('costs', {}).get('transaction_cost_bp', 3)
        
        print(f"  Commodity: {commodity}")
        print(f"  Transaction cost: {cost_bp} bps")
        
        # Step 2: Load static weights from YAML
        print(f"\n⚖️  Loading static weights...")
        weights, weights_metadata = load_static_weights(args.weights)
        
        print(f"  Weights optimized on: {weights_metadata.get('is_start', '?')} to {weights_metadata.get('is_end', '?')}")
        print(f"  Weights generated: {weights_metadata.get('date_generated', '?')}")
        
        print("\n  Static weights:")
        for name, weight in weights.items():
            print(f"    {name:20s}: {weight:.4f} ({weight*100:.2f}%)")
        
        weight_sum = sum(weights.values())
        print(f"  Weight sum: {weight_sum:.6f}")
        if abs(weight_sum - 1.0) > 0.001:
            print(f"  ⚠️  WARNING: Weights do not sum to 1.0!")
        
        # Step 3: Load sleeves
        print("\n📂 Loading sleeves...")
        sleeves = load_sleeves(config)
        
        if len(sleeves) == 0:
            print("  ❌ No sleeves loaded!")
            return 1
        
        # Validate weights match sleeves
        config_sleeves = set(sleeves.keys())
        weight_sleeves = set(weights.keys())
        
        if config_sleeves != weight_sleeves:
            missing_in_weights = config_sleeves - weight_sleeves
            missing_in_config = weight_sleeves - config_sleeves
            
            if missing_in_weights:
                print(f"  ⚠️  Sleeves in config but not in weights: {missing_in_weights}")
            if missing_in_config:
                print(f"  ⚠️  Sleeves in weights but not in config: {missing_in_config}")
            
            # Use intersection
            common_sleeves = config_sleeves & weight_sleeves
            print(f"  Using {len(common_sleeves)} common sleeves: {common_sleeves}")
            
            # Filter weights to common
            weights = {k: v for k, v in weights.items() if k in common_sleeves}
            sleeves = {k: v for k, v in sleeves.items() if k in common_sleeves}
            
            # Renormalize weights
            weight_sum = sum(weights.values())
            weights = {k: v/weight_sum for k, v in weights.items()}
            print(f"  Renormalized weights to sum to 1.0")
        
        print(f"\n  ✓ Loaded {len(sleeves)} sleeve(s)")
        
        # Step 4: Merge sleeves
        print("\n🔗 Merging sleeves on common dates...")
        merged = merge_sleeves(sleeves)
        print(f"  ✓ Merged to {len(merged)} common trading days")
        print(f"  ✓ Date range: {merged['date'].min().date()} to {merged['date'].max().date()}")
        
        # Step 5: Build static portfolio
        print("\n🚀 Building static portfolio...")
        daily_series = build_static_portfolio(merged, weights, cost_bp)
        
        # Step 6: Calculate metrics
        print("\n📈 Calculating performance metrics...")
        metrics = calculate_metrics(daily_series, split_date=args.split_date)
        
        print(f"\n  FULL PERIOD ({metrics['full']['start_date']} to {metrics['full']['end_date']}):")
        print(f"    Sharpe:     {metrics['full']['sharpe']:.4f}")
        print(f"    Return:     {metrics['full']['annual_return']*100:.2f}%")
        print(f"    Vol:        {metrics['full']['annual_vol']*100:.2f}%")
        print(f"    Max DD:     {metrics['full']['max_drawdown']*100:.2f}%")
        print(f"    Cost drag:  {metrics['full']['cost_drag_bps']:.2f} bps/year")
        
        print(f"\n  IN-SAMPLE (< {args.split_date}):")
        print(f"    Sharpe:     {metrics['is']['sharpe']:.4f}")
        print(f"    Return:     {metrics['is']['annual_return']*100:.2f}%")
        print(f"    Observations: {metrics['is']['obs']:,}")
        
        print(f"\n  OUT-OF-SAMPLE (>= {args.split_date}):")
        print(f"    Sharpe:     {metrics['oos']['sharpe']:.4f}")
        print(f"    Return:     {metrics['oos']['annual_return']*100:.2f}%")
        print(f"    Observations: {metrics['oos']['obs']:,}")
        
        # IS/OOS degradation
        if metrics['is']['sharpe'] > 0:
            degradation = ((metrics['oos']['sharpe'] / metrics['is']['sharpe']) - 1) * 100
            print(f"\n  IS/OOS Degradation: {degradation:+.1f}%")
        
        # Step 7: Save outputs
        print(f"\n💾 Saving outputs to {args.outdir}...")
        output_dir = Path(args.outdir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save daily series with timestamp
        daily_csv = output_dir / f'daily_series_{timestamp}.csv'
        daily_series.to_csv(daily_csv, index=False)
        print(f"  ✓ Saved {daily_csv.name}")
        
        # Also save latest
        daily_series.to_csv(output_dir / 'daily_series_latest.csv', index=False)
        print(f"  ✓ Saved daily_series_latest.csv")
        
        # Save metrics
        summary = {
            'timestamp': timestamp,
            'config_file': str(args.config),
            'weights_file': str(args.weights),
            'weights_metadata': weights_metadata,
            'static_weights': weights,
            'metrics': metrics
        }
        
        metrics_json = output_dir / f'summary_metrics_{timestamp}.json'
        with open(metrics_json, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"  ✓ Saved {metrics_json.name}")
        
        # Also save latest
        with open(output_dir / 'summary_metrics_latest.json', 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"  ✓ Saved summary_metrics_latest.json")
        
        # Print final summary
        print("\n" + "=" * 80)
        print("BUILD COMPLETE - Static Portfolio")
        print("=" * 80)
        print(f"✅ Full Period Sharpe:  {metrics['full']['sharpe']:.4f}")
        print(f"✅ IS Sharpe:           {metrics['is']['sharpe']:.4f}")
        print(f"✅ OOS Sharpe:          {metrics['oos']['sharpe']:.4f}")
        print(f"✅ Annual Return:       {metrics['full']['annual_return']*100:.2f}%")
        print(f"✅ Max Drawdown:        {metrics['full']['max_drawdown']*100:.2f}%")
        print(f"✅ Observations:        {metrics['full']['obs']:,}")
        
        print(f"\nOutputs saved to:")
        print(f"  {output_dir.absolute()}/")
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