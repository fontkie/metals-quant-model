#!/usr/bin/env python3
"""
Build Baseline + TightStocks + VolCore Portfolio v2 - IS/OOS VALIDATED
=======================================================================
Renaissance-style methodology:
  1. IS (2011-2018): Grid search for optimal BL/TS/VC weights
  2. OOS (2019-2025): Apply IS weights FROZEN, validate

Tests marginal contribution of both overlays vs baseline and vs each
two-way combination, with proper forward-bias-free validation.

Usage:
  python build_baseline_tightstocks_volcore_v2.py --config path/to/config.yaml
"""

import argparse
import json
import yaml
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime
from itertools import product


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


def blend_three_pnls(bl_pnl: pd.Series, ts_pnl: pd.Series, vc_pnl: pd.Series,
                     bl_wt: float, ts_wt: float, vc_wt: float) -> pd.Series:
    """Blend three PnL series with given weights"""
    return (bl_pnl.fillna(0) * bl_wt + 
            ts_pnl.fillna(0) * ts_wt + 
            vc_pnl.fillna(0) * vc_wt)


def grid_search_three_weights(bl_pnl: pd.Series, ts_pnl: pd.Series, vc_pnl: pd.Series,
                               step: float = 0.05) -> tuple:
    """
    Grid search for optimal three-way weights.
    
    Returns: (best_weights, best_sharpe, all_results)
    """
    weight_range = np.arange(0.0, 1.0 + step, step)
    
    best_sharpe = -np.inf
    best_weights = {'baseline': 0.33, 'tightstocks': 0.33, 'volcore': 0.34}
    all_results = []
    
    for bl_wt, ts_wt, vc_wt in product(weight_range, repeat=3):
        # Skip if weights don't sum to ~1.0
        if abs(bl_wt + ts_wt + vc_wt - 1.0) > 0.01:
            continue
        
        blended = blend_three_pnls(bl_pnl, ts_pnl, vc_pnl, bl_wt, ts_wt, vc_wt)
        sharpe = calculate_sharpe(blended)
        
        all_results.append({
            'baseline': bl_wt,
            'tightstocks': ts_wt,
            'volcore': vc_wt,
            'sharpe': sharpe
        })
        
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_weights = {'baseline': bl_wt, 'tightstocks': ts_wt, 'volcore': vc_wt}
    
    return best_weights, best_sharpe, all_results


def find_best_two_way(bl_pnl: pd.Series, ts_pnl: pd.Series, vc_pnl: pd.Series,
                      step: float = 0.05) -> dict:
    """Find best two-way combinations for comparison"""
    weight_range = np.arange(0.0, 1.0 + step, step)
    
    results = {}
    
    # BL + TS (no VC)
    best_bl_ts = -np.inf
    best_bl_ts_wt = 0.5
    for bl_wt in weight_range:
        blended = bl_pnl.fillna(0) * bl_wt + ts_pnl.fillna(0) * (1 - bl_wt)
        sharpe = calculate_sharpe(blended)
        if sharpe > best_bl_ts:
            best_bl_ts = sharpe
            best_bl_ts_wt = bl_wt
    results['bl_ts'] = {'sharpe': best_bl_ts, 'bl': best_bl_ts_wt, 'ts': 1 - best_bl_ts_wt}
    
    # BL + VC (no TS)
    best_bl_vc = -np.inf
    best_bl_vc_wt = 0.5
    for bl_wt in weight_range:
        blended = bl_pnl.fillna(0) * bl_wt + vc_pnl.fillna(0) * (1 - bl_wt)
        sharpe = calculate_sharpe(blended)
        if sharpe > best_bl_vc:
            best_bl_vc = sharpe
            best_bl_vc_wt = bl_wt
    results['bl_vc'] = {'sharpe': best_bl_vc, 'bl': best_bl_vc_wt, 'vc': 1 - best_bl_vc_wt}
    
    return results


def analyze_robustness(all_results: list, best_sharpe: float) -> dict:
    """Analyze weight robustness"""
    if len(all_results) == 0:
        return {'within_1pct': 0, 'within_5pct': 0, 'total': 0}
    
    within_1pct = sum(1 for r in all_results if r['sharpe'] >= best_sharpe * 0.99)
    within_5pct = sum(1 for r in all_results if r['sharpe'] >= best_sharpe * 0.95)
    
    return {
        'within_1pct': within_1pct,
        'within_5pct': within_5pct,
        'total': len(all_results)
    }


