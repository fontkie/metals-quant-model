#!/usr/bin/env python3
"""
Validate Final Portfolio with Fixed Weights
============================================
This script applies PRE-DETERMINED weights (not optimized) and reports
IS/OOS performance for the final production portfolio.

Weights were derived from separate validated tests:
- TightStocks: 25% (validated IS 2011-2018, OOS 2019-2025)
- VolCore: 5% (validated IS 2017-2020, with 50% discount)
- Baseline: 70% (remainder)

This script just applies those weights and reports combined performance.

Usage:
  python validate_final_portfolio.py --config path/to/config.yaml
"""

import argparse
import json
import yaml
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime


def load_config(config_path: str) -> dict:
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def load_sleeve(sleeve_config: dict, base_path: Path) -> pd.DataFrame:
    file_path = base_path / sleeve_config['path']
    
    if not file_path.exists():
        raise FileNotFoundError(f"Sleeve file not found: {file_path}")
    
    df = pd.read_csv(file_path, parse_dates=['date'])
    df.set_index('date', inplace=True)
    
    pos_col = sleeve_config.get('position_col', 'pos')
    pnl_col = sleeve_config.get('pnl_col', 'pnl_gross')
    
    result = df[[pos_col, pnl_col]].copy()
    result.columns = ['position', 'pnl_gross']
    
    return result


def calculate_sharpe(pnl_series: pd.Series, periods_per_year: int = 252) -> float:
    pnl = pnl_series.dropna()
    if len(pnl) == 0 or pnl.std() == 0:
        return 0.0
    return (pnl.mean() * periods_per_year) / (pnl.std() * np.sqrt(periods_per_year))


def calculate_metrics(pnl_series: pd.Series) -> dict:
    pnl = pnl_series.dropna()
    
    if len(pnl) == 0:
        return {'sharpe': 0.0, 'annual_return': 0.0, 'annual_vol': 0.0, 
                'max_drawdown': 0.0, 'days': 0}
    
    cum_returns = (1 + pnl).cumprod()
    sharpe = calculate_sharpe(pnl)
    total_return = cum_returns.iloc[-1] - 1
    annual_return = (1 + total_return) ** (252 / len(pnl)) - 1
    annual_vol = pnl.std() * np.sqrt(252)
    
    cum_max = cum_returns.cummax()
    drawdown = (cum_returns - cum_max) / cum_max
    max_dd = drawdown.min()
    
    return {
        'sharpe': float(sharpe),
        'annual_return': float(annual_return),
        'annual_vol': float(annual_vol),
        'max_drawdown': float(max_dd),
        'days': int(len(pnl))
    }


