#!/usr/bin/env python3
"""
TrendImpulse V5 - Stage 3 OOS Validation
========================================
One-Time Honest Test on Out-of-Sample Data (2019-2025)

âš ï¸  CRITICAL RULES âš ï¸ 
1. Run this script ONCE only
2. Report results honestly (even if bad)
3. NEVER adjust parameters after seeing OOS results
4. Use OOS Sharpe as production expectation
5. If OOS < 0.25: Don't deploy (parameters are overfit)

Expected Results:
- OOS Sharpe: 0.30-0.40 (60-80% of IS is normal)
- If OOS/IS < 60%: Forward bias concern
- If OOS/IS > 120%: Lucky or data error

Time: ~1 minute
"""

import sys
import json
from pathlib import Path
from typing import Dict

import pandas as pd
import numpy as np

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))


def calculate_detailed_metrics(
    positions: pd.Series,
    returns: pd.Series,
    target_vol: float = 0.10,
    cost_bps: float = 3.0,
) -> Dict:
    """Calculate comprehensive strategy metrics"""
    # Vol targeting
    pos_abs = positions.abs()
    strategy_returns_raw = positions.shift(1) * returns
    realized_vol = strategy_returns_raw.rolling(63).std() * np.sqrt(252)
    scale = np.where(realized_vol > 0.01, target_vol / realized_vol, 1.0)
    scale = np.clip(scale, 0.2, 3.0)
    positions_scaled = positions * scale
    
    # Strategy returns
    strategy_returns = positions_scaled.shift(1) * returns
    
    # Transaction costs
    turnover = positions_scaled.diff().abs()
    costs = turnover * (cost_bps / 10000)
    strategy_returns_net = strategy_returns - costs
    
    # Metrics
    valid_returns = strategy_returns_net.dropna()
    valid_returns_gross = strategy_returns.dropna()
    
    if len(valid_returns) < 252:
        return None
    
    annual_return = valid_returns.mean() * 252
    annual_return_gross = valid_returns_gross.mean() * 252
    annual_vol = valid_returns.std() * np.sqrt(252)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0.0
    sharpe_gross = annual_return_gross / annual_vol if annual_vol > 0 else 0.0
    
    # Max drawdown
    cum_returns = (1 + valid_returns).cumprod()
    running_max = cum_returns.expanding().max()
    drawdown = (cum_returns - running_max) / running_max
    max_drawdown = drawdown.min()
    
    # Turnover
    annual_turnover = turnover.sum() * 252 / len(turnover)
    
    # Activity
    pct_active = (pos_abs > 0.01).mean() * 100
    
    # Win rate
    winning_days = (valid_returns > 0).sum()
    total_days = len(valid_returns)
    win_rate = winning_days / total_days if total_days > 0 else 0.0
    
    return {
        'sharpe': sharpe,
        'sharpe_gross': sharpe_gross,
        'annual_return': annual_return,
        'annual_return_gross': annual_return_gross,
        'annual_vol': annual_vol,
        'max_drawdown': max_drawdown,
        'annual_turnover': annual_turnover,
        'pct_active': pct_active,
        'win_rate': win_rate,
        'cost_drag_sharpe': sharpe_gross - sharpe,
        'cost_drag_return': annual_return_gross - annual_return,
    }