def main():
    parser = argparse.ArgumentParser(description='Build BL + TS + VC v2 (IS/OOS validated)')
    parser.add_argument('--config', required=True, help='Path to config YAML')
    
    args = parser.parse_args()
    
    print("="*80)
    print("BASELINE + TIGHTSTOCKS + VOLCORE v2 - IS/OOS VALIDATED")
    print("="*80)
    print()
    
    # Load configuration
    config = load_config(args.config)
    base_path = Path(config.get('base_path', '.'))
    
    is_start = pd.Timestamp(config.get('is_start_date', '2000-01-01'))  # Optional IS start
    is_cutoff = pd.Timestamp(config['is_oos_cutoff'])
    grid_step = config.get('grid_step', 0.05)
    
    # Component-specific allocation discounts
    discounts = config.get('allocation_discounts', {})
    
    print(f"IS start: {is_start.date()}")
    print(f"IS/OOS cutoff: {is_cutoff.date()}")
    print(f"Grid step: {grid_step:.0%}")
    if discounts:
        print(f"Allocation discounts: {discounts}")
    print()
    
    # Load sleeves
    print("-"*80)
    print("LOADING SLEEVES")
    print("-"*80)
    
    baseline = load_sleeve(config['components']['baseline'], base_path)
    tightstocks = load_sleeve(config['components']['tightstocks'], base_path)
    volcore = load_sleeve(config['components']['volcore'], base_path)
    
    print(f"Baseline: {len(baseline)} days")
    print(f"TightStocks: {len(tightstocks)} days")
    print(f"VolCore: {len(volcore)} days")
    
    # Align dates
    common_dates = baseline.index.intersection(tightstocks.index).intersection(volcore.index)
    print(f"Common dates: {len(common_dates)}")
    print(f"Range: {common_dates.min().date()} to {common_dates.max().date()}")
    
    bl_pnl = baseline.loc[common_dates, 'pnl_gross']
    ts_pnl = tightstocks.loc[common_dates, 'pnl_gross']
    vc_pnl = volcore.loc[common_dates, 'pnl_gross']
    
    # Split IS/OOS (with optional IS start date)
    is_dates = common_dates[(common_dates >= is_start) & (common_dates < is_cutoff)]
    oos_dates = common_dates[common_dates >= is_cutoff]
    
    print(f"\nIS: {is_dates.min().date()} to {is_dates.max().date()} ({len(is_dates)} days)")
    print(f"OOS: {oos_dates.min().date()} to {oos_dates.max().date()} ({len(oos_dates)} days)")
    print()
    
    # IS PnLs
    is_bl = bl_pnl.loc[is_dates]
    is_ts = ts_pnl.loc[is_dates]
    is_vc = vc_pnl.loc[is_dates]
    
    # OOS PnLs
    oos_bl = bl_pnl.loc[oos_dates]
    oos_ts = ts_pnl.loc[oos_dates]
    oos_vc = vc_pnl.loc[oos_dates]
    
    # =========================================================================
    # PHASE 1: IS WEIGHT OPTIMIZATION
    # =========================================================================
    print("-"*80)
    print("PHASE 1: IN-SAMPLE WEIGHT OPTIMIZATION")
    print("-"*80)
    
    # Standalone IS performance
    is_bl_sharpe = calculate_sharpe(is_bl)
    is_ts_sharpe = calculate_sharpe(is_ts)
    is_vc_sharpe = calculate_sharpe(is_vc)
    
    print(f"IS Standalone:")
    print(f"  Baseline:    {is_bl_sharpe:.3f}")
    print(f"  TightStocks: {is_ts_sharpe:.3f}")
    print(f"  VolCore:     {is_vc_sharpe:.3f}")
    print()
    
    # Best two-way for comparison
    is_two_way = find_best_two_way(is_bl, is_ts, is_vc, step=grid_step)
    print(f"IS Best Two-Way:")
    print(f"  BL+TS: {is_two_way['bl_ts']['sharpe']:.3f} ({is_two_way['bl_ts']['bl']:.0%}/{is_two_way['bl_ts']['ts']:.0%})")
    print(f"  BL+VC: {is_two_way['bl_vc']['sharpe']:.3f} ({is_two_way['bl_vc']['bl']:.0%}/{is_two_way['bl_vc']['vc']:.0%})")
    print()
    
    # Grid search three-way on IS
    best_weights, is_best_sharpe, is_results = grid_search_three_weights(
        is_bl, is_ts, is_vc, step=grid_step
    )
    
    print(f"IS Optimal Three-Way Weights:")
    print(f"  Baseline:    {best_weights['baseline']:.0%}")
    print(f"  TightStocks: {best_weights['tightstocks']:.0%}")
    print(f"  VolCore:     {best_weights['volcore']:.0%}")
    print(f"IS Best Sharpe: {is_best_sharpe:.3f}")
    
    # Store raw weights before discount
    raw_weights = best_weights.copy()
    
    # Apply component-specific discounts
    if discounts:
        for component, discount in discounts.items():
            if component in best_weights and discount < 1.0:
                raw_wt = best_weights[component]
                best_weights[component] = raw_wt * discount
                print(f"\nDiscount applied to {component}: {raw_wt:.0%} × {discount:.0%} = {best_weights[component]:.0%}")
        
        # Renormalize weights to sum to 1.0
        total = sum(best_weights.values())
        if total > 0:
            # Redistribute the discount to baseline
            discount_amount = 1.0 - total
            best_weights['baseline'] = best_weights['baseline'] + discount_amount
            print(f"Redistributed {discount_amount:.0%} to Baseline")
            print(f"\nFinal weights after discount:")
            for name, wt in best_weights.items():
                print(f"  {name}: {wt:.0%}")
    
    # IS marginal vs baseline
    is_marginal_bl = is_best_sharpe - is_bl_sharpe
    is_marginal_2way = is_best_sharpe - max(is_two_way['bl_ts']['sharpe'], is_two_way['bl_vc']['sharpe'])
    print(f"\nIS Marginal vs BL alone: {is_marginal_bl:+.3f}")
    print(f"IS Marginal vs best two-way: {is_marginal_2way:+.3f}")
    
    # Robustness
    robustness = analyze_robustness(is_results, is_best_sharpe)
    print(f"\nIS Weight Robustness:")
    print(f"  Within 1% of optimal: {robustness['within_1pct']}")
    print(f"  Within 5% of optimal: {robustness['within_5pct']}")
    
    # Correlations
    print(f"\nIS Correlations:")
    print(f"  BL vs TS: {is_bl.corr(is_ts):.3f}")
    print(f"  BL vs VC: {is_bl.corr(is_vc):.3f}")
    print(f"  TS vs VC: {is_ts.corr(is_vc):.3f}")
    
    # =========================================================================
    # PHASE 2: OOS VALIDATION (FROZEN WEIGHTS)
    # =========================================================================
    print()
    print("-"*80)
    print("PHASE 2: OUT-OF-SAMPLE VALIDATION")
    print("-"*80)
    print("Applying IS weights FROZEN to OOS...")
    print()
    
    # Standalone OOS
    oos_bl_sharpe = calculate_sharpe(oos_bl)
    oos_ts_sharpe = calculate_sharpe(oos_ts)
    oos_vc_sharpe = calculate_sharpe(oos_vc)
    
    print(f"OOS Standalone:")
    print(f"  Baseline:    {oos_bl_sharpe:.3f}")
    print(f"  TightStocks: {oos_ts_sharpe:.3f}")
    print(f"  VolCore:     {oos_vc_sharpe:.3f}")
    print()
    
    # Best two-way in OOS (for reference - but we use IS weights)
    oos_two_way = find_best_two_way(oos_bl, oos_ts, oos_vc, step=grid_step)
    
    # Apply frozen IS weights to OOS
    oos_blended = blend_three_pnls(
        oos_bl, oos_ts, oos_vc,
        best_weights['baseline'], best_weights['tightstocks'], best_weights['volcore']
    )
    oos_sharpe = calculate_sharpe(oos_blended)
    
    print(f"OOS Weights (from IS):")
    print(f"  Baseline:    {best_weights['baseline']:.0%}")
    print(f"  TightStocks: {best_weights['tightstocks']:.0%}")
    print(f"  VolCore:     {best_weights['volcore']:.0%}")
    print(f"OOS Portfolio Sharpe: {oos_sharpe:.3f}")
    
    # OOS marginals
    oos_marginal_bl = oos_sharpe - oos_bl_sharpe
    print(f"\nOOS Marginal vs BL alone: {oos_marginal_bl:+.3f}")
    
    # Correlations
    print(f"\nOOS Correlations:")
    print(f"  BL vs TS: {oos_bl.corr(oos_ts):.3f}")
    print(f"  BL vs VC: {oos_bl.corr(oos_vc):.3f}")
    print(f"  TS vs VC: {oos_ts.corr(oos_vc):.3f}")
    
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
    
    print(f"\n{'Metric':<25} {'IS':>12} {'OOS':>12}")
    print("-"*50)
    print(f"{'Baseline':<25} {is_bl_sharpe:>12.3f} {oos_bl_sharpe:>12.3f}")
    print(f"{'TightStocks':<25} {is_ts_sharpe:>12.3f} {oos_ts_sharpe:>12.3f}")
    print(f"{'VolCore':<25} {is_vc_sharpe:>12.3f} {oos_vc_sharpe:>12.3f}")
    print(f"{'Best Two-Way':<25} {max(is_two_way['bl_ts']['sharpe'], is_two_way['bl_vc']['sharpe']):>12.3f} {max(oos_two_way['bl_ts']['sharpe'], oos_two_way['bl_vc']['sharpe']):>12.3f}")
    print(f"{'Three-Way Portfolio':<25} {is_best_sharpe:>12.3f} {oos_sharpe:>12.3f}")
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
    
    # Value-add assessment
    print()
    print("-"*50)
    print("COMPONENT VALUE ASSESSMENT (OOS)")
    print("-"*50)
    
    # Does three-way beat best two-way?
    best_oos_two_way = max(oos_two_way['bl_ts']['sharpe'], oos_two_way['bl_vc']['sharpe'])
    three_vs_two = oos_sharpe - best_oos_two_way
    
    if three_vs_two > 0.05:
        print(f"✓ Three-way adds significant value vs two-way (+{three_vs_two:.3f})")
        three_way_rec = "RECOMMENDED"
    elif three_vs_two > 0:
        print(f"~ Three-way adds marginal value vs two-way (+{three_vs_two:.3f})")
        three_way_rec = "CONSIDER"
    else:
        print(f"✗ Three-way does not beat two-way ({three_vs_two:+.3f})")
        three_way_rec = "USE TWO-WAY"
    
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
    full_blended = blend_three_pnls(
        bl_pnl, ts_pnl, vc_pnl,
        best_weights['baseline'], best_weights['tightstocks'], best_weights['volcore']
    )
    
    daily_df = pd.DataFrame({
        'date': common_dates,
        'baseline_pnl': bl_pnl.values,
        'tightstocks_pnl': ts_pnl.values,
        'volcore_pnl': vc_pnl.values,
        'portfolio_pnl': full_blended.values,
        'baseline_weight': best_weights['baseline'],
        'tightstocks_weight': best_weights['tightstocks'],
        'volcore_weight': best_weights['volcore'],
        'is_period': common_dates < is_cutoff
    })
    daily_df.to_csv(outdir / 'daily_series.csv', index=False)
    print(f"✓ daily_series.csv")
    
    # Validation summary
    validation = {
        'generated': datetime.now().isoformat(),
        'methodology': 'IS optimization, OOS validation (weights frozen)',
        'is_cutoff': str(is_cutoff.date()),
        'optimal_weights': best_weights,
        'is_metrics': {
            'baseline': is_bl_sharpe,
            'tightstocks': is_ts_sharpe,
            'volcore': is_vc_sharpe,
            'best_two_way': max(is_two_way['bl_ts']['sharpe'], is_two_way['bl_vc']['sharpe']),
            'three_way': is_best_sharpe
        },
        'oos_metrics': {
            'baseline': oos_bl_sharpe,
            'tightstocks': oos_ts_sharpe,
            'volcore': oos_vc_sharpe,
            'best_two_way': best_oos_two_way,
            'three_way': oos_sharpe
        },
        'validation': {
            'degradation_pct': degradation,
            'status': status,
            'three_way_vs_two_way': three_vs_two,
            'recommendation': three_way_rec
        },
        'robustness': robustness
    }
    
    with open(outdir / 'validation_summary.json', 'w') as f:
        json.dump(validation, f, indent=2)
    print(f"✓ validation_summary.json")
    
    # Correlation matrix
    corr_df = pd.DataFrame({
        'baseline': bl_pnl,
        'tightstocks': ts_pnl,
        'volcore': vc_pnl
    }).corr()
    corr_df.to_csv(outdir / 'correlation_matrix.csv')
    print(f"✓ correlation_matrix.csv")
    
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
    print(f"  Weights: {best_weights['baseline']:.0%} BL / {best_weights['tightstocks']:.0%} TS / {best_weights['volcore']:.0%} VC")
    print(f"  Three-Way: {three_way_rec}")


if __name__ == '__main__':
    main()