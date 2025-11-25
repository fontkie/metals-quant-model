#!/usr/bin/env python3
"""
Build Portfolio: Baseline Layer4 Demand + TightStocks + VolCore
================================================================
This script applies PRE-DETERMINED weights (not optimized) and reports
IS/OOS performance for the production portfolio.

Architecture:
  70% - Baseline with Copper Demand Overlay (Core 3 with Layer 4)
  25% - TightStocks v2 (supply-side fundamental - independent)
  05% - VolCore v2 (vol risk premium - independent)

Cost Methodology:
  All sleeves provide GROSS PnL.
  Costs applied once at portfolio level on |delta_position|.

Usage:
  python build_baseline_layer4_demand.py --config path/to/config.yaml
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
    """Load a sleeve's daily series and extract position/pnl columns."""
    file_path = base_path / sleeve_config['path']
    
    if not file_path.exists():
        raise FileNotFoundError(f"Sleeve file not found: {file_path}")
    
    df = pd.read_csv(file_path, parse_dates=['date'])
    df.set_index('date', inplace=True)
    
    pos_col = sleeve_config.get('position_col', 'pos')
    pnl_col = sleeve_config.get('pnl_col', 'pnl_gross')
    
    # Handle case where column might not exist
    if pos_col not in df.columns:
        raise KeyError(f"Position column '{pos_col}' not found. Available: {list(df.columns)}")
    if pnl_col not in df.columns:
        raise KeyError(f"PnL column '{pnl_col}' not found. Available: {list(df.columns)}")
    
    result = df[[pos_col, pnl_col]].copy()
    result.columns = ['position', 'pnl_gross']
    
    return result


def calculate_sharpe(pnl_series: pd.Series, periods_per_year: int = 252) -> float:
    """Calculate annualized Sharpe ratio."""
    pnl = pnl_series.dropna()
    if len(pnl) == 0 or pnl.std() == 0:
        return 0.0
    return (pnl.mean() * periods_per_year) / (pnl.std() * np.sqrt(periods_per_year))


def calculate_metrics(pnl_series: pd.Series) -> dict:
    """Calculate comprehensive performance metrics."""
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


def apply_transaction_costs(positions: pd.Series, cost_bps: float) -> pd.Series:
    """Calculate transaction costs on position changes."""
    trades = positions.diff().abs()
    costs = -trades * (cost_bps / 10000)
    return costs.fillna(0)


