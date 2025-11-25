#!/usr/bin/env python3
"""
Build Baseline + VolCore Portfolio v2 - IS/OOS VALIDATED
=========================================================
Renaissance-style methodology:
  1. IS (2011-2018): Grid search for optimal BL/VC weights
  2. OOS (2019-2025): Apply IS weights FROZEN, validate

Tests marginal contribution of VolCore to baseline portfolio
with proper forward-bias-free validation.

Usage:
  python build_baseline_volcore_v2.py --config path/to/config.yaml
"""

import argparse
import json
import yaml
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime


def load_config(config_path: str) -> dict:
    """Load YAML configuration"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def load_sleeve(sleeve_config: dict, base_path: Path) -> pd.DataFrame:
    """Load a sleeve's daily series"""
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
    """Calculate annualized Sharpe ratio"""
    pnl = pnl_series.dropna()
    if len(pnl) == 0 or pnl.std() == 0:
        return 0.0
    return (pnl.mean() * periods_per_year) / (pnl.std() * np.sqrt(periods_per_year))


def calculate_metrics(pnl_series: pd.Series, label: str = "Portfolio") -> dict:
    """Calculate comprehensive performance metrics"""
    pnl = pnl_series.dropna()
    
    if len(pnl) == 0:
        return {'label': label, 'sharpe': 0.0, 'annual_return': 0.0, 
                'annual_vol': 0.0, 'max_drawdown': 0.0, 'days': 0}
    
    cum_returns = (1 + pnl).cumprod()
    sharpe = calculate_sharpe(pnl)
    total_return = cum_returns.iloc[-1] - 1
    annual_return = (1 + total_return) ** (252 / len(pnl)) - 1
    annual_vol = pnl.std() * np.sqrt(252)
    
    cum_max = cum_returns.cummax()
    drawdown = (cum_returns - cum_max) / cum_max
    max_dd = drawdown.min()
    
    return {
        'label': label,
        'sharpe': float(sharpe),
        'annual_return': float(annual_return),
        'annual_vol': float(annual_vol),
        'max_drawdown': float(max_dd),
        'days': int(len(pnl))
    }


def blend_pnls(bl_pnl: pd.Series, vc_pnl: pd.Series, bl_weight: float) -> pd.Series:
    """Blend two PnL series"""
    vc_weight = 1.0 - bl_weight
    return bl_pnl.fillna(0) * bl_weight + vc_pnl.fillna(0) * vc_weight


def grid_search_weights(bl_pnl: pd.Series, vc_pnl: pd.Series, step: float = 0.05) -> tuple:
    """
    Grid search for optimal baseline weight.
    
    Returns: (best_bl_weight, best_sharpe, all_results)
    """
    weight_range = np.arange(0.0, 1.0 + step, step)
    
    best_sharpe = -np.inf
    best_bl_weight = 0.5
    all_results = []
    
    for bl_weight in weight_range:
        blended = blend_pnls(bl_pnl, vc_pnl, bl_weight)
        sharpe = calculate_sharpe(blended)
        
        all_results.append({
            'baseline_weight': bl_weight,
            'volcore_weight': 1.0 - bl_weight,
            'sharpe': sharpe
        })
        
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_bl_weight = bl_weight
    
    return best_bl_weight, best_sharpe, all_results


