#!/usr/bin/env python3
"""
Volatility-Static Portfolio Builder
====================================

Tests STATIC blending (fixed weights) as a baseline comparison.
This is the STATIC baseline - weights NEVER change regardless of regime.

Uses same regime files but applies FIXED weights FROM CSV:
  Weights are calculated by build_static_vol_weights.py via grid search
  optimization on 2000-2018 data, then FROZEN for out-of-sample testing.
  
  Example weights after optimization:
    TrendMedium:  52%
    TrendImpulse: 23%
    MomentumCore: 25%
  
  (Actual weights depend on optimization results)

Purpose: Measure value-add of adaptive blending vs. optimized static baseline.

Author: Claude (ex-Renaissance) + Kieran
Date: November 13, 2025
Version: 1.0 - Baseline comparison
"""

import argparse
import json
import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_regime_files(base_dir):
    """Load regime classification files (for date alignment only)."""
    base_path = Path(base_dir)
    
    combined_regime_path = base_path / 'regime_classification_vol_trend.csv'
    
    if combined_regime_path.exists():
        df = pd.read_csv(combined_regime_path)
        print(f"  ✓ Loaded regime dates: {len(df)} rows")
        return df
    else:
        raise FileNotFoundError(f"Missing: {combined_regime_path}")


def load_sleeve_data(sleeve_paths):
    """Load daily series for each sleeve."""
    sleeves = {}
    for name, path in sleeve_paths.items():
        filepath = Path(path)
        if filepath.exists():
            df = pd.read_csv(filepath)
            df['date'] = pd.to_datetime(df['date'])
            sleeves[name] = df
            print(f"  ✓ Loaded {name}: {len(df)} days")
        else:
            print(f"  ✗ Missing sleeve: {filepath}")
    
    return sleeves


def apply_static_blending(sleeves, regime_df, static_weights):
    """
    Apply FIXED weights to sleeve returns (no regime adaptation).
    
    Args:
        sleeves: dict of {sleeve_name: DataFrame with 'date', 'portfolio_ret'}
        regime_df: DataFrame with 'date' and 'combined_regime' (for alignment)
        static_weights: dict of {sleeve_name: weight} - CONSTANT across all regimes
    
    Returns:
        DataFrame with daily portfolio returns
    """
    # Merge all sleeves on date
    base_dates = regime_df[['date', 'combined_regime']].copy()
    base_dates['date'] = pd.to_datetime(base_dates['date'])
    
    for sleeve_name, sleeve_df in sleeves.items():
        ret_col = f'{sleeve_name}_ret'
        
        # Handle different column names
        if 'ret' in sleeve_df.columns:
            base_dates = base_dates.merge(
                sleeve_df[['date', 'ret']].rename(columns={'ret': ret_col}),
                on='date',
                how='left'
            )
        elif 'portfolio_ret' in sleeve_df.columns:
            base_dates = base_dates.merge(
                sleeve_df[['date', 'portfolio_ret']].rename(columns={'portfolio_ret': ret_col}),
                on='date',
                how='left'
            )
        elif 'pnl_net' in sleeve_df.columns:
            base_dates = base_dates.merge(
                sleeve_df[['date', 'pnl_net']].rename(columns={'pnl_net': ret_col}),
                on='date',
                how='left'
            )
        else:
            raise ValueError(f"Sleeve {sleeve_name} missing return column")
    
    # Apply STATIC weights (same every day)
    portfolio_rets = []
    weights_log = []
    
    for idx, row in base_dates.iterrows():
        # Calculate weighted return with FIXED weights
        total_ret = 0.0
        for sleeve_name in sleeves.keys():
            ret = row.get(f'{sleeve_name}_ret', 0.0)
            weight = static_weights[sleeve_name]
            total_ret += ret * weight
        
        portfolio_rets.append(total_ret)
        weights_log.append({
            'date': row['date'],
            'regime': row['combined_regime'],  # Track regime but don't use it
            **{f'{name}_weight': static_weights[name] for name in sleeves.keys()}
        })
    
    # Add portfolio returns to dataframe
    base_dates['portfolio_ret'] = portfolio_rets
    base_dates['portfolio_pnl'] = base_dates['portfolio_ret'].cumsum()
    
    return base_dates, pd.DataFrame(weights_log)


def calculate_metrics(daily_series, split_date='2019-01-01'):
    """Calculate performance metrics with IS/OOS split."""
    
    daily_series['date'] = pd.to_datetime(daily_series['date'])
    
    def calc_period_metrics(df, label):
        returns = df['portfolio_ret'].values
        
        # Annualization factor (252 trading days)
        ann_factor = np.sqrt(252)
        
        annual_return = returns.mean() * 252
        annual_vol = returns.std() * ann_factor
        sharpe = annual_return / annual_vol if annual_vol > 0 else 0.0
        
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdowns = (cumulative - running_max) / running_max
        max_dd = drawdowns.min()
        
        return {
            f'{label}_sharpe': sharpe,
            f'{label}_return': annual_return,
            f'{label}_vol': annual_vol,
            f'{label}_max_dd': max_dd,
            f'{label}_days': len(df)
        }
    
    # Full period
    full_metrics = calc_period_metrics(daily_series, 'full')
    
    # In-sample (before split_date)
    is_data = daily_series[daily_series['date'] < split_date]
    is_metrics = calc_period_metrics(is_data, 'is')
    
    # Out-of-sample (after split_date)
    oos_data = daily_series[daily_series['date'] >= split_date]
    oos_metrics = calc_period_metrics(oos_data, 'oos')
    
    return {**full_metrics, **is_metrics, **oos_metrics}