def main():
    parser = argparse.ArgumentParser(description='Build Baseline Layer4 Demand Portfolio')
    parser.add_argument('--config', required=True, help='Path to config YAML')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("BASELINE LAYER4 DEMAND + TIGHTSTOCKS + VOLCORE")
    print("=" * 80)
    print()
    print("Architecture:")
    print("  70% Baseline with Demand Overlay (Core 3 + Layer 4)")
    print("  25% TightStocks v2 (supply-side, independent)")
    print("  05% VolCore v2 (vol premium, independent)")
    print()
    print("Costs applied at portfolio level (GROSS PnL from all sleeves)")
    print()
    
    # Load configuration
    config = load_config(args.config)
    base_path = Path(config.get('base_path', '.'))
    
    # Fixed weights
    weights = config['fixed_weights']
    is_cutoff = pd.Timestamp(config['is_oos_cutoff'])
    cost_bps = config.get('transaction_cost_bps', 3)
    
    print(f"Fixed Weights:")
    for name, wt in weights.items():
        print(f"  {name}: {wt:.0%}")
    print(f"\nIS/OOS cutoff: {is_cutoff.date()}")
    print(f"Transaction costs: {cost_bps} bps one-way")
    print()
    
    # Load sleeves
    print("-" * 80)
    print("LOADING SLEEVES")
    print("-" * 80)
    
    sleeves = {}
    for name, sleeve_config in config['components'].items():
        print(f"Loading {name}...")
        try:
            sleeves[name] = load_sleeve(sleeve_config, base_path)
            print(f"  Range: {sleeves[name].index.min().date()} to {sleeves[name].index.max().date()}")
            print(f"  Days: {len(sleeves[name])}")
        except Exception as e:
            print(f"  ERROR: {e}")
            raise
    
    # Find common dates (when ALL sleeves have data)
    common_dates = sleeves['baseline_demand'].index
    for name, df in sleeves.items():
        common_dates = common_dates.intersection(df.index)
    
    print(f"\nCommon dates (all sleeves): {len(common_dates)}")
    print(f"Range: {common_dates.min().date()} to {common_dates.max().date()}")
    
    # Extract positions and PnLs on common dates
    pos_dict = {name: df.loc[common_dates, 'position'] for name, df in sleeves.items()}
    pnl_dict = {name: df.loc[common_dates, 'pnl_gross'] for name, df in sleeves.items()}
    
    # Split IS/OOS
    is_dates = common_dates[common_dates < is_cutoff]
    oos_dates = common_dates[common_dates >= is_cutoff]
    
    print(f"\nIS: {is_dates.min().date()} to {is_dates.max().date()} ({len(is_dates)} days)")
    print(f"OOS: {oos_dates.min().date()} to {oos_dates.max().date()} ({len(oos_dates)} days)")
    
    # Build blended portfolio position
    portfolio_pos = pd.Series(0.0, index=common_dates)
    for name, wt in weights.items():
        portfolio_pos += pos_dict[name].fillna(0) * wt
    
    # Build blended portfolio GROSS PnL (before costs)
    portfolio_pnl_gross = pd.Series(0.0, index=common_dates)
    for name, wt in weights.items():
        portfolio_pnl_gross += pnl_dict[name].fillna(0) * wt
    
    # Apply transaction costs at portfolio level
    portfolio_costs = apply_transaction_costs(portfolio_pos, cost_bps)
    portfolio_pnl_net = portfolio_pnl_gross + portfolio_costs
    
    # Calculate metrics
    print()
    print("=" * 80)
    print("PERFORMANCE RESULTS")
    print("=" * 80)
    
    # Individual sleeves (gross)
    print(f"\n{'SLEEVE PERFORMANCE (Gross)':<40} {'IS':>12} {'OOS':>12}")
    print("-" * 65)
    
    for name in weights.keys():
        is_sharpe = calculate_sharpe(pnl_dict[name].loc[is_dates])
        oos_sharpe = calculate_sharpe(pnl_dict[name].loc[oos_dates])
        print(f"{name:<40} {is_sharpe:>12.3f} {oos_sharpe:>12.3f}")
    
    # Portfolio metrics
    is_pnl_gross = portfolio_pnl_gross.loc[is_dates]
    is_pnl_net = portfolio_pnl_net.loc[is_dates]
    oos_pnl_gross = portfolio_pnl_gross.loc[oos_dates]
    oos_pnl_net = portfolio_pnl_net.loc[oos_dates]
    
    is_metrics_gross = calculate_metrics(is_pnl_gross)
    is_metrics_net = calculate_metrics(is_pnl_net)
    oos_metrics_gross = calculate_metrics(oos_pnl_gross)
    oos_metrics_net = calculate_metrics(oos_pnl_net)
    full_metrics_net = calculate_metrics(portfolio_pnl_net)
    
    print("-" * 65)
    print(f"{'PORTFOLIO (Gross)':<40} {is_metrics_gross['sharpe']:>12.3f} {oos_metrics_gross['sharpe']:>12.3f}")
    print(f"{'PORTFOLIO (Net, 3bps)':<40} {is_metrics_net['sharpe']:>12.3f} {oos_metrics_net['sharpe']:>12.3f}")
    
    # Degradation
    if is_metrics_net['sharpe'] > 0:
        degradation = (oos_metrics_net['sharpe'] - is_metrics_net['sharpe']) / is_metrics_net['sharpe']
    else:
        degradation = 0
    
    print()
    print("-" * 65)
    print(f"IS→OOS Degradation (Net): {degradation:+.1%}")
    
    # Validation status
    if oos_metrics_net['sharpe'] >= is_metrics_net['sharpe'] * 0.80:
        status = "PASS"
        print(f"\n✓ PASS - OOS retains ≥80% of IS performance")
    elif oos_metrics_net['sharpe'] >= is_metrics_net['sharpe'] * 0.60:
        status = "MARGINAL"
        print(f"\n⚠ MARGINAL - OOS retains 60-80% of IS")
    else:
        status = "FAIL"
        print(f"\n✗ FAIL - OOS retains <60% of IS")
    
    # Correlation matrix
    print()
    print("-" * 65)
    print("CORRELATION MATRIX (Full Period, Gross PnL)")
    print("-" * 65)
    corr_df = pd.DataFrame({name: pnl_dict[name] for name in weights.keys()}).corr()
    print(corr_df.round(3).to_string())
    
    # Additional metrics
    print()
    print("-" * 65)
    print("ADDITIONAL METRICS (Net)")
    print("-" * 65)
    print(f"{'Metric':<30} {'IS':>15} {'OOS':>15}")
    print(f"{'Annual Return':<30} {is_metrics_net['annual_return']:>14.1%} {oos_metrics_net['annual_return']:>14.1%}")
    print(f"{'Annual Volatility':<30} {is_metrics_net['annual_vol']:>14.1%} {oos_metrics_net['annual_vol']:>14.1%}")
    print(f"{'Max Drawdown':<30} {is_metrics_net['max_drawdown']:>14.1%} {oos_metrics_net['max_drawdown']:>14.1%}")
    
    # Transaction cost impact
    total_costs_is = portfolio_costs.loc[is_dates].sum()
    total_costs_oos = portfolio_costs.loc[oos_dates].sum()
    print()
    print(f"{'Total Transaction Costs':<30} {total_costs_is*100:>14.2f}% {total_costs_oos*100:>14.2f}%")
    
    # Save outputs
    print()
    print("-" * 80)
    print("SAVING OUTPUTS")
    print("-" * 80)
    
    base_outdir = Path(config['output_dir'])
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    outdir = base_outdir / timestamp
    outdir.mkdir(parents=True, exist_ok=True)
    latest_dir = base_outdir / 'latest'
    
    # Daily series
    daily_df = pd.DataFrame({
        'date': common_dates,
        'baseline_demand_pos': pos_dict['baseline_demand'].values,
        'tightstocks_pos': pos_dict['tightstocks'].values,
        'volcore_pos': pos_dict['volcore'].values,
        'portfolio_pos': portfolio_pos.values,
        'baseline_demand_pnl_gross': pnl_dict['baseline_demand'].values,
        'tightstocks_pnl_gross': pnl_dict['tightstocks'].values,
        'volcore_pnl_gross': pnl_dict['volcore'].values,
        'portfolio_pnl_gross': portfolio_pnl_gross.values,
        'portfolio_costs': portfolio_costs.values,
        'portfolio_pnl_net': portfolio_pnl_net.values,
        'is_period': common_dates < is_cutoff
    })
    for name, wt in weights.items():
        daily_df[f'{name}_weight'] = wt
    daily_df.to_csv(outdir / 'daily_series.csv', index=False)
    print(f"✓ daily_series.csv")
    
    # Validation summary
    validation = {
        'generated': datetime.now().isoformat(),
        'methodology': 'Fixed weights with costs at portfolio level',
        'architecture': {
            'baseline_demand': 'Core 3 (TM/MC/RF) with demand overlay - 70%',
            'tightstocks': 'Supply-side fundamental (independent) - 25%',
            'volcore': 'Vol risk premium (independent) - 5%'
        },
        'is_cutoff': str(is_cutoff.date()),
        'transaction_cost_bps': cost_bps,
        'fixed_weights': weights,
        'weight_sources': config.get('weight_sources', {}),
        'is_metrics': {
            'portfolio_sharpe_gross': is_metrics_gross['sharpe'],
            'portfolio_sharpe_net': is_metrics_net['sharpe'],
            'annual_return': is_metrics_net['annual_return'],
            'annual_vol': is_metrics_net['annual_vol'],
            'max_drawdown': is_metrics_net['max_drawdown'],
            'days': is_metrics_net['days'],
            'sleeves_gross': {name: calculate_sharpe(pnl_dict[name].loc[is_dates]) 
                             for name in weights.keys()}
        },
        'oos_metrics': {
            'portfolio_sharpe_gross': oos_metrics_gross['sharpe'],
            'portfolio_sharpe_net': oos_metrics_net['sharpe'],
            'annual_return': oos_metrics_net['annual_return'],
            'annual_vol': oos_metrics_net['annual_vol'],
            'max_drawdown': oos_metrics_net['max_drawdown'],
            'days': oos_metrics_net['days'],
            'sleeves_gross': {name: calculate_sharpe(pnl_dict[name].loc[oos_dates]) 
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
    print("=" * 80)
    print("BASELINE LAYER4 DEMAND PORTFOLIO COMPLETE")
    print("=" * 80)
    print(f"\nWeights: {' / '.join(f'{name}={wt:.0%}' for name, wt in weights.items())}")
    print(f"\nIS Sharpe (Net):  {is_metrics_net['sharpe']:.3f}")
    print(f"OOS Sharpe (Net): {oos_metrics_net['sharpe']:.3f}")
    print(f"Status:           {status}")
    print(f"\nOutputs: {outdir}")


if __name__ == '__main__':
    main()