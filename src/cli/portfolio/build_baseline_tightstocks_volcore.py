"""
Build Baseline + TightStocks + VolCore Portfolio
Three-way combination testing with grid search
"""

import pandas as pd
import numpy as np
import yaml
from pathlib import Path
import json
from datetime import datetime
import itertools

def load_config(config_path):
    """Load configuration file"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def load_component(component_config, base_path):
    """Load a component sleeve's daily series"""
    file_path = Path(base_path) / component_config['path']
    
    if not file_path.exists():
        raise FileNotFoundError(f"Component file not found: {file_path}")
    
    df = pd.read_csv(file_path, parse_dates=['date'])
    df.set_index('date', inplace=True)
    
    # Extract position and PnL columns
    position_col = component_config['position_col']
    pnl_col = component_config['pnl_col']
    
    if position_col not in df.columns:
        raise ValueError(f"Position column '{position_col}' not found in {file_path}")
    if pnl_col not in df.columns:
        raise ValueError(f"PnL column '{pnl_col}' not found in {file_path}")
    
    return df[[position_col, pnl_col]].rename(columns={
        position_col: 'position',
        pnl_col: 'pnl_gross'
    })

def calculate_sharpe(returns, periods_per_year=252):
    """Calculate annualized Sharpe ratio"""
    if len(returns) == 0 or returns.std() == 0:
        return 0.0
    return (returns.mean() * periods_per_year) / (returns.std() * np.sqrt(periods_per_year))

def calculate_metrics(pnl_series, label="Portfolio"):
    """Calculate comprehensive performance metrics"""
    returns = pnl_series
    cum_returns = (1 + returns).cumprod()
    
    sharpe = calculate_sharpe(returns)
    total_return = cum_returns.iloc[-1] - 1
    ann_return = (1 + total_return) ** (252 / len(returns)) - 1
    ann_vol = returns.std() * np.sqrt(252)
    
    # Drawdown
    cum_max = cum_returns.cummax()
    drawdown = (cum_returns - cum_max) / cum_max
    max_dd = drawdown.min()
    
    # Win rate
    win_rate = (returns > 0).sum() / len(returns)
    
    return {
        'label': label,
        'sharpe': sharpe,
        'total_return': total_return,
        'ann_return': ann_return,
        'ann_vol': ann_vol,
        'max_drawdown': max_dd,
        'win_rate': win_rate,
        'num_days': len(returns)
    }

def blend_three_portfolios(bl_pnl, ts_pnl, vc_pnl, w_bl, w_ts, w_vc):
    """Blend three portfolios with given weights (pre-normalized)"""
    # All three should already be aligned on common dates
    blended_pnl = (bl_pnl * w_bl + ts_pnl * w_ts + vc_pnl * w_vc)
    return blended_pnl

def generate_grid_allocations(increment=0.05):
    """Generate all valid three-way weight combinations that sum to 1.0"""
    allocations = []
    
    # Generate weights in increments
    weights = np.arange(0.0, 1.0 + increment, increment)
    
    for w_bl in weights:
        for w_ts in weights:
            w_vc = 1.0 - w_bl - w_ts
            
            # Check if valid (w_vc in valid range and sums to 1.0)
            if -0.001 <= w_vc <= 1.001:  # Small tolerance for floating point
                # Round to avoid floating point issues
                w_bl_round = round(w_bl, 3)
                w_ts_round = round(w_ts, 3)
                w_vc_round = round(w_vc, 3)
                
                # Verify sum
                if abs(w_bl_round + w_ts_round + w_vc_round - 1.0) < 0.01:
                    allocations.append({
                        'baseline': w_bl_round,
                        'tightstocks': w_ts_round,
                        'volcore': w_vc_round
                    })
    
    return allocations

