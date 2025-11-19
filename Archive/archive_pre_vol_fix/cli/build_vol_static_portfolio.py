#!/usr/bin/env python3
"""
Build Static Portfolio - Proper Portfolio-Level Costs
=====================================================

Applies STATIC weights with CORRECT cost accounting:
  1. Uses sleeve pnl_gross (not pnl_net)
  2. Calculates portfolio position from weighted sleeve positions
  3. Applies costs when PORTFOLIO position changes
  4. Fair comparison baseline for adaptive portfolio

Author: Claude (ex-Renaissance) + Kieran
Date: November 13, 2025
Version: 2.0 - Portfolio-level cost tracking
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import yaml

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_config(config_path: str) -> dict:
    """Load portfolio configuration YAML."""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config


def load_static_weights(weights_csv_path: str) -> dict:
    """
    Load static weights from CSV.
    
    Args:
        weights_csv_path: Path to vol_static_weights.csv
        
    Returns:
        dict: {sleeve_name: weight}
    """
    df = pd.read_csv(weights_csv_path)
    weights = df.iloc[0].to_dict()
    return weights


def load_sleeves(config: dict) -> dict:
    """
    Load sleeve data with pos and pnl_gross columns.
    
    Returns:
        dict: {sleeve_name: DataFrame with columns [date, pos, pnl_gross, ret]}
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
    Merge sleeves on common dates.
    
    Returns:
        DataFrame with columns: date, [sleeve]_pos, [sleeve]_pnl_gross
    """
    # Start with dates
    first_sleeve = list(sleeves.keys())[0]
    merged = sleeves[first_sleeve][['date']].copy()
    
    # Add each sleeve's pos and pnl_gross
    for sleeve_name, df in sleeves.items():
        sleeve_data = df[['date', 'pos', 'pnl_gross']].rename(columns={
            'pos': f'{sleeve_name}_pos',
            'pnl_gross': f'{sleeve_name}_pnl_gross'
        })
        merged = merged.merge(sleeve_data, on='date', how='inner')
    
    return merged


def build_static_portfolio(merged: pd.DataFrame, weights: dict, cost_bp: float) -> pd.DataFrame:
    """
    Build static portfolio with proper portfolio-level costs.
    
    Args:
        merged: Merged sleeve data
        weights: Static weights dict
        cost_bp: Transaction cost in basis points
        
    Returns:
        DataFrame with portfolio performance
    """
    # Get sleeve names
    sleeve_names = list(weights.keys())
    
    # Add constant weights
    for sleeve_name, weight in weights.items():
        merged[f'{sleeve_name}_weight'] = weight
    
    # Calculate portfolio position and PnL
    print("💼 Calculating portfolio position and costs...")
    
    cost_decimal = cost_bp / 10000.0  # Convert bp to decimal
    
    portfolio_pos = np.zeros(len(merged))
    portfolio_trade = np.zeros(len(merged))
    portfolio_pnl_gross = np.zeros(len(merged))
    portfolio_cost = np.zeros(len(merged))
    
    for i in range(len(merged)):
        # Calculate portfolio position as weighted sum of sleeve positions
        pos = 0.0
        pnl_gross = 0.0
        
        for sleeve_name in sleeve_names:
            sleeve_pos = merged.iloc[i][f'{sleeve_name}_pos']
            sleeve_weight = weights[sleeve_name]
            sleeve_pnl_gross = merged.iloc[i][f'{sleeve_name}_pnl_gross']
            
            # Handle NaN positions (before strategy starts)
            if pd.notna(sleeve_pos):
                pos += sleeve_pos * sleeve_weight
            
            pnl_gross += sleeve_pnl_gross * sleeve_weight
        
        portfolio_pos[i] = pos
        portfolio_pnl_gross[i] = pnl_gross
        
        # Calculate trade (position change)
        if i > 0:
            trade = portfolio_pos[i] - portfolio_pos[i-1]
            portfolio_trade[i] = trade
            
            # Apply cost if position changed
            if trade != 0:
                portfolio_cost[i] = abs(trade) * cost_decimal
    
    # Calculate net PnL
    portfolio_pnl_net = portfolio_pnl_gross - portfolio_cost
    
    # Add to DataFrame
    merged['portfolio_pos'] = portfolio_pos
    merged['portfolio_trade'] = portfolio_trade
    merged['portfolio_pnl_gross'] = portfolio_pnl_gross
    merged['portfolio_cost'] = portfolio_cost
    merged['portfolio_pnl_net'] = portfolio_pnl_net
    
    return merged


def calculate_metrics(daily_series: pd.DataFrame) -> dict:
    """Calculate portfolio performance metrics."""
    returns = daily_series['portfolio_pnl_net'].values
    costs = daily_series['portfolio_cost'].values
    
    # Annual metrics
    mean_ret = returns.mean() * 252
    vol = returns.std() * np.sqrt(252)
    sharpe = mean_ret / vol if vol > 0 else 0.0
    
    # Cumulative returns for drawdown
    cumulative = (1 + returns).cumprod()
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = (cumulative - running_max) / running_max
    max_dd = drawdowns.min()
    
    # Calmar ratio
    calmar = abs(mean_ret / max_dd) if max_dd < 0 else 0.0
    
    # Cost analysis
    total_costs = costs.sum()
    cost_per_year = total_costs / (len(returns) / 252)
    cost_drag_bps = (total_costs / len(returns)) * 252 * 10000
    
    return {
        'sharpe': float(sharpe),
        'annual_return': float(mean_ret),
        'annual_vol': float(vol),
        'max_drawdown': float(max_dd),
        'calmar': float(calmar),
        'total_portfolio_costs': float(total_costs),
        'annual_portfolio_costs': float(cost_per_year),
        'cost_drag_bps': float(cost_drag_bps),
        'obs': len(returns),
        'start_date': daily_series['date'].min().strftime('%Y-%m-%d'),
        'end_date': daily_series['date'].max().strftime('%Y-%m-%d')
    }


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Build static portfolio with proper portfolio-level costs"
    )
    
    parser.add_argument(
        '--config',
        default=r'Config\Copper\portfolio_static.yaml',
        help='Path to portfolio configuration YAML'
    )
    
    parser.add_argument(
        '--weights',
        default=r'outputs\Copper\VolRegime\vol_static_weights.csv',
        help='Path to static weights CSV'
    )
    
    parser.add_argument(
        '--outdir',
        default=r'outputs\Copper\VolStatic',
        help='Output directory for results'
    )
    
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Print header
    print("\n" + "=" * 80)
    print("STATIC PORTFOLIO - Proper Portfolio-Level Costs")
    print("=" * 80)
    print(f"Config:  {args.config}")
    print(f"Weights: {args.weights}")
    print(f"Output:  {args.outdir}")
    
    try:
        # Step 1: Load configuration
        print("\n📋 Loading configuration...")
        config = load_config(args.config)
        
        commodity = config.get('io', {}).get('commodity', 'Unknown')
        cost_bp = config.get('costs', {}).get('transaction_cost_bp', 1.5)
        
        print(f"  Commodity: {commodity}")
        print(f"  Transaction cost: {cost_bp} bps")
        
        # Step 2: Load static weights
        print(f"\n⚖️  Loading static weights from {args.weights}...")
        weights = load_static_weights(args.weights)
        
        print("  Static weights:")
        for name, weight in weights.items():
            print(f"    {name:15s}: {weight:.4f} ({weight*100:.2f}%)")
        
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
        
        print(f"  ✓ Loaded {len(sleeves)} sleeve(s)")
        
        # Step 4: Merge sleeves
        print("\n🔗 Merging sleeves on common dates...")
        merged = merge_sleeves(sleeves)
        print(f"  ✓ Merged to {len(merged)} common trading days")
        print(f"  ✓ Date range: {merged['date'].min()} to {merged['date'].max()}")
        
        # Step 5: Build static portfolio
        print("\n🚀 Building static portfolio...")
        daily_series = build_static_portfolio(merged, weights, cost_bp)
        
        # Step 6: Calculate metrics
        print("\n📈 Calculating performance metrics...")
        metrics = calculate_metrics(daily_series)
        
        print(f"  Sharpe:           {metrics['sharpe']:.4f}")
        print(f"  Return:           {metrics['annual_return']*100:.2f}%")
        print(f"  Vol:              {metrics['annual_vol']*100:.2f}%")
        print(f"  Max DD:           {metrics['max_drawdown']*100:.2f}%")
        print(f"  Calmar:           {metrics['calmar']:.4f}")
        print(f"  Portfolio costs:  {metrics['annual_portfolio_costs']*100:.4f}%/year")
        print(f"  Cost drag:        {metrics['cost_drag_bps']:.2f} bps/year")
        
        # Step 7: Save outputs
        print(f"\n💾 Saving outputs to {args.outdir}...")
        output_dir = Path(args.outdir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save daily series
        daily_series.to_csv(output_dir / 'daily_series.csv', index=False)
        print(f"  ✓ Saved daily_series.csv")
        
        # Save metrics
        summary = {
            'static_weights': weights,
            'metrics': metrics
        }
        with open(output_dir / 'summary_metrics.json', 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"  ✓ Saved summary_metrics.json")
        
        # Print final summary
        print("\n" + "=" * 80)
        print("BUILD COMPLETE - Static Portfolio")
        print("=" * 80)
        print(f"✅ Portfolio Sharpe: {metrics['sharpe']:.4f}")
        print(f"✅ Annual Return:   {metrics['annual_return']*100:.2f}%")
        print(f"✅ Annual Vol:      {metrics['annual_vol']*100:.2f}%")
        print(f"✅ Max Drawdown:    {metrics['max_drawdown']*100:.2f}%")
        print(f"✅ Cost Drag:       {metrics['cost_drag_bps']:.2f} bps/year")
        print(f"✅ Observations:    {metrics['obs']:,}")
        
        print("\nOutputs saved to:")
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