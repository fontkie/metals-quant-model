# src/cli/optimize_rangefader_v5.py
"""
RangeFader v5 Parameter Optimization
=====================================
Systematic grid search to find optimal mean reversion parameters.

CRITICAL RULE: NO FORWARD BIAS
- In-Sample: 2000-2018 (19 years) - for optimization
- Out-of-Sample: 2019-2025 (6.9 years) - NEVER touched during optimization

Target Performance:
- Overall Sharpe: >0.30 (IS), >0.25 (OOS)
- Choppy Sharpe: >0.60 (IS), >0.40 (OOS)
- Activity: 8-15% of days

Usage:
    python src/cli/optimize_rangefader_v5.py --help
"""

import argparse
import pandas as pd
import numpy as np
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.signals.rangefader_v5 import (
    generate_rangefader_signal,
    calculate_adx_ohlc,
    validate_regime_behavior,
)


def calculate_sharpe(returns: pd.Series) -> float:
    """Calculate annualized Sharpe ratio."""
    if len(returns) == 0 or returns.std() == 0:
        return 0.0
    return (returns.mean() / returns.std()) * np.sqrt(252)


def test_parameter_combination(
    df: pd.DataFrame,
    lookback: int,
    entry: float,
    exit: float,
    adx_threshold: float,
    target_vol: float = 0.10,
    cost_bps: float = 3.0,
) -> Dict:
    """
    Test a single parameter combination.
    
    Args:
        df: DataFrame with OHLC data
        lookback: Lookback window for MA/std
        entry: Entry threshold (z-score)
        exit: Exit threshold (z-score)
        adx_threshold: ADX threshold for choppy regime
        target_vol: Target volatility for sizing
        cost_bps: Transaction costs in bps
        
    Returns:
        Dict with performance metrics
    """
    try:
        # Generate signal
        positions = generate_rangefader_signal(
            df,
            lookback_window=lookback,
            zscore_entry=entry,
            zscore_exit=exit,
            adx_threshold=adx_threshold,
            adx_window=14,
            update_frequency=1,
        )
        
        # Calculate returns
        returns = df['price'].pct_change()
        
        # Apply vol targeting (simplified)
        realized_vol = (positions.shift(1) * returns).rolling(63).std() * np.sqrt(252)
        leverage = target_vol / (realized_vol + 1e-6)
        leverage = leverage.clip(0, 3.0)  # Cap at 3x
        
        positions_scaled = positions * leverage
        
        # Calculate strategy returns
        strat_returns = positions_scaled.shift(1) * returns
        
        # Calculate turnover and costs
        position_changes = positions_scaled.diff().abs()
        turnover = position_changes.sum()
        annual_turnover = turnover / (len(df) / 252)
        
        total_costs = turnover * (cost_bps / 10000)
        annual_cost = total_costs / (len(df) / 252)
        
        # Net returns
        net_returns = strat_returns - (position_changes * cost_bps / 10000)
        
        # Calculate metrics
        gross_sharpe = calculate_sharpe(strat_returns.dropna())
        net_sharpe = calculate_sharpe(net_returns.dropna())
        
        # Regime-specific performance
        adx = calculate_adx_ohlc(df['high'], df['low'], df['price'], window=14)
        choppy_mask = adx < adx_threshold
        
        choppy_returns = net_returns[choppy_mask]
        choppy_sharpe = calculate_sharpe(choppy_returns.dropna())
        
        # Activity metrics
        activity_pct = (positions.abs() > 0.01).sum() / len(positions) * 100
        activity_in_choppy = (positions[choppy_mask].abs() > 0.01).sum() / choppy_mask.sum() * 100 if choppy_mask.sum() > 0 else 0
        
        return {
            'lookback': lookback,
            'entry': entry,
            'exit': exit,
            'adx_threshold': adx_threshold,
            'gross_sharpe': gross_sharpe,
            'net_sharpe': net_sharpe,
            'choppy_sharpe': choppy_sharpe,
            'annual_turnover': annual_turnover,
            'annual_cost': annual_cost,
            'activity_pct': activity_pct,
            'activity_in_choppy': activity_in_choppy,
            'choppy_pct_time': choppy_mask.mean() * 100,
            'n_obs': len(df),
            'success': True,
        }
        
    except Exception as e:
        return {
            'lookback': lookback,
            'entry': entry,
            'exit': exit,
            'adx_threshold': adx_threshold,
            'error': str(e),
            'success': False,
        }