def generate_trendimpulse_v5_signal_with_regime(
    df: pd.DataFrame,
    momentum_window: int,
    entry_threshold: float,
    exit_threshold: float,
    low_vol_threshold: float,
    medium_vol_threshold: float,
    low_vol_scale: float,
    medium_vol_scale: float,
    high_vol_scale: float,
    vol_window: int = 63,
    vol_percentile_window: int = 252,
    weekly_updates: bool = True,
    update_frequency: int = 5,
) -> pd.Series:
    """TrendImpulse signal WITH vol regime scaling"""
    price = df['price'].values
    n = len(price)
    returns = df['price'].pct_change().values
    
    # Calculate momentum
    momentum = np.zeros(n)
    for i in range(momentum_window, n):
        momentum[i] = price[i] / price[i - momentum_window] - 1
    
    # Generate base position
    position_raw = np.zeros(n)
    current_state = 0
    
    for i in range(momentum_window, n):
        mom = momentum[i]
        
        if current_state == 0:
            if mom > entry_threshold:
                current_state = 1
            elif mom < -entry_threshold:
                current_state = -1
        elif current_state == 1:
            if mom < -entry_threshold:
                current_state = -1
            elif mom < exit_threshold:
                current_state = 0
        elif current_state == -1:
            if mom > entry_threshold:
                current_state = 1
            elif mom > -exit_threshold:
                current_state = 0
        
        position_raw[i] = current_state
    
    # Calculate rolling vol
    vol = pd.Series(returns).rolling(vol_window, min_periods=vol_window).std() * np.sqrt(252)
    vol = vol.values
    
    # Calculate percentile rank
    vol_percentile = np.zeros(n)
    for i in range(vol_percentile_window, n):
        window = vol[i - vol_percentile_window + 1:i + 1]
        window = window[~np.isnan(window)]
        if len(window) > 0:
            vol_percentile[i] = (window < vol[i]).sum() / len(window)
    
    # Apply regime scaling
    regime_scale = np.ones(n)
    
    if weekly_updates:
        last_scale = 1.0
        for i in range(n):
            if i % update_frequency == 0 or i < vol_window:
                if np.isnan(vol_percentile[i]) or i < vol_percentile_window:
                    last_scale = 1.0
                elif vol_percentile[i] < low_vol_threshold:
                    last_scale = low_vol_scale
                elif vol_percentile[i] < medium_vol_threshold:
                    last_scale = medium_vol_scale
                else:
                    last_scale = high_vol_scale
            regime_scale[i] = last_scale
    else:
        for i in range(n):
            if np.isnan(vol_percentile[i]) or i < vol_percentile_window:
                regime_scale[i] = 1.0
            elif vol_percentile[i] < low_vol_threshold:
                regime_scale[i] = low_vol_scale
            elif vol_percentile[i] < medium_vol_threshold:
                regime_scale[i] = medium_vol_scale
            else:
                regime_scale[i] = high_vol_scale
    
    position_final = position_raw * regime_scale
    
    return pd.Series(position_final, index=df.index)


