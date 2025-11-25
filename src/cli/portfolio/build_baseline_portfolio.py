#!/usr/bin/env python3
"""
Build Baseline Portfolio (Equal-Weight) - POSITION-BASED BLENDING
------------------------------------------------------------------
Properly blends sleeve POSITIONS (not PnLs) for transparency and overlay support.

Key differences from previous version:
- Loads positions from sleeves (not pnl_net)
- Blends positions to get portfolio position
- Calculates pnl_gross from blended positions
- NO costs at portfolio level (already applied at sleeve level)
- Outputs: date, price, ret, sleeve_pos, portfolio_pos, pnl_gross
"""

import argparse
import json
import yaml
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, date
import sys

# Import blender
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from portfolio.blender import (
    blend_sleeves_equal_weight,
    calculate_sleeve_attribution,
    calculate_correlation_matrix
)


class CustomJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for datetime/numpy types"""
    def default(self, obj):
        if isinstance(obj, date):
            return obj.isoformat()
        elif isinstance(obj, (datetime, pd.Timestamp)):
            return obj.isoformat()
        elif isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif pd.isna(obj):
            return None
        elif isinstance(obj, Path):
            return str(obj)
        return super().default(obj)


def load_sleeve_data(sleeve_config: dict) -> tuple:
    """
    Load sleeve position and return data.
    
    Returns positions (for blending) and pnl_net (for attribution only).
    """
    
    sleeve_positions = {}
    sleeve_pnls = {}
    price_series = None
    ret_series = None
    dates = None
    
    for sleeve_name, sleeve_path in sleeve_config.items():
        print(f"Loading {sleeve_name} from {sleeve_path}...")
        
        df = pd.read_csv(sleeve_path)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        
        # Extract required columns
        if 'pos' not in df.columns:
            raise ValueError(f"Sleeve {sleeve_name} missing 'pos' column")
        if 'pnl_net' not in df.columns:
            raise ValueError(f"Sleeve {sleeve_name} missing 'pnl_net' column")
        
        sleeve_positions[sleeve_name] = df['pos']
        sleeve_pnls[sleeve_name] = df['pnl_net']
        
        # Get price and returns (should be same for all sleeves)
        if price_series is None and 'price' in df.columns:
            price_series = df['price']
        if ret_series is None and 'ret' in df.columns:
            ret_series = df['ret']
        
        # Track common dates
        if dates is None:
            dates = df.index
        else:
            dates = dates.union(df.index)
    
    # Reindex all to common dates
    for name in sleeve_positions:
        sleeve_positions[name] = sleeve_positions[name].reindex(dates)
        sleeve_pnls[name] = sleeve_pnls[name].reindex(dates)
    
    if price_series is not None:
        price_series = price_series.reindex(dates)
    if ret_series is not None:
        ret_series = ret_series.reindex(dates)
    
    print(f"\nLoaded {len(sleeve_positions)} sleeves")
    print(f"Date range: {dates.min().date()} to {dates.max().date()}")
    print(f"Total days: {len(dates)}")
    
    return sleeve_positions, sleeve_pnls, price_series, ret_series, dates


def blend_positions(sleeve_positions: dict) -> pd.Series:
    """
    Blend sleeve positions using equal weights.
    
    Args:
        sleeve_positions: Dict of sleeve name -> position series
        
    Returns:
        Portfolio position series (equal-weighted)
    """
    df = pd.DataFrame(sleeve_positions)
    n_sleeves = len(sleeve_positions)
    
    # Equal weight
    portfolio_pos = sum(df[name] / n_sleeves for name in sleeve_positions.keys())
    
    return portfolio_pos


def calculate_portfolio_pnl(portfolio_pos: pd.Series, ret_series: pd.Series) -> pd.Series:
    """
    Calculate portfolio PnL from blended positions.
    
    Uses T-1 position to earn T return (proper accrual).
    NO COSTS - costs already applied at sleeve level.
    
    Args:
        portfolio_pos: Blended portfolio position
        ret_series: Copper returns
        
    Returns:
        Portfolio pnl_gross (no costs)
    """
    # T-1 position earns T return
    pos_lagged = portfolio_pos.shift(1)
    pnl_gross = pos_lagged * ret_series
    
    return pnl_gross


def calculate_is_oos_metrics(portfolio_pnl: pd.Series, is_cutoff: str) -> dict:
    """Calculate IS/OOS performance metrics"""
    cutoff = pd.Timestamp(is_cutoff)
    
    is_pnl = portfolio_pnl[portfolio_pnl.index < cutoff]
    oos_pnl = portfolio_pnl[portfolio_pnl.index >= cutoff]
    
    def calc_sharpe(pnl):
        pnl = pnl.dropna()
        if len(pnl) == 0 or pnl.std() == 0:
            return 0.0
        return (pnl.mean() / pnl.std()) * np.sqrt(252)
    
    is_sharpe = calc_sharpe(is_pnl)
    oos_sharpe = calc_sharpe(oos_pnl)
    
    return {
        'is_sharpe': float(is_sharpe),
        'oos_sharpe': float(oos_sharpe),
        'oos_is_ratio': float(oos_sharpe / is_sharpe) if is_sharpe > 0 else 0.0,
        'is_days': int(len(is_pnl)),
        'oos_days': int(len(oos_pnl))
    }


def save_outputs(
    outdir: Path,
    dates: pd.DatetimeIndex,
    price_series: pd.Series,
    ret_series: pd.Series,
    sleeve_positions: dict,
    portfolio_pos: pd.Series,
    portfolio_pnl: pd.Series,
    sleeve_pnls: dict,
    attribution: dict,
    correlation: pd.DataFrame,
    is_oos: dict,
    config: dict
) -> None:
    """Save all outputs with proper columns"""
    
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    
    # 1. Daily series - PROPER COLUMNS
    print("\nSaving daily series...")
    daily_df = pd.DataFrame(index=dates)
    daily_df['price'] = price_series
    daily_df['ret'] = ret_series
    
    # Add sleeve positions
    for name, pos in sleeve_positions.items():
        daily_df[f'{name}_pos'] = pos
    
    # Add portfolio position and PnL
    daily_df['portfolio_pos'] = portfolio_pos
    daily_df['pnl_gross'] = portfolio_pnl
    
    daily_df.to_csv(outdir / 'daily_series.csv')
    print(f"  ✓ Saved: daily_series.csv")
    print(f"    Columns: {', '.join(daily_df.columns)}")
    
    # 2. Summary metrics
    print("Saving summary metrics...")
    summary = {
        'portfolio': attribution['Portfolio'],
        'is_oos': is_oos,
        'diversification': attribution['Diversification'],
        'generated': datetime.now().isoformat(),
        'config': config
    }
    with open(outdir / 'summary_metrics.json', 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, cls=CustomJSONEncoder)
    print(f"  ✓ Saved: summary_metrics.json")
    
    # 3. Sleeve attribution
    print("Saving sleeve attribution...")
    with open(outdir / 'sleeve_attribution.json', 'w', encoding='utf-8') as f:
        json.dump(attribution, f, indent=2, cls=CustomJSONEncoder)
    print(f"  ✓ Saved: sleeve_attribution.json")
    
    # 4. Correlation matrix
    print("Saving correlation matrix...")
    correlation.to_csv(outdir / 'correlation_matrix.csv')
    print(f"  ✓ Saved: correlation_matrix.csv")
    
    # 5. Validation report
    print("Saving validation report...")
    report = generate_validation_report(attribution, is_oos, correlation)
    with open(outdir / 'validation_report.txt', 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"  ✓ Saved: validation_report.txt")


def generate_validation_report(attribution: dict, is_oos: dict, correlation: pd.DataFrame) -> str:
    """Generate human-readable validation report"""
    
    lines = []
    lines.append("="*80)
    lines.append("BASELINE PORTFOLIO - VALIDATION REPORT")
    lines.append("="*80)
    lines.append("")
    
    # Portfolio performance
    pf = attribution['Portfolio']
    lines.append("PORTFOLIO PERFORMANCE (Equal-Weight)")
    lines.append("-" * 40)
    lines.append(f"Sharpe Ratio:    {pf['sharpe']:>8.3f}")
    lines.append(f"Annual Return:   {pf['annual_return']*100:>7.1f}%")
    lines.append(f"Annual Vol:      {pf['annual_vol']*100:>7.1f}%")
    lines.append("")
    
    # Individual sleeves
    lines.append("INDIVIDUAL SLEEVES")
    lines.append("-" * 40)
    for name, metrics in attribution.items():
        if name in ['Portfolio', 'Diversification']:
            continue
        lines.append(f"{name:<20} Sharpe: {metrics['sharpe']:>6.3f}")
    lines.append("")
    
    # Diversification
    div = attribution['Diversification']
    lines.append("DIVERSIFICATION BENEFIT")
    lines.append("-" * 40)
    lines.append(f"Best sleeve Sharpe:  {div['best_sleeve_sharpe']:>6.3f}")
    lines.append(f"Portfolio Sharpe:    {div['portfolio_sharpe']:>6.3f}")
    lines.append(f"Improvement:         {div['improvement_pct']:>6.1f}%")
    lines.append("")
    
    # IS/OOS
    lines.append("IN-SAMPLE vs OUT-OF-SAMPLE")
    lines.append("-" * 40)
    lines.append(f"IS Sharpe:       {is_oos['is_sharpe']:>8.3f} ({is_oos['is_days']} days)")
    lines.append(f"OOS Sharpe:      {is_oos['oos_sharpe']:>8.3f} ({is_oos['oos_days']} days)")
    lines.append(f"OOS/IS Ratio:    {is_oos['oos_is_ratio']:>8.1%}")
    lines.append("")
    
    # Validation checks
    lines.append("VALIDATION CHECKS")
    lines.append("-" * 40)
    
    if pf['sharpe'] > 0:
        lines.append("✅ Portfolio Sharpe > 0")
    else:
        lines.append("❌ Portfolio Sharpe <= 0")
    
    if div['improvement_pct'] > 0:
        lines.append(f"✅ Diversification benefit: +{div['improvement_pct']:.1f}%")
    else:
        lines.append("⚠️ No diversification benefit")
    
    if is_oos['oos_is_ratio'] >= 0.80:
        lines.append(f"✅ OOS retention: {is_oos['oos_is_ratio']:.1%} (good)")
    elif is_oos['oos_is_ratio'] >= 0.60:
        lines.append(f"⚠️ OOS retention: {is_oos['oos_is_ratio']:.1%} (acceptable)")
    else:
        lines.append(f"❌ OOS retention: {is_oos['oos_is_ratio']:.1%} (poor)")
    
    avg_corr = correlation.values[np.triu_indices_from(correlation.values, k=1)].mean()
    if avg_corr < 0.4:
        lines.append(f"✅ Low avg correlation: {avg_corr:.3f} (good diversification)")
    elif avg_corr < 0.6:
        lines.append(f"⚠️ Moderate correlation: {avg_corr:.3f}")
    else:
        lines.append(f"❌ High correlation: {avg_corr:.3f} (limited diversification)")
    
    lines.append("")
    lines.append("NOTE: Portfolio PnL is gross (no costs - already applied at sleeve level)")
    lines.append("")
    lines.append("="*80)
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='Build baseline equal-weight portfolio')
    parser.add_argument('--config', required=True, help='Path to config YAML')
    parser.add_argument('--outdir', required=True, help='Output directory')
    
    args = parser.parse_args()
    
    # Load config
    print(f"Loading config from {args.config}...")
    with open(args.config, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # Load sleeve data (positions + pnls)
    sleeve_positions, sleeve_pnls, price_series, ret_series, dates = load_sleeve_data(config['sleeves'])
    
    # Blend positions (Layer 3)
    print("\nBlending positions (equal-weight)...")
    portfolio_pos = blend_positions(sleeve_positions)
    
    # Calculate portfolio PnL from blended positions
    print("Calculating portfolio PnL from blended positions...")
    portfolio_pnl = calculate_portfolio_pnl(portfolio_pos, ret_series)
    
    # Calculate metrics (use pnl_net for sleeve attribution, pnl_gross for portfolio)
    print("Calculating attribution...")
    attribution = calculate_sleeve_attribution(sleeve_pnls, portfolio_pnl)
    
    print("Calculating correlations...")
    correlation = calculate_correlation_matrix(sleeve_pnls)
    
    print("Calculating IS/OOS metrics...")
    is_oos = calculate_is_oos_metrics(portfolio_pnl, config['is_oos_cutoff'])
    
    # Save outputs
    save_outputs(
        Path(args.outdir),
        dates,
        price_series,
        ret_series,
        sleeve_positions,
        portfolio_pos,
        portfolio_pnl,
        sleeve_pnls,
        attribution,
        correlation,
        is_oos,
        config
    )
    
    # Print summary
    print("\n" + "="*80)
    print("PORTFOLIO BUILD COMPLETE")
    print("="*80)
    print(f"\nPortfolio Sharpe:     {attribution['Portfolio']['sharpe']:.3f}")
    print(f"IS Sharpe:            {is_oos['is_sharpe']:.3f}")
    print(f"OOS Sharpe:           {is_oos['oos_sharpe']:.3f}")
    print(f"OOS/IS Ratio:         {is_oos['oos_is_ratio']:.1%}")
    print(f"Diversification:      +{attribution['Diversification']['improvement_pct']:.1f}%")
    print(f"\nOutputs saved to: {args.outdir}")
    print("\n✅ Position-based blending (transparent for overlays)")
    print("✅ PnL gross (no costs - already at sleeve level)")
    print("\nNext step: Review daily_series.csv - now has positions!")


if __name__ == '__main__':
    main()