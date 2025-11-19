#!/usr/bin/env python3
"""
Build Adaptive Portfolio - AUTO-OPTIMIZED from Performance Matrix
==================================================================

KEY IMPROVEMENT: Reads optimal weights directly from sleeve_performance_3x3_matrix.csv
No manual weight entry - single source of truth!

Optimization strategy:
  - If dominant sleeve (Sharpe > 1.0, others < 0.5): 80% allocation
  - If strong preference (Sharpe gap > 0.5): 70% allocation  
  - If moderate preference (Sharpe gap > 0.2): 60% allocation
  - If close competition: 50/35/15 split
  - If all negative: Equal weight defensive (33/33/33)

Author: Claude (ex-Renaissance) + Kieran
Date: November 14, 2025
Version: 3.0 - Auto-optimized from performance matrix
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


def load_optimal_weights_from_matrix(matrix_path: str) -> dict:
    """
    Load and calculate optimal weights from performance matrix CSV.
    
    Args:
        matrix_path: Path to sleeve_performance_3x3_matrix.csv
        
    Returns:
        dict: {regime_name: {sleeve_name: weight}}
    """
    print(f"\n🎯 Loading performance matrix from: {matrix_path}")
    
    perf = pd.read_csv(matrix_path)
    
    # Parse regime names to match config format
    perf['vol_regime_lower'] = perf['vol_regime'].str.lower()
    perf['trend_state_lower'] = perf['trend_state'].str.lower()
    perf['regime_name'] = perf['vol_regime_lower'] + '_vol_' + perf['trend_state_lower']
    
    print(f"  ✓ Loaded {len(perf)} sleeve×regime combinations")
    
    # Calculate optimal weights for each regime
    optimal_weights = {}
    
    for regime_name in sorted(perf['regime_name'].unique()):
        regime_data = perf[perf['regime_name'] == regime_name]
        
        # Get Sharpe ratios for each sleeve
        sharpes = {}
        for _, row in regime_data.iterrows():
            sharpes[row['sleeve']] = row['sharpe']
        
        # Sort by Sharpe
        sorted_sleeves = sorted(sharpes.items(), key=lambda x: x[1], reverse=True)
        best_sleeve, best_sharpe = sorted_sleeves[0]
        second_sleeve, second_sharpe = sorted_sleeves[1]
        third_sleeve, third_sharpe = sorted_sleeves[2]
        
        # Apply optimization logic
        if best_sharpe < 0:
            # All negative - equal weight defensive
            weights = {
                sorted_sleeves[0][0]: 0.33,
                sorted_sleeves[1][0]: 0.33,
                sorted_sleeves[2][0]: 0.34
            }
            strategy = "All negative - defensive equal weight"
            
        elif best_sharpe > 1.0 and second_sharpe < 0.5:
            # Clear winner - concentrate 80%
            weights = {
                best_sleeve: 0.80,
                second_sleeve: 0.15,
                third_sleeve: 0.05
            }
            strategy = f"Dominant {best_sleeve} ({best_sharpe:.2f}) - 80% allocation"
            
        elif best_sharpe - second_sharpe > 0.5:
            # Strong preference - 70%
            weights = {
                best_sleeve: 0.70,
                second_sleeve: 0.25,
                third_sleeve: 0.05
            }
            strategy = f"Strong {best_sleeve} ({best_sharpe:.2f}) - 70% allocation"
            
        elif best_sharpe - second_sharpe > 0.2:
            # Moderate preference - 60%
            weights = {
                best_sleeve: 0.60,
                second_sleeve: 0.30,
                third_sleeve: 0.10
            }
            strategy = f"Moderate {best_sleeve} ({best_sharpe:.2f}) - 60% allocation"
            
        else:
            # Close competition - 50%
            weights = {
                best_sleeve: 0.50,
                second_sleeve: 0.35,
                third_sleeve: 0.15
            }
            strategy = f"Close competition - balanced allocation"
        
        optimal_weights[regime_name] = weights
        
        print(f"\n  {regime_name}:")
        print(f"    Sharpes: TM={sharpes.get('TrendMedium', 0):.2f}, TI={sharpes.get('TrendImpulse', 0):.2f}, MC={sharpes.get('MomentumCore', 0):.2f}")
        print(f"    Weights: TM={weights.get('TrendMedium', 0):.0%}, TI={weights.get('TrendImpulse', 0):.0%}, MC={weights.get('MomentumCore', 0):.0%}")
        print(f"    Strategy: {strategy}")
    
    return optimal_weights


def load_sleeves(config: dict) -> dict:
    """Load sleeve data with pos and pnl_gross columns."""
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
            required = ['date', 'pos', 'pnl_gross', 'ret']
            missing = [col for col in required if col not in df.columns]
            if missing:
                print(f"  ⚠️  {sleeve_name} missing columns: {missing}")
                continue
            
            sleeves[sleeve_name] = df[['date', 'pos', 'pnl_gross', 'ret']]
            print(f"  ✓ Loaded {sleeve_name}: {len(df)} days")
            
        except Exception as e:
            print(f"  ✗ Failed to load {sleeve_name}: {e}")
    
    return sleeves


def merge_sleeves(sleeves: dict) -> pd.DataFrame:
    """Merge sleeves on common dates."""
    first_sleeve = list(sleeves.keys())[0]
    merged = sleeves[first_sleeve][['date', 'ret']].copy()
    
    for sleeve_name, df in sleeves.items():
        sleeve_data = df[['date', 'pos', 'pnl_gross']].rename(columns={
            'pos': f'{sleeve_name}_pos',
            'pnl_gross': f'{sleeve_name}_pnl_gross'
        })
        merged = merged.merge(sleeve_data, on='date', how='inner')
    
    return merged


def detect_regime_full(merged: pd.DataFrame, config: dict) -> pd.Series:
    """Full 3x3 regime detection using volatility terciles × ADX trend states."""
    # Step 1: Calculate volatility regime
    vol_cfg = config.get('regime_detection', {}).get('volatility', {})
    vol_window = vol_cfg.get('vol_window_days', 63)
    percentile_window = vol_cfg.get('percentile_lookback_days', 252)
    low_threshold = vol_cfg.get('low_vol_percentile', 0.33)
    high_threshold = vol_cfg.get('high_vol_percentile', 0.67)
    
    vol = merged['ret'].rolling(window=vol_window, min_periods=20).std() * np.sqrt(252)
    vol_percentile = vol.rolling(window=percentile_window, min_periods=60).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else np.nan
    )
    
    vol_regime = pd.Series('medium_vol', index=merged.index)
    vol_regime[vol_percentile < low_threshold] = 'low_vol'
    vol_regime[vol_percentile > high_threshold] = 'high_vol'
    
    # Step 2: Load ADX trend regimes
    adx_path = 'C:/Code/Metals/outputs/Copper/VolRegime/adx_trend_regimes.csv'
    
    try:
        print(f"  Loading ADX trend regimes from: {adx_path}")
        adx_df = pd.read_csv(adx_path)
        adx_df['date'] = pd.to_datetime(adx_df['date'])
        
        merged_with_adx = merged[['date']].merge(
            adx_df[['date', 'trend_state']], 
            on='date', 
            how='left'
        )
        
        trend_regime = merged_with_adx['trend_state'].str.lower()
        trend_regime = trend_regime.fillna('ranging')
        
        matched = (~merged_with_adx['trend_state'].isna()).sum()
        print(f"  ✓ Matched {matched}/{len(merged)} dates with ADX trend states")
        
    except Exception as e:
        print(f"  ⚠️  Warning: Could not load ADX trend regimes from {adx_path}")
        print(f"     Error: {e}")
        trend_regime = pd.Series('ranging', index=merged.index)
    
    # Step 3: Combine vol and trend regimes
    regime = vol_regime + '_' + trend_regime
    
    return regime


def get_regime_weights_from_dict(regime: str, optimal_weights: dict) -> dict:
    """Look up weights from pre-calculated optimal weights dict."""
    if regime in optimal_weights:
        return optimal_weights[regime]
    
    # Fallback: equal weight
    return {'TrendMedium': 0.33, 'TrendImpulse': 0.33, 'MomentumCore': 0.34}


def smooth_weights_ema(weights_series: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """Apply exponential smoothing to weight transitions."""
    if window <= 1:
        return weights_series
    
    alpha = 2.0 / (window + 1)
    return weights_series.ewm(alpha=alpha, adjust=False).mean()


def build_adaptive_portfolio(merged: pd.DataFrame, config: dict, optimal_weights: dict) -> pd.DataFrame:
    """Build adaptive portfolio with auto-optimized weights from matrix."""
    sleeve_names = [col.replace('_pos', '') for col in merged.columns if col.endswith('_pos')]
    
    # Detect regimes
    print("\n📊 Detecting market regimes...")
    regime = detect_regime_full(merged, config)
    merged['regime'] = regime
    
    # Get target weights for each regime (from optimal_weights dict)
    print("⚖️  Applying auto-optimized regime weights...")
    target_weights = []
    for idx, row in merged.iterrows():
        regime_label = row['regime']
        weights = get_regime_weights_from_dict(regime_label, optimal_weights)
        target_weights.append(weights)
    
    weights_df = pd.DataFrame(target_weights, index=merged.index)
    
    # Apply smoothing if enabled
    smooth_cfg = config.get('transition_smoothing', {})
    if smooth_cfg.get('enabled', True):
        window = smooth_cfg.get('window_days', 1)
        if window > 1:
            print(f"🔄 Smoothing weight transitions (window={window})...")
            weights_df = smooth_weights_ema(weights_df, window=window)
    
    # Add weights to merged
    for sleeve_name in sleeve_names:
        merged[f'{sleeve_name}_weight'] = weights_df[sleeve_name]
    
    # Calculate portfolio position and PnL
    print("💼 Calculating portfolio position and costs...")
    
    cost_cfg = config.get('costs', {})
    cost_bp = cost_cfg.get('transaction_cost_bp', 1.5) / 10000.0
    
    portfolio_pos = np.zeros(len(merged))
    portfolio_trade = np.zeros(len(merged))
    portfolio_pnl_gross = np.zeros(len(merged))
    portfolio_cost = np.zeros(len(merged))
    
    for i in range(len(merged)):
        pos = 0.0
        pnl_gross = 0.0
        
        for sleeve_name in sleeve_names:
            sleeve_pos = merged.iloc[i][f'{sleeve_name}_pos']
            sleeve_weight = merged.iloc[i][f'{sleeve_name}_weight']
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
                portfolio_cost[i] = abs(trade) * cost_bp
    
    portfolio_pnl_net = portfolio_pnl_gross - portfolio_cost
    
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
    
    mean_ret = returns.mean() * 252
    vol = returns.std() * np.sqrt(252)
    sharpe = mean_ret / vol if vol > 0 else 0.0
    
    cumulative = (1 + returns).cumprod()
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = (cumulative - running_max) / running_max
    max_dd = drawdowns.min()
    
    calmar = abs(mean_ret / max_dd) if max_dd < 0 else 0.0
    
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
        description="Build adaptive portfolio with AUTO-OPTIMIZED weights from performance matrix"
    )
    
    parser.add_argument(
        '--config',
        default=r'Config\Copper\vol_adaptive_portfolio.yaml',
        help='Path to portfolio configuration YAML'
    )
    
    parser.add_argument(
        '--matrix',
        default=r'outputs\Copper\VolRegime\sleeve_performance_3x3_matrix.csv',
        help='Path to performance matrix CSV (for auto-optimization)'
    )
    
    parser.add_argument(
        '--outdir',
        default=r'outputs\Copper\VolAdaptive',
        help='Output directory for results'
    )
    
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Print header
    print("\n" + "=" * 80)
    print("ADAPTIVE PORTFOLIO - AUTO-OPTIMIZED from Performance Matrix")
    print("=" * 80)
    print(f"Config: {args.config}")
    print(f"Matrix: {args.matrix}")
    print(f"Output: {args.outdir}")
    
    try:
        # Step 1: Load configuration
        print("\n📋 Loading configuration...")
        config = load_config(args.config)
        
        commodity = config.get('io', {}).get('commodity', 'Unknown')
        portfolio_name = config.get('io', {}).get('portfolio_name', 'Unknown')
        
        print(f"  Commodity: {commodity}")
        print(f"  Portfolio: {portfolio_name}")
        
        # Step 2: Load optimal weights from performance matrix
        optimal_weights = load_optimal_weights_from_matrix(args.matrix)
        
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
        
        # Step 5: Build adaptive portfolio
        print("\n🚀 Building adaptive portfolio...")
        daily_series = build_adaptive_portfolio(merged, config, optimal_weights)
        
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
        
        # Save metrics with optimal weights
        summary = {
            'optimization_source': args.matrix,
            'optimal_weights': optimal_weights,
            'metrics': metrics
        }
        with open(output_dir / 'summary_metrics.json', 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"  ✓ Saved summary_metrics.json (includes optimal weights)")
        
        # Save regime summary
        regime_summary = daily_series.groupby('regime').agg({
            'portfolio_pnl_net': ['count', 'mean', 'std'],
            'portfolio_cost': 'sum'
        }).round(6)
        regime_summary.to_csv(output_dir / 'regime_summary.csv')
        print(f"  ✓ Saved regime_summary.csv")
        
        # Print final summary
        print("\n" + "=" * 80)
        print("BUILD COMPLETE - Adaptive Portfolio (AUTO-OPTIMIZED)")
        print("=" * 80)
        print(f"✅ Portfolio Sharpe: {metrics['sharpe']:.4f}")
        print(f"✅ Annual Return:   {metrics['annual_return']*100:.2f}%")
        print(f"✅ Annual Vol:      {metrics['annual_vol']*100:.2f}%")
        print(f"✅ Max Drawdown:    {metrics['max_drawdown']*100:.2f}%")
        print(f"✅ Cost Drag:       {metrics['cost_drag_bps']:.2f} bps/year")
        print(f"✅ Observations:    {metrics['obs']:,}")
        
        print("\n💡 Weights auto-optimized from:")
        print(f"   {args.matrix}")
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