def validate_oos(
    df_oos: pd.DataFrame,
    best_params: Dict,
    output_dir: Path,
) -> Dict:
    """
    Test optimized parameters on out-of-sample data.
    
    âš ï¸  This should be run ONCE only after Stage 1 + Stage 2 complete.
    """
    print(f"\n{'='*70}")
    print("TRENDIMPULSE V5 - OUT-OF-SAMPLE VALIDATION")
    print("âš ï¸  ONE-TIME TEST - RESULTS REPORTED HONESTLY")
    print(f"{'='*70}")
    print(f"OOS Period: {df_oos['date'].min()} to {df_oos['date'].max()}")
    print(f"Observations: {len(df_oos)}")
    print()
    
    print("Optimized Parameters (from Stage 1 + Stage 2):")
    for k, v in best_params.items():
        if k != 'sharpe':  # Don't print IS sharpe here
            print(f"  {k}: {v}")
    print()
    
    # Generate signal
    print("Generating OOS signals with optimized parameters...")
    # Filter out non-parameter keys (like 'sharpe' if present)
    signal_params = {k: v for k, v in best_params.items() 
                     if k in ['momentum_window', 'entry_threshold', 'exit_threshold',
                             'low_vol_threshold', 'medium_vol_threshold', 
                             'low_vol_scale', 'medium_vol_scale', 'high_vol_scale',
                             'vol_window', 'vol_percentile_window', 
                             'weekly_updates', 'update_frequency']}
    signal = generate_trendimpulse_v5_signal_with_regime(df_oos, **signal_params)
    
    # Calculate metrics
    returns = df_oos['price'].pct_change()
    metrics = calculate_detailed_metrics(
        positions=signal,
        returns=returns,
        target_vol=0.10,
        cost_bps=3.0,
    )
    
    if metrics is None:
        print("ERROR: Insufficient data for OOS validation")
        return None
    
    print(f"\n{'='*70}")
    print("OUT-OF-SAMPLE RESULTS (2019-2025)")
    print(f"{'='*70}")
    
    print(f"\nPerformance:")
    print(f"  Net Sharpe:        {metrics['sharpe']:+.3f}")
    print(f"  Gross Sharpe:      {metrics['sharpe_gross']:+.3f}")
    print(f"  Annual Return:     {metrics['annual_return']*100:+.2f}%")
    print(f"  Annual Vol:        {metrics['annual_vol']*100:.2f}%")
    print(f"  Max Drawdown:      {metrics['max_drawdown']*100:.2f}%")
    
    print(f"\nTrading Characteristics:")
    print(f"  Turnover:          {metrics['annual_turnover']:.1f}x")
    print(f"  Activity:          {metrics['pct_active']:.1f}%")
    print(f"  Win Rate:          {metrics['win_rate']*100:.1f}%")
    
    print(f"\nCost Impact:")
    print(f"  Cost Drag (Sharpe): {metrics['cost_drag_sharpe']:.3f}")
    print(f"  Cost Drag (Return): {metrics['cost_drag_return']*100:.2f}%")
    
    # Compare to in-sample
    is_sharpe = best_params.get('sharpe', 0.0)
    oos_is_ratio = metrics['sharpe'] / is_sharpe if is_sharpe > 0 else 0.0
    
    print(f"\n{'='*70}")
    print("IN-SAMPLE vs OUT-OF-SAMPLE COMPARISON")
    print(f"{'='*70}")
    print(f"  IS Sharpe (2000-2018):  {is_sharpe:+.3f}")
    print(f"  OOS Sharpe (2019-2025): {metrics['sharpe']:+.3f}")
    print(f"  OOS/IS Ratio:           {oos_is_ratio:.1%}")
    
    # Diagnostic
    print(f"\n{'='*70}")
    print("DIAGNOSTIC")
    print(f"{'='*70}")
    
    if oos_is_ratio >= 0.60 and oos_is_ratio <= 1.20:
        print("✅ OOS/IS ratio in acceptable range (60-120%)")
        if metrics['sharpe'] >= 0.30:
            print("✅ OOS Sharpe >= 0.30 (good momentum performance)")
            verdict = "DEPLOY READY"
        elif metrics['sharpe'] >= 0.25:
            print("⚠️  OOS Sharpe 0.25-0.30 (marginal, proceed with caution)")
            verdict = "MARGINAL - DEPLOY WITH CAUTION"
        else:
            print("❌ OOS Sharpe < 0.25 (weak performance)")
            verdict = "DO NOT DEPLOY - WEAK PERFORMANCE"
    elif oos_is_ratio < 0.60:
        print(f"❌ OOS/IS ratio < 60% (forward bias concern)")
        print(f"   Parameters may be overfit to in-sample period")
        verdict = "DO NOT DEPLOY - POSSIBLE FORWARD BIAS"
    else:
        print(f"⚠️  OOS/IS ratio > 120% (unusually good, verify data)")
        print(f"   Could be lucky or data quality issue")
        verdict = "INVESTIGATE - TOO GOOD TO BE TRUE"
    
    print(f"\nVERDICT: {verdict}")
    
    # Save results
    oos_results = {
        'optimized_parameters': {k: v for k, v in best_params.items() if k != 'sharpe'},
        'is_metrics': {
            'sharpe': is_sharpe,
            'period': 'in-sample data used for optimization',
        },
        'oos_metrics': metrics,
        'comparison': {
            'is_sharpe': is_sharpe,
            'oos_sharpe': metrics['sharpe'],
            'oos_is_ratio': oos_is_ratio,
            'degradation': is_sharpe - metrics['sharpe'],
        },
        'verdict': verdict,
        'validation_date': pd.Timestamp.now().isoformat(),
        'oos_period': f"{df_oos['date'].min()} to {df_oos['date'].max()}",
        'critical_reminder': 'DO NOT re-optimize based on these results. Use OOS Sharpe for production expectations.',
    }
    
    results_path = output_dir / 'oos_validation_report.json'
    with open(results_path, 'w') as f:
        json.dump(oos_results, f, indent=2)
    print(f"\nResults saved: {results_path}")
    
    # Save daily series
    df_oos_with_signal = df_oos.copy()
    df_oos_with_signal['position'] = signal
    daily_path = output_dir / 'daily_series_oos.csv'
    df_oos_with_signal.to_csv(daily_path, index=False)
    print(f"Daily OOS series saved: {daily_path}")
    
    print(f"\n{'='*70}")
    print("âš ï¸  CRITICAL REMINDER")
    print(f"{'='*70}")
    print("1. These OOS results are FINAL - do not re-optimize!")
    print("2. Use OOS Sharpe (not IS Sharpe) for production expectations")
    print("3. If verdict is negative, consider:")
    print("   - Using TrendMedium V2 instead (0.505 Sharpe, working well)")
    print("   - Waiting for more data / different market regime")
    print("   - Simplifying the strategy further")
    print("4. If deploying, monitor live performance vs OOS expectations")
    print(f"{'='*70}\n")
    
    return oos_results