def main():
    parser = argparse.ArgumentParser(description='Build Baseline + VolCore v2 (IS/OOS validated)')
    parser.add_argument('--config', required=True, help='Path to config YAML')
    
    args = parser.parse_args()
    
    print("="*80)
    print("BASELINE + VOLCORE v2 - IS/OOS VALIDATED")
    print("="*80)
    print()
    
    # Load configuration
    config = load_config(args.config)
    base_path = Path(config.get('base_path', '.'))
    
    is_start = pd.Timestamp(config.get('is_start_date', '2000-01-01'))  # Optional IS start
    is_cutoff = pd.Timestamp(config['is_oos_cutoff'])
    grid_step = config.get('grid_step', 0.05)
    
    # Discount factor for reduced-confidence allocations
    allocation_discount = config.get('allocation_discount', 1.0)
    discount_reason = config.get('discount_reason', None)
    
    print(f"IS start: {is_start.date()}")
    print(f"IS/OOS cutoff: {is_cutoff.date()}")
    print(f"Grid step: {grid_step:.0%}")
    if allocation_discount < 1.0:
        print(f"Allocation discount: {allocation_discount:.0%} ({discount_reason})")
    print()
    
    # Load sleeves
    print("-"*80)
    print("LOADING SLEEVES")
    print("-"*80)
    
    baseline = load_sleeve(config['components']['baseline'], base_path)
    volcore = load_sleeve(config['components']['volcore'], base_path)
    
    print(f"Baseline: {len(baseline)} days")
    print(f"VolCore: {len(volcore)} days")
    
    # Align dates
    common_dates = baseline.index.intersection(volcore.index)
    print(f"Common dates: {len(common_dates)}")
    print(f"Range: {common_dates.min().date()} to {common_dates.max().date()}")
    
    bl_pnl = baseline.loc[common_dates, 'pnl_gross']
    vc_pnl = volcore.loc[common_dates, 'pnl_gross']
    
    # Split IS/OOS (with optional IS start date)
    is_dates = common_dates[(common_dates >= is_start) & (common_dates < is_cutoff)]
    oos_dates = common_dates[common_dates >= is_cutoff]
    
    print(f"\nIS: {is_dates.min().date()} to {is_dates.max().date()} ({len(is_dates)} days)")
    print(f"OOS: {oos_dates.min().date()} to {oos_dates.max().date()} ({len(oos_dates)} days)")
    print()
    
    # IS PnLs
    is_bl_pnl = bl_pnl.loc[is_dates]
    is_vc_pnl = vc_pnl.loc[is_dates]
    
    # OOS PnLs
    oos_bl_pnl = bl_pnl.loc[oos_dates]
    oos_vc_pnl = vc_pnl.loc[oos_dates]
    
    # =========================================================================
    # PHASE 1: IS WEIGHT OPTIMIZATION
    # =========================================================================
    print("-"*80)
    print("PHASE 1: IN-SAMPLE WEIGHT OPTIMIZATION")
    print("-"*80)
    
    # Standalone IS performance
    is_bl_sharpe = calculate_sharpe(is_bl_pnl)
    is_vc_sharpe = calculate_sharpe(is_vc_pnl)
    
    print(f"IS Standalone - Baseline: {is_bl_sharpe:.3f} Sharpe")
    print(f"IS Standalone - VolCore: {is_vc_sharpe:.3f} Sharpe")
    print()
    
    # Grid search on IS
    best_bl_weight, is_best_sharpe, is_results = grid_search_weights(
        is_bl_pnl, is_vc_pnl, step=grid_step
    )
    best_vc_weight = 1.0 - best_bl_weight
    
    print(f"IS Optimal Weights:")
    print(f"  Baseline: {best_bl_weight:.0%}")
    print(f"  VolCore:  {best_vc_weight:.0%}")
    print(f"IS Best Sharpe: {is_best_sharpe:.3f}")
    
    # Apply allocation discount if specified
    if allocation_discount < 1.0:
        raw_vc_weight = best_vc_weight
        best_vc_weight = best_vc_weight * allocation_discount
        best_bl_weight = 1.0 - best_vc_weight
        print(f"\nAfter {allocation_discount:.0%} discount ({discount_reason}):")
        print(f"  Baseline: {best_bl_weight:.0%}")
        print(f"  VolCore:  {best_vc_weight:.0%} (was {raw_vc_weight:.0%})")
    
    # Marginal contribution in IS
    is_marginal = is_best_sharpe - is_bl_sharpe
    print(f"IS Marginal (vs BL alone): {is_marginal:+.3f}")
    print()
    
    # Correlation in IS
    is_correlation = is_bl_pnl.corr(is_vc_pnl)
    print(f"IS Correlation: {is_correlation:.3f}")
    
    # =========================================================================
    # PHASE 2: OOS VALIDATION (FROZEN WEIGHTS)
    # =========================================================================
    print()
    print("-"*80)
    print("PHASE 2: OUT-OF-SAMPLE VALIDATION")
    print("-"*80)
    print(f"Applying IS weights FROZEN to OOS...")
    print()
    
    # Standalone OOS performance
    oos_bl_sharpe = calculate_sharpe(oos_bl_pnl)
    oos_vc_sharpe = calculate_sharpe(oos_vc_pnl)
    
    print(f"OOS Standalone - Baseline: {oos_bl_sharpe:.3f} Sharpe")
    print(f"OOS Standalone - VolCore: {oos_vc_sharpe:.3f} Sharpe")
    print()
    
    # Apply frozen IS weights to OOS
    oos_blended = blend_pnls(oos_bl_pnl, oos_vc_pnl, best_bl_weight)
    oos_sharpe = calculate_sharpe(oos_blended)
    
    print(f"OOS Weights (from IS):")
    print(f"  Baseline: {best_bl_weight:.0%}")
    print(f"  VolCore:  {best_vc_weight:.0%}")
    print(f"OOS Portfolio Sharpe: {oos_sharpe:.3f}")
    
    # OOS marginal
    oos_marginal = oos_sharpe - oos_bl_sharpe
    print(f"OOS Marginal (vs BL alone): {oos_marginal:+.3f}")
    
    # Correlation in OOS
    oos_correlation = oos_bl_pnl.corr(oos_vc_pnl)
    print(f"OOS Correlation: {oos_correlation:.3f}")
    
    # =========================================================================
    # VALIDATION SUMMARY
    # =========================================================================
    print()
    print("="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    
    # Degradation
    if is_best_sharpe > 0:
        degradation = (oos_sharpe - is_best_sharpe) / is_best_sharpe
    else:
        degradation = 0
    
    print(f"\n{'Metric':<30} {'IS':>10} {'OOS':>10}")
    print("-"*52)
    print(f"{'Baseline Sharpe':<30} {is_bl_sharpe:>10.3f} {oos_bl_sharpe:>10.3f}")
    print(f"{'VolCore Sharpe':<30} {is_vc_sharpe:>10.3f} {oos_vc_sharpe:>10.3f}")
    print(f"{'Portfolio Sharpe':<30} {is_best_sharpe:>10.3f} {oos_sharpe:>10.3f}")
    print(f"{'Marginal (vs BL)':<30} {is_marginal:>+10.3f} {oos_marginal:>+10.3f}")
    print(f"{'Correlation':<30} {is_correlation:>10.3f} {oos_correlation:>10.3f}")
    print()
    print(f"IS→OOS Degradation: {degradation:+.1%}")
    
    # Validation status
    if oos_sharpe >= is_best_sharpe * 0.80:
        status = "PASS"
        print(f"\n✓ PASS - OOS retains ≥80% of IS performance")
    elif oos_sharpe >= is_best_sharpe * 0.60:
        status = "MARGINAL"
        print(f"\n⚠ MARGINAL - OOS retains 60-80% of IS")
    else:
        status = "FAIL"
        print(f"\n✗ FAIL - OOS retains <60% of IS")
    
    # VolCore value-add check
    print()
    if oos_marginal > 0.05:
        print(f"✓ VolCore adds significant value in OOS (+{oos_marginal:.3f} Sharpe)")
        vc_recommendation = "INCLUDE"
    elif oos_marginal > 0:
        print(f"~ VolCore adds marginal value in OOS (+{oos_marginal:.3f} Sharpe)")
        vc_recommendation = "CONSIDER"
    else:
        print(f"✗ VolCore does not add value in OOS ({oos_marginal:+.3f} Sharpe)")
        vc_recommendation = "EXCLUDE"
    
    # =========================================================================
    # SAVE OUTPUTS
    # =========================================================================
    print()
    print("-"*80)
    print("SAVING OUTPUTS")
    print("-"*80)
    
    # Create timestamped output directory
    base_outdir = Path(config['output_dir'])
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    outdir = base_outdir / timestamp
    outdir.mkdir(parents=True, exist_ok=True)
    
    # Also create/update 'latest' symlink/copy
    latest_dir = base_outdir / 'latest'
    
    # Daily series
    daily_df = pd.DataFrame({
        'date': common_dates,
        'baseline_pnl': bl_pnl.values,
        'volcore_pnl': vc_pnl.values,
        'portfolio_pnl': blend_pnls(bl_pnl, vc_pnl, best_bl_weight).values,
        'baseline_weight': best_bl_weight,
        'volcore_weight': best_vc_weight,
        'is_period': common_dates < is_cutoff
    })
    daily_df.to_csv(outdir / 'daily_series.csv', index=False)
    print(f"✓ daily_series.csv")
    
    # Validation summary
    validation = {
        'generated': datetime.now().isoformat(),
        'methodology': 'IS optimization, OOS validation (weights frozen)',
        'is_start': str(is_start.date()),
        'is_cutoff': str(is_cutoff.date()),
        'optimal_weights_raw': {
            'baseline': 1.0 - (best_vc_weight / allocation_discount) if allocation_discount < 1.0 else best_bl_weight,
            'volcore': best_vc_weight / allocation_discount if allocation_discount < 1.0 else best_vc_weight
        },
        'allocation_discount': {
            'factor': allocation_discount,
            'reason': discount_reason,
            'applied': allocation_discount < 1.0
        },
        'optimal_weights_final': {
            'baseline': best_bl_weight,
            'volcore': best_vc_weight
        },
        'is_metrics': {
            'baseline_sharpe': is_bl_sharpe,
            'volcore_sharpe': is_vc_sharpe,
            'portfolio_sharpe': is_best_sharpe,
            'marginal': is_marginal,
            'correlation': is_correlation
        },
        'oos_metrics': {
            'baseline_sharpe': oos_bl_sharpe,
            'volcore_sharpe': oos_vc_sharpe,
            'portfolio_sharpe': oos_sharpe,
            'marginal': oos_marginal,
            'correlation': oos_correlation
        },
        'validation': {
            'degradation_pct': degradation,
            'status': status,
            'volcore_recommendation': vc_recommendation
        }
    }
    
    with open(outdir / 'validation_summary.json', 'w') as f:
        json.dump(validation, f, indent=2)
    print(f"✓ validation_summary.json")
    
    # Weight comparison (all tested)
    with open(outdir / 'weight_comparison.json', 'w') as f:
        json.dump({'is_grid_results': is_results}, f, indent=2)
    print(f"✓ weight_comparison.json")
    
    # Copy to 'latest'
    import shutil
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    shutil.copytree(outdir, latest_dir)
    print(f"✓ Copied to latest/")
    
    print()
    print("="*80)
    print("BUILD COMPLETE")
    print("="*80)
    print(f"\nOutputs: {outdir}")
    print(f"Latest:  {latest_dir}")
    print(f"\nResult: {status}")
    print(f"  IS Sharpe:  {is_best_sharpe:.3f}")
    print(f"  OOS Sharpe: {oos_sharpe:.3f}")
    if allocation_discount < 1.0:
        print(f"  Raw weights: {1.0 - (best_vc_weight / allocation_discount):.0%} BL / {best_vc_weight / allocation_discount:.0%} VC")
        print(f"  After {allocation_discount:.0%} discount: {best_bl_weight:.0%} BL / {best_vc_weight:.0%} VC")
        print(f"  Discount reason: {discount_reason}")
    else:
        print(f"  Weights: {best_bl_weight:.0%} BL / {best_vc_weight:.0%} VC")
    print(f"  VolCore: {vc_recommendation}")


if __name__ == '__main__':
    main()