# src/cli/build_rangefader_v5.py
"""
RangeFader v5 Builder - 4-Layer Architecture
=============================================
Builds complete RangeFader v5 backtest with proper OHLC ADX.

CRITICAL FIX FROM V4:
- V4 used close-only ADX (underestimated by ~6 points)
- V5 uses proper OHLC ADX calculation

Layers:
1. Signal Generation (rangefader_v5.py) - Pure strategy logic with OHLC ADX
2. Vol Targeting - Closed-loop EWMA targeting to 10%
3. Portfolio (future) - Single sleeve for now
4. Execution - Apply costs once on net position

Usage:
    python src/cli/build_rangefader_v5.py --help
"""

import argparse
import pandas as pd
import numpy as np
import yaml
import json
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.signals.rangefader_v5 import (
    generate_rangefader_signal,
    get_regime_statistics,
    get_signal_statistics,
    validate_regime_behavior,
)


def apply_vol_targeting(
    positions: pd.Series,
    returns: pd.Series,
    target_vol: float = 0.10,
    vol_window: int = 63,
    leverage_cap: float = 3.0,
) -> pd.Series:
    """
    Apply volatility targeting to positions (Layer 2).
    
    Args:
        positions: Raw position signal (-1 to +1)
        returns: Asset returns
        target_vol: Target annualized volatility
        vol_window: Rolling window for vol calculation
        leverage_cap: Maximum leverage multiplier
        
    Returns:
        pd.Series: Vol-targeted positions
    """
    # Calculate realized vol of strategy
    strat_returns = positions.shift(1) * returns
    realized_vol = strat_returns.rolling(vol_window).std() * np.sqrt(252)
    
    # Calculate leverage adjustment
    leverage = target_vol / (realized_vol + 1e-6)
    leverage = leverage.clip(0, leverage_cap)
    
    # Apply leverage
    positions_targeted = positions * leverage
    
    return positions_targeted


def calculate_costs(
    positions: pd.Series,
    cost_bps: float = 3.0,
) -> pd.Series:
    """
    Calculate transaction costs (Layer 4).
    
    Args:
        positions: Position series
        cost_bps: One-way cost in basis points
        
    Returns:
        pd.Series: Costs in return units
    """
    position_changes = positions.diff().abs()
    costs = position_changes * (cost_bps / 10000)
    return costs