def main():
    # Paths
    data_path = Path('Data/copper/pricing/canonical/copper_lme_3mo.canonical.csv')
    output_dir = Path('outputs/Copper/TrendImpulse_v5/optimization')
    stage2_params_path = output_dir / 'stage2_best_params.json'
    
    # Check Stage 2 results exist
    if not stage2_params_path.exists():
        print(f"ERROR: Stage 2 results not found at {stage2_params_path}")
        print("Please run Stage 1 and Stage 2 optimization first!")
        return 1
    
    # Load Stage 2 best params
    print("Loading Stage 2 best parameters...")
    with open(stage2_params_path, 'r') as f:
        stage2_data = json.load(f)
    
    best_params = stage2_data['full_params']
    is_metrics = stage2_data['best_metrics']
    
    # Convert integer parameters from JSON (they load as floats)
    if 'momentum_window' in best_params:
        best_params['momentum_window'] = int(best_params['momentum_window'])
    if 'vol_window' in best_params:
        best_params['vol_window'] = int(best_params['vol_window'])
    if 'vol_percentile_window' in best_params:
        best_params['vol_percentile_window'] = int(best_params['vol_percentile_window'])
    if 'update_frequency' in best_params:
        best_params['update_frequency'] = int(best_params['update_frequency'])
    
    # Add IS sharpe for comparison
    best_params['sharpe'] = is_metrics['sharpe']
    
    print(f"Stage 1+2 IS Sharpe: {is_metrics['sharpe']:.3f}")
    print()
    
    # Load data
    print("Loading canonical data...")
    df = pd.read_csv(data_path, parse_dates=['date'])
    
    # Split out-of-sample
    OOS_START = '2019-01-01'
    df_oos = df[df['date'] >= OOS_START].copy()
    
    print(f"Out-of-Sample: {df_oos['date'].min()} to {df_oos['date'].max()} ({len(df_oos)} obs)")
    
    # CRITICAL: Confirm this is the first run
    oos_report_path = output_dir / 'oos_validation_report.json'
    if oos_report_path.exists():
        print(f"\n{'='*70}")
        print("⚠️  WARNING: OOS validation has already been run!")
        print(f"{'='*70}")
        print(f"Found existing report: {oos_report_path}")
        print()
        response = input("Running OOS validation multiple times creates forward bias.\nAre you SURE you want to re-run? (type 'YES' to confirm): ")
        if response != 'YES':
            print("Aborting. Use existing OOS results.")
            return 0
        print("\nProceeding with re-validation (NOT RECOMMENDED)...\n")
    
    # Run validation
    results = validate_oos(df_oos, best_params, output_dir)
    
    if results is None:
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())