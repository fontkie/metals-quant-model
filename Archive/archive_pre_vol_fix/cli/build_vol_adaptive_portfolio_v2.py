#!/usr/bin/env python3
"""
Build Adaptive Portfolio v2
============================

Applies regime-specific weights to build portfolio returns.
Handles regime transitions with turnover costs.

Key features:
  - Reads regime weights from YAML
  - Classifies each day into IV regime (no forward bias)
  - Applies regime-appropriate weights
  - Calculates turnover from regime transitions
  - Compares IS vs OOS performance

Author: Claude (ex-Renaissance) + Kieran
Date: November 17, 2025
Version: 2.0
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import yaml
import json


def load_config(config_path: str) -> dict:
    """Load portfolio configuration YAML."""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config


def load_regime_weights(weights_path: str) -> dict:
    """Load regime-specific weights from YAML."""
    with open(weights_path, 'r') as f:
        data = yaml.safe_load(f)
    
    # Extract regime weights
    regime_weights = data.get('regime_weights', {})
    metadata = data.get('optimization_metadata', {})
    
    print(f"  ✓ Loaded weights from: {weights_path}")
    print(f"    Generated: {metadata.get('date_generated', 'unknown')}")
    print(f"    IS Period: {metadata.get('is_start', '?')} to {metadata.get('is_end', '?')}")
    print(f"    Regime Type: {metadata.get('regime_type', 'unknown')}")
    
    return regime_weights, metadata


def load_iv_data(iv_path: str) -> pd.DataFrame:
    """Load implied volatility data."""
    df = pd.read_csv(iv_path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    
    print(f"  ✓ Loaded IV data: {len(df)} days ({df['date'].min().date()} to {df['date'].max().date()})")
    
    return df


def classify_iv_regimes(iv_df: pd.DataFrame, lookback: int = 252, 
                        low_pct: float = 0.33, high_pct: float = 0.67,
                        regime_lag: int = 1) -> pd.DataFrame:
    """
    Classify days into IV regimes using rolling percentile.
    
    Uses EXPANDING window initially, then rolling lookback.
    No forward bias - percentile calculated on historical data only.
    
    PUBLICATION TIMING:
        regime_lag = 1 (default): Use T-1's regime for T's weights (conservative)
        regime_lag = 0: Use T's regime for T's weights (assumes same-day execution)
        
        *** TO TEST T vs T-1: Change --regime-lag parameter in batch file ***
    """
    df = iv_df.copy()
    
    # Calculate rolling percentile (no forward bias)
    iv_pct = []
    
    for i in range(len(df)):
        if i < 20:  # Minimum history requirement
            iv_pct.append(np.nan)
        else:
            window_size = min(lookback, i + 1)
            historical_iv = df['iv'].iloc[max(0, i + 1 - window_size):i + 1]
            current_iv = df['iv'].iloc[i]
            
            pct = (historical_iv <= current_iv).sum() / len(historical_iv)
            iv_pct.append(pct)
    
    df['iv_percentile'] = iv_pct
    
    # Classify regime
    def classify_regime(pct):
        if pd.isna(pct):
            return np.nan
        elif pct <= low_pct:
            return 'LOW'
        elif pct <= high_pct:
            return 'MEDIUM'
        else:
            return 'HIGH'
    
    df['vol_regime'] = df['iv_percentile'].apply(classify_regime)
    
    # Apply regime lag (T-1 conservative approach)
    if regime_lag > 0:
        df['vol_regime'] = df['vol_regime'].shift(regime_lag)
        df['iv_percentile'] = df['iv_percentile'].shift(regime_lag)
        print(f"  ⏰ Regime lag: T-{regime_lag} (using {regime_lag}-day lagged classification)")
    else:
        print(f"  ⏰ Regime lag: T (same-day classification)")
    
    return df


def load_sleeve_returns(config: dict, start_date: str = None, end_date: str = None) -> tuple:
    """Load sleeve returns from config-specified paths."""
    sleeve_info = {}
    dfs = {}
    
    sleeves_cfg = config.get('sleeves', {})
    
    for sleeve_name, sleeve_cfg in sleeves_cfg.items():
        if not sleeve_cfg.get('enabled', True):
            continue
        
        csv_path = sleeve_cfg.get('path')
        if not csv_path or not Path(csv_path).exists():
            print(f"  WARNING: Path not found for {sleeve_name}: {csv_path}")
            continue
        
        try:
            df = pd.read_csv(csv_path)
            df['date'] = pd.to_datetime(df['date'])
            
            # Get return column
            if 'pnl_net' in df.columns:
                ret_col = 'pnl_net'
            elif 'pnl_gross' in df.columns:
                ret_col = 'pnl_gross'
            elif 'ret' in df.columns:
                ret_col = 'ret'
            else:
                print(f"  WARNING: {sleeve_name} missing return column")
                continue
            
            df = df[['date', ret_col]].rename(columns={ret_col: f'{sleeve_name}_ret'})
            dfs[sleeve_name] = df
            
            sleeve_info[sleeve_name] = {
                'path': csv_path,
                'data_start': df['date'].min().strftime('%Y-%m-%d'),
                'data_end': df['date'].max().strftime('%Y-%m-%d')
            }
            
            print(f"  ✓ Loaded {sleeve_name}: {len(df)} days")
            
        except Exception as e:
            print(f"  ✗ Failed to load {sleeve_name}: {e}")
    
    if len(dfs) == 0:
        raise ValueError("No sleeves loaded!")
    
    # Merge all sleeves
    sleeve_names = list(dfs.keys())
    merged = dfs[sleeve_names[0]]
    
    for name in sleeve_names[1:]:
        merged = merged.merge(dfs[name], on='date', how='outer')
    
    merged = merged.sort_values('date').reset_index(drop=True)
    
    # Fill missing returns with 0
    for name in sleeve_names:
        ret_col = f'{name}_ret'
        merged[ret_col] = merged[ret_col].fillna(0.0)
    
    # Filter date range
    if start_date:
        merged = merged[merged['date'] >= pd.to_datetime(start_date)]
    if end_date:
        merged = merged[merged['date'] <= pd.to_datetime(end_date)]
    
    return merged, sleeve_info


def build_adaptive_portfolio(returns_df: pd.DataFrame, regime_df: pd.DataFrame,
                              regime_weights: dict, cost_bp: float = 3.0) -> pd.DataFrame:
    """
    Build portfolio returns with regime-specific weights.
    
    Handles:
      - Daily regime classification
      - Weight changes on regime transitions
      - Turnover calculation for costs
    """
    # Merge returns with regime
    portfolio = returns_df.merge(
        regime_df[['date', 'vol_regime', 'iv_percentile']], 
        on='date', 
        how='inner'
    )
    
    # Filter to valid regimes only
    portfolio = portfolio[portfolio['vol_regime'].notna()].copy()
    portfolio = portfolio.sort_values('date').reset_index(drop=True)
    
    print(f"  Portfolio days: {len(portfolio)}")
    
    # Get sleeve names from first regime's weights
    sleeve_names = list(list(regime_weights.values())[0].keys())
    ret_cols = [f'{name}_ret' for name in sleeve_names]
    
    # Initialize columns for each sleeve's weight
    for name in sleeve_names:
        portfolio[f'w_{name}'] = 0.0
    
    # Apply regime-specific weights
    for regime, weights in regime_weights.items():
        mask = portfolio['vol_regime'] == regime
        for name, weight in weights.items():
            portfolio.loc[mask, f'w_{name}'] = weight
    
    # Calculate portfolio return (gross of costs)
    portfolio['ret_gross'] = 0.0
    for name in sleeve_names:
        portfolio['ret_gross'] += portfolio[f'w_{name}'] * portfolio[f'{name}_ret']
    
    # Calculate turnover from regime transitions
    portfolio['turnover'] = 0.0
    
    # First day has full deployment (turnover = 1.0)
    portfolio.loc[portfolio.index[0], 'turnover'] = 1.0
    
    # Subsequent days: turnover = sum of absolute weight changes
    for i in range(1, len(portfolio)):
        turnover = 0.0
        for name in sleeve_names:
            w_col = f'w_{name}'
            w_prev = portfolio.loc[portfolio.index[i-1], w_col]
            w_curr = portfolio.loc[portfolio.index[i], w_col]
            turnover += abs(w_curr - w_prev)
        portfolio.loc[portfolio.index[i], 'turnover'] = turnover
    
    # Calculate costs (turnover * cost_bp / 10000)
    portfolio['cost'] = portfolio['turnover'] * cost_bp / 10000
    
    # Net return
    portfolio['ret_net'] = portfolio['ret_gross'] - portfolio['cost']
    
    # Summary
    regime_changes = (portfolio['vol_regime'] != portfolio['vol_regime'].shift(1)).sum() - 1
    total_turnover = portfolio['turnover'].sum()
    avg_daily_turnover = portfolio['turnover'].mean()
    
    print(f"  Regime changes: {regime_changes}")
    print(f"  Total turnover: {total_turnover:.2f}")
    print(f"  Avg daily turnover: {avg_daily_turnover:.4f}")
    print(f"  Annualized turnover: {avg_daily_turnover * 252:.2f}")
    
    return portfolio


def calculate_metrics(portfolio_df: pd.DataFrame, label: str = "Full") -> dict:
    """Calculate performance metrics for a portfolio series."""
    rets = portfolio_df['ret_net'].values
    
    # Basic metrics
    mean_ret = rets.mean() * 252
    vol = rets.std() * np.sqrt(252)
    sharpe = mean_ret / vol if vol > 0 else 0
    
    # Max drawdown
    cumulative = (1 + rets).cumprod()
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = (cumulative - running_max) / running_max
    max_dd = drawdowns.min()
    
    # Calmar ratio
    calmar = mean_ret / abs(max_dd) if max_dd != 0 else 0
    
    # Cost drag
    total_cost = portfolio_df['cost'].sum()
    cost_drag_annual = total_cost / (len(portfolio_df) / 252)
    cost_drag_bps = cost_drag_annual * 10000
    
    # Regime stats
    regime_days = portfolio_df['vol_regime'].value_counts()
    regime_pct = regime_days / len(portfolio_df)
    
    metrics = {
        'sharpe': float(sharpe),
        'annual_return': float(mean_ret),
        'annual_vol': float(vol),
        'max_drawdown': float(max_dd),
        'calmar': float(calmar),
        'cost_drag_bps': float(cost_drag_bps),
        'obs': int(len(rets)),
        'start_date': portfolio_df['date'].min().strftime('%Y-%m-%d'),
        'end_date': portfolio_df['date'].max().strftime('%Y-%m-%d'),
        'regime_distribution': {regime: float(regime_pct.get(regime, 0)) for regime in ['LOW', 'MEDIUM', 'HIGH']},
        'total_turnover': float(portfolio_df['turnover'].sum()),
        'regime_changes': int((portfolio_df['vol_regime'] != portfolio_df['vol_regime'].shift(1)).sum() - 1)
    }
    
    return metrics


def save_outputs(portfolio_df: pd.DataFrame, metrics: dict, weights_metadata: dict,
                 config: dict, args, output_dir: Path) -> tuple:
    """Save portfolio daily series and summary metrics."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # 1. Save daily series CSV
    csv_filename = f'daily_series_{timestamp}.csv'
    csv_path = output_dir / csv_filename
    
    # Select columns to save
    sleeve_names = [col.replace('w_', '') for col in portfolio_df.columns if col.startswith('w_')]
    save_cols = ['date', 'vol_regime', 'iv_percentile']
    save_cols += [f'{name}_ret' for name in sleeve_names]
    save_cols += [f'w_{name}' for name in sleeve_names]
    save_cols += ['ret_gross', 'turnover', 'cost', 'ret_net']
    
    portfolio_df[save_cols].to_csv(csv_path, index=False)
    
    # Save latest version
    latest_csv = output_dir / 'daily_series_latest.csv'
    portfolio_df[save_cols].to_csv(latest_csv, index=False)
    
    # 2. Save summary metrics JSON
    json_filename = f'summary_metrics_{timestamp}.json'
    json_path = output_dir / json_filename
    
    summary = {
        'timestamp': timestamp,
        'config_file': str(args.config),
        'weights_file': str(args.weights),
        'iv_file': str(args.iv_file),
        'regime_lag': args.regime_lag,
        'regime_lag_note': f'T-{args.regime_lag} classification',
        'weights_metadata': weights_metadata,
        'metrics': metrics
    }
    
    with open(json_path, 'w') as f:
        json.dump(summary, f, indent=2)
    
    # Save latest version
    latest_json = output_dir / 'summary_metrics_latest.json'
    with open(latest_json, 'w') as f:
        json.dump(summary, f, indent=2)
    
    return csv_path, json_path


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Apply adaptive regime weights to build portfolio returns"
    )
    
    parser.add_argument(
        '--config',
        required=True,
        help='Path to portfolio configuration YAML'
    )
    
    parser.add_argument(
        '--weights',
        required=True,
        help='Path to regime weights YAML (from build_vol_adaptive_weights_v2.py)'
    )
    
    parser.add_argument(
        '--iv-file',
        required=True,
        help='Path to implied volatility CSV'
    )
    
    parser.add_argument(
        '--outdir',
        default='outputs/Copper/VolAdaptive',
        help='Output directory for portfolio files'
    )
    
    parser.add_argument(
        '--split-date',
        default='2019-01-01',
        help='Date to split IS vs OOS periods'
    )
    
    parser.add_argument(
        '--lookback',
        type=int,
        default=252,
        help='Rolling window for IV percentile calculation'
    )
    
    parser.add_argument(
        '--low-pct',
        type=float,
        default=0.33,
        help='Percentile threshold for LOW regime'
    )
    
    parser.add_argument(
        '--high-pct',
        type=float,
        default=0.67,
        help='Percentile threshold for HIGH regime'
    )
    
    parser.add_argument(
        '--regime-lag',
        type=int,
        default=1,
        help='Days to lag regime classification. 1=T-1 (conservative), 0=T (same-day). Default: 1'
    )
    
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Print header
    print("\n" + "=" * 80)
    print("ADAPTIVE PORTFOLIO BUILDER v2.0")
    print("=" * 80)
    print(f"Config:      {args.config}")
    print(f"Weights:     {args.weights}")
    print(f"IV File:     {args.iv_file}")
    print(f"Split Date:  {args.split_date}")
    print(f"Regime Lag:  T-{args.regime_lag} ({'conservative' if args.regime_lag == 1 else 'same-day' if args.regime_lag == 0 else f'{args.regime_lag}-day'})")
    print(f"Output:      {args.outdir}")
    print(f"Timestamp:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Step 1: Load configuration
        print("\n📋 Loading configuration...")
        config = load_config(args.config)
        
        # Step 2: Load regime weights
        print("\n⚖️  Loading regime weights...")
        regime_weights, weights_metadata = load_regime_weights(args.weights)
        
        for regime in ['LOW', 'MEDIUM', 'HIGH']:
            if regime in regime_weights:
                print(f"\n  {regime} regime weights:")
                for name, weight in regime_weights[regime].items():
                    print(f"    {name:20s}: {weight:.4f}")
        
        # Step 3: Load IV data and classify regimes
        print("\n📈 Loading IV data and classifying regimes...")
        iv_df = load_iv_data(args.iv_file)
        regime_df = classify_iv_regimes(
            iv_df, 
            lookback=args.lookback,
            low_pct=args.low_pct,
            high_pct=args.high_pct,
            regime_lag=args.regime_lag
        )
        
        # Step 4: Load sleeve returns
        print("\n📂 Loading sleeve returns...")
        returns_df, sleeve_info = load_sleeve_returns(config)
        print(f"  ✓ {len(returns_df)} total trading days")
        
        # Step 5: Build adaptive portfolio
        print("\n🔧 Building adaptive portfolio...")
        cost_bp = config.get('costs', {}).get('transaction_cost_bp', 3)
        print(f"  Transaction cost: {cost_bp} bp")
        
        portfolio_df = build_adaptive_portfolio(
            returns_df, regime_df, regime_weights, cost_bp
        )
        
        # Step 6: Calculate metrics
        print("\n📊 Calculating performance metrics...")
        
        split_date = pd.to_datetime(args.split_date)
        
        # Full period
        metrics_full = calculate_metrics(portfolio_df, "Full")
        print(f"\n  Full Period ({metrics_full['start_date']} to {metrics_full['end_date']}):")
        print(f"    Sharpe:        {metrics_full['sharpe']:.4f}")
        print(f"    Annual Return: {metrics_full['annual_return']*100:.2f}%")
        print(f"    Annual Vol:    {metrics_full['annual_vol']*100:.2f}%")
        print(f"    Max Drawdown:  {metrics_full['max_drawdown']*100:.2f}%")
        print(f"    Calmar:        {metrics_full['calmar']:.4f}")
        print(f"    Cost Drag:     {metrics_full['cost_drag_bps']:.2f} bps/year")
        print(f"    Regime Changes: {metrics_full['regime_changes']}")
        
        # In-sample
        is_data = portfolio_df[portfolio_df['date'] < split_date]
        if len(is_data) > 0:
            metrics_is = calculate_metrics(is_data, "IS")
            print(f"\n  In-Sample ({metrics_is['start_date']} to {metrics_is['end_date']}):")
            print(f"    Sharpe:        {metrics_is['sharpe']:.4f}")
            print(f"    Annual Return: {metrics_is['annual_return']*100:.2f}%")
            print(f"    Cost Drag:     {metrics_is['cost_drag_bps']:.2f} bps/year")
            print(f"    Regime Changes: {metrics_is['regime_changes']}")
        else:
            metrics_is = {}
        
        # Out-of-sample
        oos_data = portfolio_df[portfolio_df['date'] >= split_date]
        if len(oos_data) > 0:
            metrics_oos = calculate_metrics(oos_data, "OOS")
            print(f"\n  Out-of-Sample ({metrics_oos['start_date']} to {metrics_oos['end_date']}):")
            print(f"    Sharpe:        {metrics_oos['sharpe']:.4f}")
            print(f"    Annual Return: {metrics_oos['annual_return']*100:.2f}%")
            print(f"    Cost Drag:     {metrics_oos['cost_drag_bps']:.2f} bps/year")
            print(f"    Regime Changes: {metrics_oos['regime_changes']}")
        else:
            metrics_oos = {}
        
        # Degradation analysis
        if metrics_is and metrics_oos:
            sharpe_degradation = (metrics_oos['sharpe'] - metrics_is['sharpe']) / metrics_is['sharpe'] * 100
            print(f"\n  📉 OOS Degradation: {sharpe_degradation:.1f}%")
        
        # Step 7: Save outputs
        print(f"\n💾 Saving outputs to {args.outdir}...")
        output_dir = Path(args.outdir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        all_metrics = {
            'full': metrics_full,
            'is': metrics_is,
            'oos': metrics_oos,
            'split_date': args.split_date
        }
        
        csv_path, json_path = save_outputs(
            portfolio_df, all_metrics, weights_metadata, config, args, output_dir
        )
        
        print(f"  ✓ Saved {csv_path.name}")
        print(f"  ✓ Saved {json_path.name}")
        print(f"  ✓ Saved daily_series_latest.csv")
        print(f"  ✓ Saved summary_metrics_latest.json")
        
        # Final summary
        print("\n" + "=" * 80)
        print("BUILD COMPLETE")
        print("=" * 80)
        print(f"✅ Adaptive portfolio built with {len(regime_weights)} regimes")
        print(f"✅ Full Period Sharpe: {metrics_full['sharpe']:.4f}")
        if metrics_is and metrics_oos:
            print(f"✅ IS Sharpe: {metrics_is['sharpe']:.4f}")
            print(f"✅ OOS Sharpe: {metrics_oos['sharpe']:.4f}")
            print(f"✅ OOS Degradation: {sharpe_degradation:.1f}%")
        print(f"\nOutput files:")
        print(f"  {csv_path}")
        print(f"  {json_path}")
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