def run_optimization(
    df_is: pd.DataFrame,
    df_oos: pd.DataFrame,
    lookback_range: list = [30, 40, 50, 60, 70],
    entry_range: list = [0.6, 0.7, 0.8, 0.9, 1.0],
    exit_range: list = [0.2, 0.3, 0.4],
    adx_range: list = [15, 17, 20],
    target_vol: float = 0.10,
    cost_bps: float = 3.0,
) -> Tuple[pd.DataFrame, Dict]:
    """
    Run full parameter optimization on IS data.
    
    Args:
        df_is: In-sample data (2000-2018)
        df_oos: Out-of-sample data (2019-2025)
        lookback_range: Lookback windows to test
        entry_range: Entry thresholds to test
        exit_range: Exit thresholds to test
        adx_range: ADX thresholds to test
        target_vol: Target volatility
        cost_bps: Transaction costs
        
    Returns:
        results_df: DataFrame with all results
        best_params: Dict with best parameter set
    """
    print("=" * 80)
    print("RANGEFADER V5 PARAMETER OPTIMIZATION")
    print("=" * 80)
    print(f"\nIn-Sample: {df_is.index[0]} to {df_is.index[-1]} ({len(df_is)} days)")
    print(f"Out-of-Sample: {df_oos.index[0]} to {df_oos.index[-1]} ({len(df_oos)} days)")
    print(f"\nParameter Space:")
    print(f"  Lookback: {lookback_range}")
    print(f"  Entry: {entry_range}")
    print(f"  Exit: {exit_range}")
    print(f"  ADX Threshold: {adx_range}")
    
    total_combinations = len(lookback_range) * len(entry_range) * len(exit_range) * len(adx_range)
    print(f"\nTotal Combinations: {total_combinations}")
    print(f"Estimated Time: {total_combinations * 2 / 60:.1f} minutes")
    
    # Run grid search on IS data
    print("\n" + "=" * 80)
    print("PHASE 1: IN-SAMPLE OPTIMIZATION (2000-2018)")
    print("=" * 80)
    
    results = []
    for i, lookback in enumerate(lookback_range):
        for entry in entry_range:
            for exit in exit_range:
                for adx in adx_range:
                    result = test_parameter_combination(
                        df_is, lookback, entry, exit, adx, target_vol, cost_bps
                    )
                    results.append(result)
                    
                    if result['success'] and result['net_sharpe'] > 0.25:
                        print(f"  [{len(results)}/{total_combinations}] "
                              f"L={lookback:2d} E={entry:.1f} X={exit:.1f} ADX={adx:2.0f} "
                              f"→ Net={result['net_sharpe']:+.3f} Choppy={result['choppy_sharpe']:+.3f}")
    
    results_df = pd.DataFrame(results)
    results_df = results_df[results_df['success']]
    
    # Find best IS parameters
    results_df_sorted = results_df.sort_values('net_sharpe', ascending=False)
    best_is = results_df_sorted.iloc[0]
    
    print("\n" + "=" * 80)
    print("TOP 10 IN-SAMPLE CONFIGURATIONS")
    print("=" * 80)
    print(results_df_sorted[['lookback', 'entry', 'exit', 'adx_threshold', 
                              'net_sharpe', 'choppy_sharpe', 'activity_pct']].head(10).to_string(index=False))
    
    # Test best parameters on OOS
    print("\n" + "=" * 80)
    print("PHASE 2: OUT-OF-SAMPLE VALIDATION (2019-2025)")
    print("=" * 80)
    
    best_params = {
        'lookback': int(best_is['lookback']),
        'entry': float(best_is['entry']),
        'exit': float(best_is['exit']),
        'adx_threshold': float(best_is['adx_threshold']),
    }
    
    print(f"\nBest IS Parameters:")
    print(f"  Lookback: {best_params['lookback']}")
    print(f"  Entry: {best_params['entry']}")
    print(f"  Exit: {best_params['exit']}")
    print(f"  ADX Threshold: {best_params['adx_threshold']}")
    
    print(f"\nIS Performance:")
    print(f"  Net Sharpe: {best_is['net_sharpe']:.3f}")
    print(f"  Choppy Sharpe: {best_is['choppy_sharpe']:.3f}")
    print(f"  Activity: {best_is['activity_pct']:.1f}%")
    
    # Test on OOS
    oos_result = test_parameter_combination(
        df_oos,
        best_params['lookback'],
        best_params['entry'],
        best_params['exit'],
        best_params['adx_threshold'],
        target_vol,
        cost_bps,
    )
    
    print(f"\nOOS Performance:")
    print(f"  Net Sharpe: {oos_result['net_sharpe']:.3f}")
    print(f"  Choppy Sharpe: {oos_result['choppy_sharpe']:.3f}")
    print(f"  Activity: {oos_result['activity_pct']:.1f}%")
    
    # Evaluate OOS vs IS
    sharpe_decay = oos_result['net_sharpe'] / best_is['net_sharpe'] if best_is['net_sharpe'] != 0 else 0
    print(f"\nOOS/IS Ratio: {sharpe_decay:.2f}")
    
    if sharpe_decay > 0.70:
        print("  ✓ EXCELLENT - Robust performance")
    elif sharpe_decay > 0.50:
        print("  ✓ GOOD - Acceptable decay")
    elif sharpe_decay > 0.30:
        print("  ⚠ MARGINAL - Significant decay")
    else:
        print("  ✗ POOR - Likely overfit")
    
    # Validate regime behavior
    print("\n" + "=" * 80)
    print("REGIME VALIDATION")
    print("=" * 80)
    
    # Generate positions with best params
    positions_oos = generate_rangefader_signal(
        df_oos,
        lookback_window=best_params['lookback'],
        zscore_entry=best_params['entry'],
        zscore_exit=best_params['exit'],
        adx_threshold=best_params['adx_threshold'],
    )
    
    validation = validate_regime_behavior(
        df_oos,
        positions_oos,
        adx_threshold=best_params['adx_threshold'],
        verbose=True,
    )
    
    # Final recommendation
    print("\n" + "=" * 80)
    print("FINAL RECOMMENDATION")
    print("=" * 80)
    
    deploy_ready = (
        oos_result['net_sharpe'] > 0.20 and
        oos_result['choppy_sharpe'] > 0.30 and
        sharpe_decay > 0.50 and
        validation['all_passed']
    )
    
    if deploy_ready:
        print("\n✓✓ READY TO DEPLOY")
        print(f"  • OOS Sharpe: {oos_result['net_sharpe']:.3f} (target: >0.20)")
        print(f"  • Choppy Sharpe: {oos_result['choppy_sharpe']:.3f} (target: >0.30)")
        print(f"  • Regime validation: PASS")
        print(f"  • Decay ratio: {sharpe_decay:.2f} (target: >0.50)")
    else:
        print("\n✗✗ NOT READY - Issues detected:")
        if oos_result['net_sharpe'] <= 0.20:
            print(f"  • OOS Sharpe too low: {oos_result['net_sharpe']:.3f} (need >0.20)")
        if oos_result['choppy_sharpe'] <= 0.30:
            print(f"  • Choppy Sharpe too low: {oos_result['choppy_sharpe']:.3f} (need >0.30)")
        if sharpe_decay <= 0.50:
            print(f"  • Too much decay: {sharpe_decay:.2f} (need >0.50)")
        if not validation['all_passed']:
            print(f"  • Regime validation FAILED")
    
    return results_df, {
        'best_params': best_params,
        'is_performance': {
            'net_sharpe': float(best_is['net_sharpe']),
            'choppy_sharpe': float(best_is['choppy_sharpe']),
            'activity_pct': float(best_is['activity_pct']),
        },
        'oos_performance': {
            'net_sharpe': float(oos_result['net_sharpe']),
            'choppy_sharpe': float(oos_result['choppy_sharpe']),
            'activity_pct': float(oos_result['activity_pct']),
        },
        'oos_is_ratio': float(sharpe_decay),
        'deploy_ready': deploy_ready,
        'validation': validation,
    }