def load_static_weights(weights_path):
    """Load static weights from CSV."""
    df = pd.read_csv(weights_path)
    
    # Should have exactly one row
    if len(df) != 1:
        raise ValueError(f"Expected 1 row in weights CSV, got {len(df)}")
    
    weights = {
        'TrendMedium': df['TrendMedium'].iloc[0],
        'TrendImpulse': df['TrendImpulse'].iloc[0],
        'MomentumCore': df['MomentumCore'].iloc[0],
    }
    
    return weights


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Build VOL-STATIC portfolio (fixed weights)"
    )
    
    parser.add_argument(
        '--regime-dir',
        default=r'C:\Code\Metals\outputs\Copper\VolRegime',
        help='Directory containing regime files (for date alignment)'
    )
    
    parser.add_argument(
        '--weights-csv',
        default=r'C:\Code\Metals\outputs\Copper\VolRegime\vol_static_weights.csv',
        help='Path to static weights CSV'
    )
    
    parser.add_argument(
        '--sleeve-dir',
        default=r'C:\Code\Metals\outputs\Copper',
        help='Base directory for sleeve outputs'
    )
    
    parser.add_argument(
        '--outdir',
        default=r'C:\Code\Metals\outputs\Copper\VolStatic',
        help='Output directory'
    )
    
    args = parser.parse_args()
    
    # Load static weights from CSV
    print("\n⚖️  Loading static weights from CSV...")
    static_weights = load_static_weights(args.weights_csv)
    print(f"  ✓ Loaded weights from: {args.weights_csv}")
    
    # Validate weights sum to 1.0
    total_weight = sum(static_weights.values())
    if not np.isclose(total_weight, 1.0):
        print(f"  Warning: Weights sum to {total_weight:.4f}, normalizing to 1.0")
        static_weights = {k: v/total_weight for k, v in static_weights.items()}
    
    # Print header
    print("\n" + "=" * 80)
    print("VOL-STATIC PORTFOLIO BUILDER")
    print("Baseline: FIXED weights (no regime adaptation)")
    print("=" * 80)
    print("Static weights:")
    for name, weight in static_weights.items():
        print(f"  {name:15s}: {weight:.2%}")
    
    try:
        # Step 1: Load regime files (for date alignment)
        print("\n📊 Loading regime dates...")
        regime_df = load_regime_files(args.regime_dir)
        
        # Step 2: Load sleeve data
        print("\n📂 Loading sleeve data...")
        sleeve_paths = {
            'TrendMedium': Path(args.sleeve_dir) / 'TrendMedium' / 'daily_series.csv',
            'TrendImpulse': Path(args.sleeve_dir) / 'TrendImpulse_v4' / 'daily_series.csv',
            'MomentumCore': Path(args.sleeve_dir) / 'MomentumCore_v1' / 'daily_series.csv',
        }
        sleeves = load_sleeve_data(sleeve_paths)
        
        if len(sleeves) != 3:
            raise ValueError(f"Expected 3 sleeves, got {len(sleeves)}")
        
        # Step 3: Apply static blending
        print("\n🔒 Applying STATIC blending (fixed weights)...")
        daily_series, weights_log = apply_static_blending(
            sleeves,
            regime_df,
            static_weights
        )
        
        print(f"  ✓ Generated {len(daily_series)} days of portfolio returns")
        
        # Step 4: Calculate metrics
        print("\n📈 Calculating performance metrics...")
        metrics = calculate_metrics(daily_series)
        
        # Step 5: Save outputs
        print(f"\n💾 Saving outputs to {args.outdir}...")
        output_dir = Path(args.outdir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save daily series
        daily_series.to_csv(output_dir / 'vol_static_daily_series.csv', index=False)
        print(f"  ✓ Saved vol_static_daily_series.csv")
        
        # Save weights log (constant weights for reference)
        weights_log.to_csv(output_dir / 'vol_static_weights_log.csv', index=False)
        print(f"  ✓ Saved vol_static_weights_log.csv")
        
        # Save metrics
        with open(output_dir / 'vol_static_metrics.json', 'w') as f:
            json.dump(metrics, f, indent=2)
        print(f"  ✓ Saved vol_static_metrics.json")
        
        # Save config
        config_output = {
            'strategy': 'vol_static',
            'description': 'Fixed weights baseline (no regime adaptation)',
            'weights': static_weights,
        }
        with open(output_dir / 'vol_static_config.json', 'w') as f:
            json.dump(config_output, f, indent=2)
        print(f"  ✓ Saved vol_static_config.json")
        
        # Print summary
        print("\n" + "=" * 80)
        print("VOL-STATIC RESULTS")
        print("=" * 80)
        print(f"Full Period  (2000-2025):")
        print(f"  Sharpe:      {metrics['full_sharpe']:.4f}")
        print(f"  Return:      {metrics['full_return']*100:.2f}%")
        print(f"  Vol:         {metrics['full_vol']*100:.2f}%")
        print(f"  Max DD:      {metrics['full_max_dd']*100:.2f}%")
        print(f"\nIn-Sample    (2000-2018):")
        print(f"  Sharpe:      {metrics['is_sharpe']:.4f}")
        print(f"  Days:        {metrics['is_days']:,}")
        print(f"\nOut-of-Sample (2019-2025):")
        print(f"  Sharpe:      {metrics['oos_sharpe']:.4f}")
        print(f"  Days:        {metrics['oos_days']:,}")
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