"""
Build Baseline + VolCore Portfolio
Tests marginal contribution of VolCore to baseline portfolio
"""

import pandas as pd
import numpy as np
import yaml
from pathlib import Path
import json
from datetime import datetime

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
        'num_trades': len(returns)
    }

def blend_portfolios(baseline_pnl, vc_pnl, baseline_weight, vc_weight):
    """Blend two portfolios with given weights"""
    # Align on common dates
    common_idx = baseline_pnl.index.intersection(vc_pnl.index)
    
    baseline_aligned = baseline_pnl.loc[common_idx]
    vc_aligned = vc_pnl.loc[common_idx]
    
    # Weighted blend
    blended_pnl = (baseline_aligned * baseline_weight + 
                   vc_aligned * vc_weight)
    
    return blended_pnl

def analyze_period(df, period_config):
    """Calculate metrics for a specific time period"""
    start = period_config.get('start')
    end = period_config.get('end')
    
    if start:
        df = df[df.index >= start]
    if end:
        df = df[df.index <= end]
    
    return df

def main():
    """Main execution"""
    
    # Setup paths
    base_path = Path(r"C:\Code\Metals")
    config_path = base_path / "Config" / "Copper" / "portfolio_baseline_volcore.yaml"
    
    print("="*80)
    print("BASELINE + VOLCORE PORTFOLIO ANALYSIS")
    print("="*80)
    print()
    
    # Load config
    print("Loading configuration...")
    config = load_config(config_path)
    
    # Load components
    print("Loading component sleeves...")
    baseline_df = load_component(config['components']['baseline'], base_path)
    vc_df = load_component(config['components']['volcore'], base_path)
    
    print(f"  Baseline: {len(baseline_df)} days")
    print(f"  VolCore: {len(vc_df)} days")
    
    # Align dates
    common_dates = baseline_df.index.intersection(vc_df.index)
    print(f"  Common dates: {len(common_dates)} days")
    print(f"  Date range: {common_dates[0].date()} to {common_dates[-1].date()}")
    print()
    
    baseline_pnl = baseline_df.loc[common_dates, 'pnl_gross']
    vc_pnl = vc_df.loc[common_dates, 'pnl_gross']
    
    # Create output directory
    output_dir = base_path / config['output_dir']
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Track results
    all_results = []
    
    # Test 1: Baseline alone
    print("-" * 80)
    print("TEST 1: BASELINE ALONE")
    print("-" * 80)
    baseline_metrics = calculate_metrics(baseline_pnl, "Baseline")
    all_results.append(baseline_metrics)
    print(f"Sharpe: {baseline_metrics['sharpe']:.3f}")
    print(f"Return: {baseline_metrics['total_return']:.1%}")
    print(f"Max DD: {baseline_metrics['max_drawdown']:.1%}")
    print()
    
    # Test 2: VolCore alone
    print("-" * 80)
    print("TEST 2: VOLCORE ALONE")
    print("-" * 80)
    vc_metrics = calculate_metrics(vc_pnl, "VolCore")
    all_results.append(vc_metrics)
    print(f"Sharpe: {vc_metrics['sharpe']:.3f}")
    print(f"Return: {vc_metrics['total_return']:.1%}")
    print(f"Max DD: {vc_metrics['max_drawdown']:.1%}")
    print()
    
    # Correlation analysis
    correlation = baseline_pnl.corr(vc_pnl)
    print("-" * 80)
    print("CORRELATION ANALYSIS")
    print("-" * 80)
    print(f"Baseline vs VolCore correlation: {correlation:.3f}")
    print()
    
    # Test weight combinations
    print("-" * 80)
    print("WEIGHT ALLOCATION TESTS")
    print("-" * 80)
    
    best_sharpe = 0
    best_allocation = None
    
    for test in config['weight_tests']:
        name = test['name']
        weights = test['weights']
        baseline_wt = weights['baseline']
        vc_wt = weights['volcore']
        
        # Normalize weights to sum to 1
        total = baseline_wt + vc_wt
        baseline_wt_norm = baseline_wt / total
        vc_wt_norm = vc_wt / total
        
        # Blend
        blended_pnl = blend_portfolios(baseline_pnl, vc_pnl, 
                                       baseline_wt_norm, vc_wt_norm)
        
        # Calculate metrics
        label = f"{name} ({baseline_wt_norm:.0%}/{vc_wt_norm:.0%})"
        metrics = calculate_metrics(blended_pnl, label)
        all_results.append(metrics)
        
        # Calculate marginal contribution
        marginal_sharpe = metrics['sharpe'] - baseline_metrics['sharpe']
        
        print(f"\n{name}:")
        print(f"  Weights: {baseline_wt_norm:.0%} Baseline / {vc_wt_norm:.0%} VolCore")
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
                'baseline_weight': baseline_wt_norm,
                'vc_weight': vc_wt_norm,
                'sharpe': metrics['sharpe']
            }
    
    print()
    print("-" * 80)
    print("BEST ALLOCATION")
    print("-" * 80)
    print(f"Name: {best_allocation['name']}")
    print(f"Weights: {best_allocation['baseline_weight']:.0%} / {best_allocation['vc_weight']:.0%}")
    print(f"Sharpe: {best_allocation['sharpe']:.3f}")
    print()
    
    # Period-specific analysis
    print("-" * 80)
    print("PERIOD BREAKDOWN")
    print("-" * 80)
    
    is_cutoff = pd.to_datetime(config['is_oos_cutoff'])
    
    for period in config['analysis']['period_breakdown']:
        period_name = period['name']
        print(f"\n{period_name}:")
        
        # Filter data
        if period['start']:
            start_date = pd.to_datetime(period['start'])
            period_baseline = baseline_pnl[baseline_pnl.index >= start_date]
            period_vc = vc_pnl[vc_pnl.index >= start_date]
        else:
            period_baseline = baseline_pnl
            period_vc = vc_pnl
            
        if period['end']:
            end_date = pd.to_datetime(period['end'])
            period_baseline = period_baseline[period_baseline.index <= end_date]
            period_vc = period_vc[period_vc.index <= end_date]
        
        # Calculate metrics for this period
        baseline_period_metrics = calculate_metrics(period_baseline, f"Baseline {period_name}")
        vc_period_metrics = calculate_metrics(period_vc, f"VolCore {period_name}")
        
        # Best allocation for this period
        best_wt = best_allocation['baseline_weight']
        vc_wt = best_allocation['vc_weight']
        period_blended = blend_portfolios(period_baseline, period_vc, best_wt, vc_wt)
        blended_period_metrics = calculate_metrics(period_blended, f"Blended {period_name}")
        
        print(f"  Baseline: {baseline_period_metrics['sharpe']:.3f} Sharpe")
        print(f"  VolCore:  {vc_period_metrics['sharpe']:.3f} Sharpe")
        print(f"  Blended:  {blended_period_metrics['sharpe']:.3f} Sharpe")
    
    print()
    
    # Save detailed daily series with best allocation
    print("-" * 80)
    print("SAVING OUTPUTS")
    print("-" * 80)
    
    best_wt = best_allocation['baseline_weight']
    vc_wt = best_allocation['vc_weight']
    
    output_df = pd.DataFrame({
        'date': common_dates,
        'baseline_pnl': baseline_pnl.values,
        'volcore_pnl': vc_pnl.values,
        'portfolio_pnl': (baseline_pnl * best_wt + vc_pnl * vc_wt).values,
        'baseline_weight': best_wt,
        'volcore_weight': vc_wt
    })
    
    output_path = output_dir / "daily_series.csv"
    output_df.to_csv(output_path, index=False)
    print(f"✓ Daily series: {output_path}")
    
    # Save weight comparison
    weight_comparison = {
        'best_allocation': best_allocation,
        'all_tests': [
            {
                'name': r['label'],
                'sharpe': r['sharpe'],
                'return': r['total_return'],
                'max_dd': r['max_drawdown']
            }
            for r in all_results
        ],
        'correlation': correlation
    }
    
    comparison_path = output_dir / "weight_comparison.json"
    with open(comparison_path, 'w') as f:
        json.dump(weight_comparison, f, indent=2)
    print(f"✓ Weight comparison: {comparison_path}")
    
    # Save validation report
    report_lines = [
        "BASELINE + VOLCORE VALIDATION REPORT",
        "=" * 80,
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Date range: {common_dates[0].date()} to {common_dates[-1].date()}",
        f"Days: {len(common_dates)}",
        "",
        "COMPONENT PERFORMANCE",
        "-" * 80,
        f"Baseline: {baseline_metrics['sharpe']:.3f} Sharpe",
        f"VolCore:  {vc_metrics['sharpe']:.3f} Sharpe",
        "",
        "CORRELATION",
        "-" * 80,
        f"Baseline vs VolCore: {correlation:.3f}",
        "",
        "BEST ALLOCATION",
        "-" * 80,
        f"Name: {best_allocation['name']}",
        f"Weights: {best_allocation['baseline_weight']:.0%} Baseline / {best_allocation['vc_weight']:.0%} VolCore",
        f"Sharpe: {best_allocation['sharpe']:.3f}",
        f"Marginal improvement: {(best_allocation['sharpe'] - baseline_metrics['sharpe']):+.3f}",
        "",
        "INTERPRETATION",
        "-" * 80,
    ]
    
    # Add interpretation
    marginal = best_allocation['sharpe'] - baseline_metrics['sharpe']
    if marginal > 0.10:
        report_lines.append("✓ VolCore adds significant value (+0.10+ Sharpe)")
        report_lines.append("✓ RECOMMEND: Include in portfolio")
    elif marginal > 0.05:
        report_lines.append("✓ VolCore adds moderate value (+0.05-0.10 Sharpe)")
        report_lines.append("✓ RECOMMEND: Include in portfolio")
    elif marginal > 0:
        report_lines.append("⚠ VolCore adds marginal value (<0.05 Sharpe)")
        report_lines.append("⚠ CONSIDER: Benefit may not justify complexity")
    else:
        report_lines.append("✗ VolCore reduces performance")
        report_lines.append("✗ RECOMMEND: Do not include")
    
    report_lines.append("")
    
    if abs(correlation) < 0.2:
        report_lines.append(f"✓ Excellent diversification (correlation: {correlation:.3f})")
    elif abs(correlation) < 0.4:
        report_lines.append(f"✓ Good diversification (correlation: {correlation:.3f})")
    else:
        report_lines.append(f"⚠ Limited diversification (correlation: {correlation:.3f})")
    
    report_path = output_dir / "validation_report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    print(f"✓ Validation report: {report_path}")
    
    print()
    print("="*80)
    print("ANALYSIS COMPLETE")
    print("="*80)
    print(f"\nOutputs saved to: {output_dir}")
    print("\nNext steps:")
    print("1. Review validation_report.txt for recommendations")
    print("2. Examine daily_series.csv for detailed performance")
    print("3. If VolCore adds value, proceed to test all three together")
    print("4. If not, investigate VolCore implementation")

if __name__ == "__main__":
    main()