def main():
    """Main execution"""
    
    # Setup paths
    base_path = Path(r"C:\Code\Metals")
    config_path = base_path / "Config" / "Copper" / "portfolio_baseline_tightstocks_volcore.yaml"
    
    print("="*80)
    print("BASELINE + TIGHTSTOCKS + VOLCORE THREE-WAY PORTFOLIO")
    print("="*80)
    print()
    
    # Load config
    print("Loading configuration...")
    config = load_config(config_path)
    
    # Load components
    print("Loading component sleeves...")
    baseline_df = load_component(config['components']['baseline'], base_path)
    ts_df = load_component(config['components']['tightstocks'], base_path)
    vc_df = load_component(config['components']['volcore'], base_path)
    
    print(f"  Baseline:    {len(baseline_df)} days ({baseline_df.index[0].date()} to {baseline_df.index[-1].date()})")
    print(f"  TightStocks: {len(ts_df)} days ({ts_df.index[0].date()} to {ts_df.index[-1].date()})")
    print(f"  VolCore:     {len(vc_df)} days ({vc_df.index[0].date()} to {vc_df.index[-1].date()})")
    
    # Align dates (limited by VolCore)
    common_dates = baseline_df.index.intersection(ts_df.index).intersection(vc_df.index)
    print(f"\n  Common dates: {len(common_dates)} days")
    print(f"  Date range: {common_dates[0].date()} to {common_dates[-1].date()}")
    print(f"  (Limited by VolCore data availability)")
    print()
    
    baseline_pnl = baseline_df.loc[common_dates, 'pnl_gross']
    ts_pnl = ts_df.loc[common_dates, 'pnl_gross']
    vc_pnl = vc_df.loc[common_dates, 'pnl_gross']
    
    # Create output directory
    output_dir = base_path / config['output_dir']
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Track results
    all_results = []
    
    # Test 1: Individual components
    print("-" * 80)
    print("INDIVIDUAL COMPONENT PERFORMANCE")
    print("-" * 80)
    
    baseline_metrics = calculate_metrics(baseline_pnl, "Baseline")
    ts_metrics = calculate_metrics(ts_pnl, "TightStocks")
    vc_metrics = calculate_metrics(vc_pnl, "VolCore")
    
    all_results.extend([baseline_metrics, ts_metrics, vc_metrics])
    
    print(f"Baseline:    {baseline_metrics['sharpe']:.3f} Sharpe, {baseline_metrics['max_drawdown']:.1%} MaxDD")
    print(f"TightStocks: {ts_metrics['sharpe']:.3f} Sharpe, {ts_metrics['max_drawdown']:.1%} MaxDD")
    print(f"VolCore:     {vc_metrics['sharpe']:.3f} Sharpe, {vc_metrics['max_drawdown']:.1%} MaxDD")
    print()
    
    # Correlation analysis
    print("-" * 80)
    print("CORRELATION MATRIX")
    print("-" * 80)
    
    corr_matrix = pd.DataFrame({
        'Baseline': baseline_pnl,
        'TightStocks': ts_pnl,
        'VolCore': vc_pnl
    }).corr()
    
    print(corr_matrix.to_string())
    print()
    
    # Save correlation matrix
    corr_path = output_dir / "three_way_correlation_matrix.csv"
    corr_matrix.to_csv(corr_path)
    print(f"✓ Correlation matrix saved: {corr_path}")
    print()
    
    # Test predefined weight combinations
    print("-" * 80)
    print("PREDEFINED WEIGHT ALLOCATION TESTS")
    print("-" * 80)
    
    best_sharpe = 0
    best_allocation = None
    
    for test in config['weight_tests']:
        name = test['name']
        weights = test['weights']
        w_bl = weights['baseline']
        w_ts = weights['tightstocks']
        w_vc = weights['volcore']
        
        # Normalize weights to sum to 1
        total = w_bl + w_ts + w_vc
        w_bl_norm = w_bl / total
        w_ts_norm = w_ts / total
        w_vc_norm = w_vc / total
        
        # Blend
        blended_pnl = blend_three_portfolios(baseline_pnl, ts_pnl, vc_pnl,
                                             w_bl_norm, w_ts_norm, w_vc_norm)
        
        # Calculate metrics
        label = f"{name} ({w_bl_norm:.0%}/{w_ts_norm:.0%}/{w_vc_norm:.0%})"
        metrics = calculate_metrics(blended_pnl, label)
        metrics['weights'] = {
            'baseline': w_bl_norm,
            'tightstocks': w_ts_norm,
            'volcore': w_vc_norm
        }
        all_results.append(metrics)
        
        # Calculate marginal contribution
        marginal_sharpe = metrics['sharpe'] - baseline_metrics['sharpe']
        
        print(f"\n{name}:")
        print(f"  Weights: {w_bl_norm:.0%} BL / {w_ts_norm:.0%} TS / {w_vc_norm:.0%} VC")
        print(f"  Sharpe: {metrics['sharpe']:.3f} (marginal: {marginal_sharpe:+.3f})")
        print(f"  Return: {metrics['total_return']:.1%}")
        print(f"  Max DD: {metrics['max_drawdown']:.1%}")
        
        if 'note' in test:
            print(f"  Note: {test['note']}")
        
        # Track best
        if metrics['sharpe'] > best_sharpe:
            best_sharpe = metrics['sharpe']
            best_allocation = {
                'name': name,
                'weights': {
                    'baseline': w_bl_norm,
                    'tightstocks': w_ts_norm,
                    'volcore': w_vc_norm
                },
                'sharpe': metrics['sharpe'],
                'max_drawdown': metrics['max_drawdown']
            }
    
    print()
    
    # Grid search (if enabled)
    if config['grid_search']['enabled']:
        print("-" * 80)
        print("GRID SEARCH OPTIMIZATION")
        print("-" * 80)
        
        increment = config['grid_search']['increment']
        print(f"Testing all combinations with {increment:.0%} increments...")
        print("(This may take a minute...)")
        print()
        
        # Generate all valid allocations
        grid_allocations = generate_grid_allocations(increment)
        print(f"Total combinations to test: {len(grid_allocations)}")
        
        grid_results = []
        
        for i, alloc in enumerate(grid_allocations):
            if (i + 1) % 100 == 0:
                print(f"  Tested {i+1}/{len(grid_allocations)}...", end='\r')
            
            w_bl = alloc['baseline']
            w_ts = alloc['tightstocks']
            w_vc = alloc['volcore']
            
            # Blend
            blended_pnl = blend_three_portfolios(baseline_pnl, ts_pnl, vc_pnl,
                                                 w_bl, w_ts, w_vc)
            
            # Calculate metrics
            sharpe = calculate_sharpe(blended_pnl)
            cum_returns = (1 + blended_pnl).cumprod()
            cum_max = cum_returns.cummax()
            drawdown = (cum_returns - cum_max) / cum_max
            max_dd = drawdown.min()
            
            grid_results.append({
                'bl_weight': w_bl,
                'ts_weight': w_ts,
                'vc_weight': w_vc,
                'sharpe': sharpe,
                'max_dd': max_dd
            })
        
        print()
        
        # Sort by Sharpe and get top results
        grid_df = pd.DataFrame(grid_results)
        grid_df_sorted = grid_df.sort_values('sharpe', ascending=False)
        
        # Save full grid results
        grid_path = output_dir / "grid_search_results.csv"
        grid_df_sorted.to_csv(grid_path, index=False)
        print(f"✓ Grid search results saved: {grid_path}")
        print()
        
        # Display top allocations
        top_n = config['grid_search']['top_n_results']
        print(f"TOP {top_n} ALLOCATIONS:")
        print()
        
        for idx, row in grid_df_sorted.head(top_n).iterrows():
            print(f"  {row['bl_weight']:.0%} BL / {row['ts_weight']:.0%} TS / {row['vc_weight']:.0%} VC")
            print(f"    Sharpe: {row['sharpe']:.3f}, MaxDD: {row['max_dd']:.1%}")
        
        # Update best allocation if grid search found better
        grid_best = grid_df_sorted.iloc[0]
        if grid_best['sharpe'] > best_sharpe:
            print()
            print(f"✓ Grid search found better allocation!")
            print(f"  Previous best: {best_sharpe:.3f} Sharpe")
            print(f"  New best: {grid_best['sharpe']:.3f} Sharpe")
            
            best_allocation = {
                'name': 'Grid Search Optimal',
                'weights': {
                    'baseline': grid_best['bl_weight'],
                    'tightstocks': grid_best['ts_weight'],
                    'volcore': grid_best['vc_weight']
                },
                'sharpe': grid_best['sharpe'],
                'max_drawdown': grid_best['max_dd']
            }
            best_sharpe = grid_best['sharpe']
        
        print()
    
    # Display best allocation
    print("-" * 80)
    print("BEST OVERALL ALLOCATION")
    print("-" * 80)
    print(f"Name: {best_allocation['name']}")
    w = best_allocation['weights']
    print(f"Weights: {w['baseline']:.0%} BL / {w['tightstocks']:.0%} TS / {w['volcore']:.0%} VC")
    print(f"Sharpe: {best_allocation['sharpe']:.3f}")
    print(f"MaxDD: {best_allocation['max_drawdown']:.1%}")
    print(f"Marginal improvement: {(best_allocation['sharpe'] - baseline_metrics['sharpe']):+.3f}")
    print()
    
    # Period-specific analysis
    print("-" * 80)
    print("PERIOD BREAKDOWN (Using Best Allocation)")
    print("-" * 80)
    
    for period in config['analysis']['period_breakdown']:
        period_name = period['name']
        
        # Filter data
        period_bl = baseline_pnl.copy()
        period_ts = ts_pnl.copy()
        period_vc = vc_pnl.copy()
        
        if period['start']:
            start_date = pd.to_datetime(period['start'])
            period_bl = period_bl[period_bl.index >= start_date]
            period_ts = period_ts[period_ts.index >= start_date]
            period_vc = period_vc[period_vc.index >= start_date]
            
        if period['end']:
            end_date = pd.to_datetime(period['end'])
            period_bl = period_bl[period_bl.index <= end_date]
            period_ts = period_ts[period_ts.index <= end_date]
            period_vc = period_vc[period_vc.index <= end_date]
        
        if len(period_bl) == 0:
            print(f"\n{period_name}: No data")
            continue
        
        # Calculate metrics for this period
        bl_period_sharpe = calculate_sharpe(period_bl)
        ts_period_sharpe = calculate_sharpe(period_ts)
        vc_period_sharpe = calculate_sharpe(period_vc)
        
        # Best allocation for this period
        w = best_allocation['weights']
        period_blended = blend_three_portfolios(period_bl, period_ts, period_vc,
                                               w['baseline'], w['tightstocks'], w['volcore'])
        blended_sharpe = calculate_sharpe(period_blended)
        
        # Calculate max DD for period
        cum_ret = (1 + period_blended).cumprod()
        cum_max = cum_ret.cummax()
        dd = (cum_ret - cum_max) / cum_max
        period_max_dd = dd.min()
        
        print(f"\n{period_name} ({len(period_bl)} days):")
        print(f"  Baseline:    {bl_period_sharpe:.3f} Sharpe")
        print(f"  TightStocks: {ts_period_sharpe:.3f} Sharpe")
        print(f"  VolCore:     {vc_period_sharpe:.3f} Sharpe")
        print(f"  Portfolio:   {blended_sharpe:.3f} Sharpe, {period_max_dd:.1%} MaxDD")
        
        if 'note' in period:
            print(f"  Note: {period['note']}")
    
    print()
    
    # Save outputs
    print("-" * 80)
    print("SAVING OUTPUTS")
    print("-" * 80)
    
    # Daily series with best allocation
    w = best_allocation['weights']
    output_df = pd.DataFrame({
        'date': common_dates,
        'baseline_pnl': baseline_pnl.values,
        'tightstocks_pnl': ts_pnl.values,
        'volcore_pnl': vc_pnl.values,
        'portfolio_pnl': (baseline_pnl * w['baseline'] + 
                         ts_pnl * w['tightstocks'] + 
                         vc_pnl * w['volcore']).values,
        'baseline_weight': w['baseline'],
        'tightstocks_weight': w['tightstocks'],
        'volcore_weight': w['volcore']
    })
    
    output_path = output_dir / "daily_series.csv"
    output_df.to_csv(output_path, index=False)
    print(f"✓ Daily series: {output_path}")
    
    # Weight comparison
    weight_comparison = {
        'best_allocation': best_allocation,
        'predefined_tests': [
            {
                'name': r['label'],
                'sharpe': r['sharpe'],
                'return': r['total_return'],
                'max_dd': r['max_drawdown'],
                'weights': r.get('weights', {})
            }
            for r in all_results if 'weights' in r
        ],
        'individual_components': {
            'baseline': {'sharpe': baseline_metrics['sharpe'], 'max_dd': baseline_metrics['max_drawdown']},
            'tightstocks': {'sharpe': ts_metrics['sharpe'], 'max_dd': ts_metrics['max_drawdown']},
            'volcore': {'sharpe': vc_metrics['sharpe'], 'max_dd': vc_metrics['max_drawdown']}
        },
        'correlation_matrix': corr_matrix.to_dict()
    }
    
    comparison_path = output_dir / "weight_comparison.json"
    with open(comparison_path, 'w') as f:
        json.dump(weight_comparison, f, indent=2)
    print(f"✓ Weight comparison: {comparison_path}")
    
    # Optimal allocation
    optimal_path = output_dir / "optimal_allocation.json"
    with open(optimal_path, 'w') as f:
        json.dump(best_allocation, f, indent=2)
    print(f"✓ Optimal allocation: {optimal_path}")
    
    # Validation report
    report_lines = [
        "THREE-WAY PORTFOLIO VALIDATION REPORT",
        "Baseline + TightStocks + VolCore",
        "=" * 80,
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Date range: {common_dates[0].date()} to {common_dates[-1].date()}",
        f"Days: {len(common_dates):,}",
        "",
        "INDIVIDUAL COMPONENT PERFORMANCE",
        "-" * 80,
        f"Baseline:    {baseline_metrics['sharpe']:.3f} Sharpe, {baseline_metrics['max_drawdown']:.1%} MaxDD",
        f"TightStocks: {ts_metrics['sharpe']:.3f} Sharpe, {ts_metrics['max_drawdown']:.1%} MaxDD",
        f"VolCore:     {vc_metrics['sharpe']:.3f} Sharpe, {vc_metrics['max_drawdown']:.1%} MaxDD",
        "",
        "CORRELATION MATRIX",
        "-" * 80,
        f"Baseline vs TightStocks: {corr_matrix.loc['Baseline', 'TightStocks']:.3f}",
        f"Baseline vs VolCore:     {corr_matrix.loc['Baseline', 'VolCore']:.3f}",
        f"TightStocks vs VolCore:  {corr_matrix.loc['TightStocks', 'VolCore']:.3f}",
        "",
        "BEST ALLOCATION",
        "-" * 80,
        f"Name: {best_allocation['name']}",
        f"Weights:",
        f"  Baseline:    {best_allocation['weights']['baseline']:.1%}",
        f"  TightStocks: {best_allocation['weights']['tightstocks']:.1%}",
        f"  VolCore:     {best_allocation['weights']['volcore']:.1%}",
        "",
        f"Performance:",
        f"  Sharpe: {best_allocation['sharpe']:.3f}",
        f"  MaxDD: {best_allocation['max_drawdown']:.1%}",
        f"  Marginal improvement: {(best_allocation['sharpe'] - baseline_metrics['sharpe']):+.3f}",
        "",
        "INTERPRETATION",
        "-" * 80,
    ]
    
    # Add interpretation
    marginal = best_allocation['sharpe'] - baseline_metrics['sharpe']
    if marginal > 0.15:
        report_lines.append("✓ THREE-WAY COMBINATION ADDS EXCELLENT VALUE (+0.15+ Sharpe)")
        report_lines.append("✓ STRONGLY RECOMMEND: Deploy three-way portfolio")
    elif marginal > 0.10:
        report_lines.append("✓ Three-way combination adds significant value (+0.10-0.15 Sharpe)")
        report_lines.append("✓ RECOMMEND: Deploy three-way portfolio")
    elif marginal > 0.05:
        report_lines.append("✓ Three-way combination adds moderate value (+0.05-0.10 Sharpe)")
        report_lines.append("✓ RECOMMEND: Consider deployment")
    else:
        report_lines.append("⚠ Three-way combination adds limited value (<0.05 Sharpe)")
        report_lines.append("⚠ REVIEW: May not justify additional complexity")
    
    report_lines.append("")
    
    # Diversification assessment
    avg_corr = (abs(corr_matrix.loc['Baseline', 'TightStocks']) + 
                abs(corr_matrix.loc['Baseline', 'VolCore']) + 
                abs(corr_matrix.loc['TightStocks', 'VolCore'])) / 3
    
    if avg_corr < 0.15:
        report_lines.append(f"✓ EXCELLENT diversification (avg correlation: {avg_corr:.3f})")
    elif avg_corr < 0.30:
        report_lines.append(f"✓ GOOD diversification (avg correlation: {avg_corr:.3f})")
    else:
        report_lines.append(f"⚠ LIMITED diversification (avg correlation: {avg_corr:.3f})")
    
    report_lines.extend([
        "",
        "NEXT STEPS",
        "-" * 80,
        "1. Review period breakdown for regime-specific performance",
        "2. Consider regime-adaptive allocation (defensive vs optimal)",
        "3. Add China Demand overlay to baseline component",
        "4. Implement walk-forward validation",
        "5. Prepare for live deployment",
        "",
        "Files generated:",
        f"  - daily_series.csv (full time series)",
        f"  - weight_comparison.json (all test results)",
        f"  - optimal_allocation.json (best weights)",
        f"  - three_way_correlation_matrix.csv (correlations)",
        f"  - grid_search_results.csv (all combinations tested)",
        ""
    ])
    
    report_path = output_dir / "validation_report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    print(f"✓ Validation report: {report_path}")
    
    print()
    print("="*80)
    print("THREE-WAY PORTFOLIO ANALYSIS COMPLETE")
    print("="*80)
    print(f"\nBest allocation: {best_allocation['weights']['baseline']:.0%} BL / "
          f"{best_allocation['weights']['tightstocks']:.0%} TS / "
          f"{best_allocation['weights']['volcore']:.0%} VC")
    print(f"Sharpe: {best_allocation['sharpe']:.3f} (marginal: {marginal:+.3f})")
    print(f"\nOutputs saved to: {output_dir}")
    print("\nNext: Review validation_report.txt for full analysis")

if __name__ == "__main__":
    main()