def build_rangefader_v5(
    df: pd.DataFrame,
    config: dict,
) -> dict:
    """
    Build complete RangeFader v5 strategy.
    
    Args:
        df: DataFrame with 'price', 'high', 'low' columns
        config: Configuration dictionary
        
    Returns:
        dict: Complete results including daily series and metrics
    """
    print("=" * 80)
    print("RANGEFADER V5 - 4-Layer Build")
    print("=" * 80)
    print(f"Data: {df.index[0]} to {df.index[-1]} ({len(df)} days, {len(df)/252:.1f} years)")
    
    # Extract config
    signal_config = config['signal']
    sizing_config = config['policy']['sizing']
    cost_config = config['policy']['costs']
    
    lookback = signal_config['lookback_window']
    entry = signal_config['zscore_entry']
    exit = signal_config['zscore_exit']
    adx_threshold = signal_config['adx_threshold']
    target_vol = sizing_config['ann_target']
    cost_bps = cost_config['one_way_bps_default']
    
    print(f"\nParameters:")
    print(f"  Lookback: {lookback} days")
    print(f"  Entry: {entry} std")
    print(f"  Exit: {exit} std")
    print(f"  ADX Threshold: {adx_threshold}")
    print(f"  Target Vol: {target_vol*100:.0f}%")
    print(f"  Costs: {cost_bps} bps")
    
    # Layer 1: Generate signal
    print("\n" + "-" * 80)
    print("Layer 1: Signal Generation (OHLC ADX)")
    print("-" * 80)
    
    positions_raw = generate_rangefader_signal(
        df,
        lookback_window=lookback,
        zscore_entry=entry,
        zscore_exit=exit,
        adx_threshold=adx_threshold,
        adx_window=14,
        update_frequency=1,
    )
    
    signal_stats = get_signal_statistics(positions_raw)
    print(f"Signal Stats:")
    print(f"  Active: {signal_stats['pct_active']:.1f}% of days")
    print(f"  Long: {signal_stats['pct_long']:.1f}%, Short: {signal_stats['pct_short']:.1f}%, Flat: {signal_stats['pct_flat']:.1f}%")
    print(f"  Mean: {signal_stats['mean']:+.3f}, Std: {signal_stats['std']:.3f}")
    
    # Regime statistics
    regime_stats = get_regime_statistics(df, adx_threshold=adx_threshold)
    print(f"\nRegime Distribution:")
    print(f"  Choppy (ADX < {adx_threshold}): {regime_stats['choppy_pct']:.1f}%")
    print(f"  Weak Trend (ADX {adx_threshold}-25): {regime_stats['weak_trend_pct']:.1f}%")
    print(f"  Strong Trend (ADX >= 25): {regime_stats['strong_trend_pct']:.1f}%")
    
    # Layer 2: Vol targeting
    print("\n" + "-" * 80)
    print("Layer 2: Volatility Targeting")
    print("-" * 80)
    
    returns = df['price'].pct_change()
    positions_targeted = apply_vol_targeting(
        positions_raw,
        returns,
        target_vol=target_vol,
        vol_window=sizing_config['vol_lookback_days_default'],
        leverage_cap=sizing_config['leverage_cap_default'],
    )
    
    # Calculate realized vol
    strat_returns_gross = positions_targeted.shift(1) * returns
    realized_vol = strat_returns_gross.std() * np.sqrt(252)
    
    print(f"Vol Targeting:")
    print(f"  Target: {target_vol*100:.1f}%")
    print(f"  Realized: {realized_vol*100:.2f}%")
    print(f"  Delta: {(realized_vol - target_vol)*100:+.2f}%")
    print(f"  Within 3%: {'✓ YES' if abs(realized_vol - target_vol) < 0.03 else '✗ NO'}")
    
    # Layer 4: Costs
    print("\n" + "-" * 80)
    print("Layer 4: Execution & Costs")
    print("-" * 80)
    
    costs = calculate_costs(positions_targeted, cost_bps=cost_bps)
    
    turnover = positions_targeted.diff().abs().sum()
    annual_turnover = turnover / (len(df) / 252)
    total_cost = costs.sum()
    annual_cost = total_cost / (len(df) / 252)
    
    print(f"Turnover:")
    print(f"  Total: {turnover:.1f}x")
    print(f"  Annual: {annual_turnover:.1f}x")
    print(f"  Annual Cost: {annual_cost*100:.3f}%")
    
    # Net PnL
    pnl_gross = strat_returns_gross
    pnl_net = strat_returns_gross - costs
    
    # Performance metrics
    print("\n" + "-" * 80)
    print("Performance Summary")
    print("-" * 80)
    
    gross_sharpe = (pnl_gross.mean() / pnl_gross.std()) * np.sqrt(252)
    net_sharpe = (pnl_net.mean() / pnl_net.std()) * np.sqrt(252)
    
    ann_return_net = pnl_net.mean() * 252
    ann_vol_net = pnl_net.std() * np.sqrt(252)
    
    cum_returns = (1 + pnl_net).cumprod()
    max_dd = (cum_returns / cum_returns.cummax() - 1).min()
    
    print(f"Overall:")
    print(f"  Gross Sharpe: {gross_sharpe:.3f}")
    print(f"  Net Sharpe: {net_sharpe:.3f}")
    print(f"  Annual Return: {ann_return_net*100:+.2f}%")
    print(f"  Annual Vol: {ann_vol_net*100:.2f}%")
    print(f"  Max Drawdown: {max_dd*100:.2f}%")
    
    # Regime-specific performance
    from src.signals.rangefader_v5 import calculate_adx_ohlc
    adx = calculate_adx_ohlc(df['high'], df['low'], df['price'], window=14)
    choppy_mask = adx < adx_threshold
    
    choppy_returns = pnl_net[choppy_mask]
    choppy_sharpe = (choppy_returns.mean() / choppy_returns.std()) * np.sqrt(252) if len(choppy_returns) > 0 else 0
    
    print(f"\nChoppy Markets (ADX < {adx_threshold}):")
    print(f"  Sharpe: {choppy_sharpe:.3f}")
    print(f"  % of Time: {choppy_mask.mean()*100:.1f}%")
    
    # Validation
    print("\n" + "-" * 80)
    print("Regime Validation")
    print("-" * 80)
    
    validation = validate_regime_behavior(
        df,
        positions_raw,
        adx_threshold=adx_threshold,
        verbose=False,
    )
    
    print(f"Activity in Choppy: {validation['activity_in_choppy']*100:.1f}% ({'✓ PASS' if validation['pass_choppy_activity'] else '✗ FAIL'})")
    print(f"Activity in Trending: {validation['activity_in_trending']*100:.1f}% ({'✓ PASS' if validation['pass_trending_activity'] else '✗ FAIL'})")
    print(f"Correlation(|pos|, ADX): {validation['correlation_pos_adx']:+.3f} ({'✓ PASS' if validation['pass_correlation'] else '✗ FAIL'})")
    print(f"Overall: {'✓✓ ALL PASSED' if validation['all_passed'] else '✗✗ SOME FAILED'}")
    
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

    
    # Build daily series
    daily_series = pd.DataFrame({
        'date': df.index,
        'price': df['price'],
        'high': df['high'],
        'low': df['low'],
        'ret': returns,
        'pos_raw': positions_raw,
        'pos': positions_targeted,
        'pnl_gross': pnl_gross,
        'costs': costs,
        'pnl_net': pnl_net,
    })
    
    # Build summary
    summary = {
        'build_date': datetime.now().isoformat(),
        'data_period': f"{df.index[0]} to {df.index[-1]}",
        'n_days': len(df),
        'n_years': len(df) / 252,
        'parameters': {
            'lookback_window': lookback,
            'zscore_entry': entry,
            'zscore_exit': exit,
            'adx_threshold': adx_threshold,
            'target_vol': target_vol,
            'cost_bps': cost_bps,
        },
        'performance': {
            'gross_sharpe': float(gross_sharpe),
            'net_sharpe': float(net_sharpe),
            'annual_return': float(ann_return_net),
            'annual_vol': float(ann_vol_net),
            'max_drawdown': float(max_dd),
            'choppy_sharpe': float(choppy_sharpe),
            'choppy_pct_time': float(choppy_mask.mean() * 100),
        },
        'turnover': {
            'total_turnover': float(turnover),
            'annual_turnover': float(annual_turnover),
            'annual_cost': float(annual_cost),
        },
        'validation': convert_to_native(validation),
        'regime_stats': convert_to_native(regime_stats),
    }
    
    return {
        'daily_series': daily_series,
        'summary': summary,
    }