def main():
    parser = argparse.ArgumentParser(description='Validate final portfolio with fixed weights')
    parser.add_argument('--config', required=True, help='Path to config YAML')
    
    args = parser.parse_args()
    
    print("="*80)
    print("FINAL PORTFOLIO VALIDATION - FIXED WEIGHTS")
    print("="*80)
    print()
    print("This applies pre-validated weights (NOT optimizing)")
    print()
    
    # Load configuration
    config = load_config(args.config)
    base_path = Path(config.get('base_path', '.'))
    
    # Fixed weights (pre-determined from separate validation)
    weights = config['fixed_weights']
    is_cutoff = pd.Timestamp(config['is_oos_cutoff'])
    
    print(f"Fixed Weights:")
    for name, wt in weights.items():
        print(f"  {name}: {wt:.0%}")
    print(f"\nIS/OOS cutoff: {is_cutoff.date()}")
    print()
    
    # Load sleeves
    print("-"*80)
    print("LOADING SLEEVES")
    print("-"*80)
    
    sleeves = {}
    for name, sleeve_config in config['components'].items():
        print(f"Loading {name}...")
        sleeves[name] = load_sleeve(sleeve_config, base_path)
        print(f"  Range: {sleeves[name].index.min().date()} to {sleeves[name].index.max().date()}")
    
    # Find common dates (when ALL sleeves have data)
    common_dates = sleeves['baseline'].index
    for name, df in sleeves.items():
        common_dates = common_dates.intersection(df.index)
    
    print(f"\nCommon dates (all sleeves): {len(common_dates)}")
    print(f"Range: {common_dates.min().date()} to {common_dates.max().date()}")
    
    # Extract PnLs
    pnl_dict = {name: df.loc[common_dates, 'pnl_gross'] for name, df in sleeves.items()}
    
    # Split IS/OOS
    is_dates = common_dates[common_dates < is_cutoff]
    oos_dates = common_dates[common_dates >= is_cutoff]
    
    print(f"\nIS: {is_dates.min().date()} to {is_dates.max().date()} ({len(is_dates)} days)")
    print(f"OOS: {oos_dates.min().date()} to {oos_dates.max().date()} ({len(oos_dates)} days)")
    
    # Apply fixed weights to create portfolio
    def blend_portfolio(pnl_dict, weights, dates):
        blended = pd.Series(0.0, index=dates)
        for name, wt in weights.items():
            if name in pnl_dict:
                blended += pnl_dict[name].loc[dates].fillna(0) * wt
        return blended
    
    # Calculate portfolio PnL
    is_portfolio = blend_portfolio(pnl_dict, weights, is_dates)
    oos_portfolio = blend_portfolio(pnl_dict, weights, oos_dates)
    full_portfolio = blend_portfolio(pnl_dict, weights, common_dates)
    
    # Calculate metrics
    print()
    print("="*80)
    print("PERFORMANCE RESULTS")
    print("="*80)
    
    # Individual sleeves
    print(f"\n{'SLEEVE PERFORMANCE':<40} {'IS':>12} {'OOS':>12}")
    print("-"*65)
    
    for name in weights.keys():
        is_sharpe = calculate_sharpe(pnl_dict[name].loc[is_dates])
        oos_sharpe = calculate_sharpe(pnl_dict[name].loc[oos_dates])
        print(f"{name:<40} {is_sharpe:>12.3f} {oos_sharpe:>12.3f}")
    
    # Portfolio
    is_metrics = calculate_metrics(is_portfolio)
    oos_metrics = calculate_metrics(oos_portfolio)
    full_metrics = calculate_metrics(full_portfolio)
    
    print("-"*65)
    print(f"{'PORTFOLIO (fixed weights)':<40} {is_metrics['sharpe']:>12.3f} {oos_metrics['sharpe']:>12.3f}")
    
    # Degradation
    if is_metrics['sharpe'] > 0:
        degradation = (oos_metrics['sharpe'] - is_metrics['sharpe']) / is_metrics['sharpe']
    else:
        degradation = 0
    
    print()
    print("-"*65)
    print(f"IS→OOS Degradation: {degradation:+.1%}")
    
    # Validation status
    if oos_metrics['sharpe'] >= is_metrics['sharpe'] * 0.80:
        status = "PASS"
        print(f"\n✓ PASS - OOS retains ≥80% of IS performance")
    elif oos_metrics['sharpe'] >= is_metrics['sharpe'] * 0.60:
        status = "MARGINAL"
        print(f"\n⚠ MARGINAL - OOS retains 60-80% of IS")
    else:
        status = "FAIL"
        print(f"\n✗ FAIL - OOS retains <60% of IS")
    
    # Correlation matrix
    print()
    print("-"*65)
    print("CORRELATION MATRIX (Full Period)")
    print("-"*65)
    corr_df = pd.DataFrame({name: pnl_dict[name] for name in weights.keys()}).corr()
    print(corr_df.round(3).to_string())
    
    # Additional metrics
    print()
    print("-"*65)
    print("ADDITIONAL METRICS")
    print("-"*65)
    print(f"{'Metric':<30} {'IS':>15} {'OOS':>15}")
    print(f"{'Annual Return':<30} {is_metrics['annual_return']:>14.1%} {oos_metrics['annual_return']:>14.1%}")
    print(f"{'Annual Volatility':<30} {is_metrics['annual_vol']:>14.1%} {oos_metrics['annual_vol']:>14.1%}")
    print(f"{'Max Drawdown':<30} {is_metrics['max_drawdown']:>14.1%} {oos_metrics['max_drawdown']:>14.1%}")
    
    # Save outputs
    print()
    print("-"*80)
    print("SAVING OUTPUTS")
    print("-"*80)
    
    base_outdir = Path(config['output_dir'])
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    outdir = base_outdir / timestamp
    outdir.mkdir(parents=True, exist_ok=True)
    latest_dir = base_outdir / 'latest'
    
    # Daily series
    daily_df = pd.DataFrame({
        'date': common_dates,
        'baseline_pnl': pnl_dict['baseline'].values,
        'tightstocks_pnl': pnl_dict['tightstocks'].values,
        'volcore_pnl': pnl_dict['volcore'].values,
        'portfolio_pnl': full_portfolio.values,
        'is_period': common_dates < is_cutoff
    })
    for name, wt in weights.items():
        daily_df[f'{name}_weight'] = wt
    daily_df.to_csv(outdir / 'daily_series.csv', index=False)
    print(f"✓ daily_series.csv")
    
    # Validation summary
    validation = {
        'generated': datetime.now().isoformat(),
        'methodology': 'Fixed weights validation (weights pre-determined, not optimized)',
        'is_cutoff': str(is_cutoff.date()),
        'fixed_weights': weights,
        'weight_sources': config.get('weight_sources', {}),
        'is_metrics': {
            'portfolio_sharpe': is_metrics['sharpe'],
            'annual_return': is_metrics['annual_return'],
            'annual_vol': is_metrics['annual_vol'],
            'max_drawdown': is_metrics['max_drawdown'],
            'days': is_metrics['days'],
            'sleeves': {name: calculate_sharpe(pnl_dict[name].loc[is_dates]) 
                       for name in weights.keys()}
        },
        'oos_metrics': {
            'portfolio_sharpe': oos_metrics['sharpe'],
            'annual_return': oos_metrics['annual_return'],
            'annual_vol': oos_metrics['annual_vol'],
            'max_drawdown': oos_metrics['max_drawdown'],
            'days': oos_metrics['days'],
            'sleeves': {name: calculate_sharpe(pnl_dict[name].loc[oos_dates]) 
                       for name in weights.keys()}
        },
        'validation': {
            'degradation_pct': degradation,
            'status': status
        }
    }
    
    with open(outdir / 'validation_summary.json', 'w') as f:
        json.dump(validation, f, indent=2)
    print(f"✓ validation_summary.json")
    
    # Correlation matrix
    corr_df.to_csv(outdir / 'correlation_matrix.csv')
    print(f"✓ correlation_matrix.csv")
    
    # Copy to latest
    import shutil
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    shutil.copytree(outdir, latest_dir)
    print(f"✓ Copied to latest/")
    
    print()
    print("="*80)
    print("FINAL PORTFOLIO VALIDATION COMPLETE")
    print("="*80)
    print(f"\nWeights: {' / '.join(f'{name}={wt:.0%}' for name, wt in weights.items())}")
    print(f"\nIS Sharpe:  {is_metrics['sharpe']:.3f}")
    print(f"OOS Sharpe: {oos_metrics['sharpe']:.3f}")
    print(f"Status:     {status}")
    print(f"\nOutputs: {outdir}")


if __name__ == '__main__':
    main()