def main():
    parser = argparse.ArgumentParser(description='Optimize RangeFader v5 parameters')
    parser.add_argument('--csv-close', required=True, help='Path to close price CSV')
    parser.add_argument('--csv-high', required=True, help='Path to high price CSV')
    parser.add_argument('--csv-low', required=True, help='Path to low price CSV')
    parser.add_argument('--outdir', default='outputs/Copper/RangeFader_v5_optimization', 
                       help='Output directory')
    parser.add_argument('--target-vol', type=float, default=0.10, help='Target volatility')
    parser.add_argument('--cost-bps', type=float, default=3.0, help='Transaction costs in bps')
    
    args = parser.parse_args()
    
    # Load data
    print("Loading data...")
    df_close = pd.read_csv(args.csv_close, parse_dates=['date'], index_col='date')
    df_high = pd.read_csv(args.csv_high, parse_dates=['date'], index_col='date')
    df_low = pd.read_csv(args.csv_low, parse_dates=['date'], index_col='date')
    
    df = pd.DataFrame({
        'price': df_close['price'],
        'high': df_high['price'],
        'low': df_low['price'],
    }).dropna()
    
    # Split IS/OOS
    split_date = '2019-01-01'
    df_is = df[df.index < split_date]
    df_oos = df[df.index >= split_date]
    
    # Run optimization
    results_df, summary = run_optimization(
        df_is, df_oos,
        target_vol=args.target_vol,
        cost_bps=args.cost_bps,
    )
    
    # Save results
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    
    results_df.to_csv(outdir / 'optimization_results.csv', index=False)
    
    # Helper function to convert numpy types to Python native types
    def convert_to_native(obj):
        """Recursively convert numpy types to native Python types for JSON serialization."""
        if isinstance(obj, dict):
            return {k: convert_to_native(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [convert_to_native(item) for item in obj]
        elif isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        else:
            return obj
    
    with open(outdir / 'optimization_summary.json', 'w') as f:
        # Convert validation results to JSON-serializable format
        summary_clean = convert_to_native(summary)
        json.dump(summary_clean, f, indent=2)
    
    print(f"\nResults saved to: {outdir}")
    print(f"  • optimization_results.csv")
    print(f"  • optimization_summary.json")


if __name__ == "__main__":
    main()