def main():
    parser = argparse.ArgumentParser(description='Build RangeFader v5 strategy')
    parser.add_argument('--csv-close', required=True, help='Path to close price CSV')
    parser.add_argument('--csv-high', required=True, help='Path to high price CSV')
    parser.add_argument('--csv-low', required=True, help='Path to low price CSV')
    parser.add_argument('--config', required=True, help='Path to config YAML')
    parser.add_argument('--outdir', required=True, help='Output directory')
    
    args = parser.parse_args()
    
    # Load config
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
    
    # Load data
    print("Loading OHLC data...")
    df_close = pd.read_csv(args.csv_close, parse_dates=['date'], index_col='date')
    df_high = pd.read_csv(args.csv_high, parse_dates=['date'], index_col='date')
    df_low = pd.read_csv(args.csv_low, parse_dates=['date'], index_col='date')
    
    df = pd.DataFrame({
        'price': df_close['price'],
        'high': df_high['price'],
        'low': df_low['price'],
    }).dropna()
    
    # Build strategy
    results = build_rangefader_v5(df, config)
    
    # Save outputs
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    
    results['daily_series'].to_csv(outdir / 'daily_series.csv', index=False)
    
    with open(outdir / 'summary_metrics.json', 'w') as f:
        json.dump(results['summary'], f, indent=2)
    
    print(f"\n{'=' * 80}")
    print(f"BUILD COMPLETE")
    print(f"{'=' * 80}")
    print(f"\nOutputs saved to: {outdir}")
    print(f"  • daily_series.csv")
    print(f"  • summary_metrics.json")


if __name__ == "__main__":
    main()