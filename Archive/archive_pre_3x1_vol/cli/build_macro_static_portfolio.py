#!/usr/bin/env python3
"""
Macro Static Portfolio - Baseline Performance
==============================================

Applies vol_static_weights (40/15/45) across all days and measures performance
by macro state (NORMAL/CHOP/CRISIS). This establishes the baseline before
Path B adjustments.

Process:
  1. Load vol_static_weights.csv (from vol optimization)
  2. Load macro_regimes.csv (NORMAL/CHOP/CRISIS classification)
  3. Load sleeve daily series (TrendMedium, TrendImpulse, MomentumCore)
  4. Apply static weights to all days (no adjustments yet)
  5. Calculate performance metrics by macro state
  6. Save baseline performance

Author: Ex-Renaissance Quant + Kieran
Date: November 13, 2025
Location: C:\Code\Metals\tools\build_macro_static_portfolio.py
"""

import argparse
import sys
from pathlib import Path
import pandas as pd
import numpy as np
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ============================================================================
# PERFORMANCE CALCULATION
# ============================================================================

def calculate_portfolio_metrics(pnl_series):
    """
    Calculate performance metrics from PnL series.
    
    Args:
        pnl_series: Series of portfolio PnL (in dollars)
        
    Returns:
        dict: Performance metrics
    """
    if len(pnl_series) == 0 or pnl_series.sum() == 0:
        return {
            'days': 0,
            'sharpe': 0.0,
            'annual_return': 0.0,
            'annual_vol': 0.0,
            'max_dd': 0.0,
            'total_return': 0.0
        }
    
    # Convert PnL to returns (assume $100 starting capital)
    starting_capital = 100.0
    returns = pnl_series / starting_capital
    
    # Annualized metrics
    years = len(returns) / 252
    total_return = returns.sum()
    annual_return = total_return / years if years > 0 else 0.0
    annual_vol = returns.std() * np.sqrt(252)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0.0
    
    # Max drawdown
    cum_pnl = returns.cumsum()
    running_max = cum_pnl.expanding().max()
    drawdown = (cum_pnl - running_max) / starting_capital
    max_dd = drawdown.min()
    
    return {
        'days': len(returns),
        'sharpe': sharpe,
        'annual_return': annual_return,
        'annual_vol': annual_vol,
        'max_dd': max_dd,
        'total_return': total_return
    }

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Calculate macro static portfolio baseline performance"
    )
    
    parser.add_argument(
        '--vol-weights',
        default=r'C:\Code\Metals\outputs\Copper\VolRegime\vol_static_weights.csv',
        help='Path to vol_static_weights.csv'
    )
    
    parser.add_argument(
        '--macro-regimes',
        default=r'C:\Code\Metals\outputs\Copper\MacroRegime\macro_regimes.csv',
        help='Path to macro_regimes.csv'
    )
    
    parser.add_argument(
        '--sleeve-dir',
        default=r'C:\Code\Metals\outputs\Copper',
        help='Base directory for sleeve outputs'
    )
    
    parser.add_argument(
        '--outdir',
        default=r'C:\Code\Metals\outputs\Copper\MacroRegime',
        help='Output directory'
    )
    
    parser.add_argument(
        '--start-date',
        default='2000-01-01',
        help='Start date for analysis'
    )
    
    parser.add_argument(
        '--end-date',
        default='2025-12-31',
        help='End date for analysis'
    )
    
    args = parser.parse_args()
    
    # Print header
    print("\n" + "=" * 80)
    print("MACRO STATIC PORTFOLIO - BASELINE PERFORMANCE")
    print("=" * 80)
    print(f"Period:      {args.start_date} to {args.end_date}")
    
    try:
        # Step 1: Load vol static weights
        print("\n📊 Loading vol static weights...")
        weights_path = Path(args.vol_weights)
        if not weights_path.exists():
            print(f"ERROR: Vol weights file not found: {weights_path}")
            print("Run build_vol_static_weights.py first!")
            return 1
        
        weights_df = pd.read_csv(weights_path)
        weights = {
            'TrendMedium': weights_df['TrendMedium'].iloc[0],
            'TrendImpulse': weights_df['TrendImpulse'].iloc[0],
            'MomentumCore': weights_df['MomentumCore'].iloc[0]
        }
        
        print(f"  Vol Static Weights (from vol optimization):")
        for name, weight in weights.items():
            print(f"    {name:15s}: {weight:.4f} ({weight*100:.1f}%)")
        
        # Step 2: Load macro regimes
        print("\n📅 Loading macro regimes...")
        macro_path = Path(args.macro_regimes)
        if not macro_path.exists():
            print(f"ERROR: Macro regimes file not found: {macro_path}")
            print("Run build_macro_regimes.py first!")
            return 1
        
        macro_df = pd.read_csv(macro_path)
        macro_df['date'] = pd.to_datetime(macro_df['date'])
        macro_df = macro_df[['date', 'macro_state']].set_index('date')
        
        print(f"  ✓ Loaded {len(macro_df)} days of macro regimes")
        
        # Show distribution
        macro_dist = macro_df['macro_state'].value_counts()
        print(f"\n  Macro state distribution:")
        for state in ['NORMAL', 'CHOP', 'CRISIS']:
            if state in macro_dist.index:
                count = macro_dist[state]
                pct = (count / len(macro_df)) * 100
                print(f"    {state:10s}: {count:5d} days ({pct:5.1f}%)")
        
        # Step 3: Load sleeve data
        print("\n📂 Loading sleeve daily series...")
        sleeve_paths = {
            'TrendMedium': Path(args.sleeve_dir) / 'TrendMedium' / 'daily_series.csv',
            'TrendImpulse': Path(args.sleeve_dir) / 'TrendImpulse_v4' / 'daily_series.csv',
            'MomentumCore': Path(args.sleeve_dir) / 'MomentumCore_v1' / 'daily_series.csv',
        }
        
        sleeves = {}
        for name, path in sleeve_paths.items():
            if not path.exists():
                print(f"ERROR: Sleeve file not found: {path}")
                return 1
            
            df = pd.read_csv(path)
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            sleeves[name] = df
            print(f"  ✓ Loaded {name}: {len(df)} days")
        
        # Step 4: Filter to date range
        start_date = pd.to_datetime(args.start_date)
        end_date = pd.to_datetime(args.end_date)
        
        for name in sleeves:
            sleeves[name] = sleeves[name].loc[start_date:end_date]
        macro_df = macro_df.loc[start_date:end_date]
        
        # Get common dates
        common_dates = macro_df.index
        for name in sleeves:
            common_dates = common_dates.intersection(sleeves[name].index)
        
        print(f"\n  {len(common_dates)} common trading days in period")
        
        # Step 5: Calculate portfolio PnL by applying static weights
        print("\n💰 Calculating portfolio PnL with static weights...")
        
        portfolio_pnl = pd.Series(0.0, index=common_dates)
        for name, weight in weights.items():
            portfolio_pnl += sleeves[name].loc[common_dates, 'pnl_net'] * weight
        
        # Combine with macro states
        portfolio_df = pd.DataFrame({
            'date': common_dates,
            'portfolio_pnl': portfolio_pnl.values,
            'macro_state': macro_df.loc[common_dates, 'macro_state'].values
        })
        
        # Step 6: Calculate performance by macro state
        print("\n📈 Calculating performance by macro state...")
        results = []
        
        for macro_state in ['NORMAL', 'CHOP', 'CRISIS']:
            state_df = portfolio_df[portfolio_df['macro_state'] == macro_state]
            
            if len(state_df) == 0:
                continue
            
            state_pnl = state_df['portfolio_pnl']
            metrics = calculate_portfolio_metrics(state_pnl)
            
            pct_of_time = (len(state_df) / len(portfolio_df)) * 100
            
            results.append({
                'macro_state': macro_state,
                'days': metrics['days'],
                'pct_of_time': pct_of_time,
                'sharpe': metrics['sharpe'],
                'annual_return': metrics['annual_return'],
                'annual_vol': metrics['annual_vol'],
                'max_dd': metrics['max_dd'],
                'total_return': metrics['total_return']
            })
            
            print(f"\n  {macro_state}:")
            print(f"    Days:         {metrics['days']:,} ({pct_of_time:.1f}%)")
            print(f"    Sharpe:       {metrics['sharpe']:.4f}")
            print(f"    Annual Ret:   {metrics['annual_return']*100:.2f}%")
            print(f"    Annual Vol:   {metrics['annual_vol']*100:.2f}%")
            print(f"    Max DD:       {metrics['max_dd']*100:.2f}%")
        
        # Step 7: Calculate full period performance
        print("\n" + "-" * 80)
        print("FULL PERIOD PERFORMANCE (Static 40/15/45)")
        print("-" * 80)
        full_metrics = calculate_portfolio_metrics(portfolio_df['portfolio_pnl'])
        
        print(f"  Days:         {full_metrics['days']:,}")
        print(f"  Sharpe:       {full_metrics['sharpe']:.4f}")
        print(f"  Annual Ret:   {full_metrics['annual_return']*100:.2f}%")
        print(f"  Annual Vol:   {full_metrics['annual_vol']*100:.2f}%")
        print(f"  Max DD:       {full_metrics['max_dd']*100:.2f}%")
        
        # Step 8: Save results
        print("\n💾 Saving results...")
        output_dir = Path(args.outdir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save performance by state
        results_df = pd.DataFrame(results)
        results_path = output_dir / 'macro_static_portfolio_performance.csv'
        results_df.to_csv(results_path, index=False)
        print(f"  ✓ Saved: {results_path}")
        
        # Save daily series
        daily_path = output_dir / 'macro_static_portfolio_daily.csv'
        portfolio_df.to_csv(daily_path, index=False)
        print(f"  ✓ Saved: {daily_path}")
        
        # Save metadata
        metadata = {
            'weights': weights,
            'period': {
                'start': args.start_date,
                'end': args.end_date,
                'days': len(common_dates)
            },
            'full_period_metrics': {k: float(v) for k, v in full_metrics.items()},
            'by_macro_state': results,
            'generated_date': pd.Timestamp.now().isoformat()
        }
        
        metadata_path = output_dir / 'macro_static_portfolio_metadata.json'
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"  ✓ Saved: {metadata_path}")
        
        print("\n" + "=" * 80)
        print("✓ MACRO STATIC PORTFOLIO BASELINE COMPLETE")
        print("=" * 80)
        print(f"\nBaseline Sharpe: {full_metrics['sharpe']:.4f}")
        print(f"This is your baseline before Path B adjustments.")
        print(f"\nNext step: Run Path B optimizer to find CHOP/CRISIS multipliers")
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