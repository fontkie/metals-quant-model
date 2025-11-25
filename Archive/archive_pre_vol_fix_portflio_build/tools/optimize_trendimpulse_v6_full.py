# tools/optimize_trendimpulse_v6_full.py
"""
TrendImpulse V6 - Complete Optimization (Both Stages)
NO FORWARD BIAS | RUNS BOTH STAGES AUTOMATICALLY

Stage 1: Core Parameters (192 combinations)
  - momentum_window, entry/exit thresholds, ADX threshold
  - Expected IS Sharpe: 0.55-0.65

Stage 2: Regime Scaling (243 combinations)
  - Uses best Stage 1 params
  - Optimizes vol regime thresholds and scales
  - Expected improvement: +0.05 to +0.10

Total: 435 combinations tested on IN-SAMPLE only (2000-2018)
Expected runtime: 25-45 minutes
"""

import argparse
import sys
from pathlib import Path
from itertools import product
import pandas as pd
import numpy as np
import json
from datetime import datetime

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))
from src.signals.trendimpulse_v6 import generate_trendimpulse_v6_signal


def calculate_sharpe(returns: pd.Series) -> float:
    """Calculate annualized Sharpe ratio"""
    valid = returns.dropna()
    if len(valid) < 20:
        return 0.0
    if valid.std() == 0:
        return 0.0
    return (valid.mean() / valid.std()) * np.sqrt(252)


def calculate_metrics(positions: pd.Series, returns: pd.Series) -> dict:
    """Calculate strategy metrics"""
    strat_returns = positions.shift(1) * returns
    
    sharpe = calculate_sharpe(strat_returns)
    
    valid = strat_returns.dropna()
    annual_return = valid.mean() * 252 if len(valid) > 0 else 0.0
    annual_vol = valid.std() * np.sqrt(252) if len(valid) > 0 else 0.0
    
    activity_pct = (positions.abs() > 0.01).mean() * 100
    long_pct = (positions > 0.01).mean() * 100
    short_pct = (positions < -0.01).mean() * 100
    
    return {
        'sharpe': sharpe,
        'annual_return': annual_return,
        'annual_vol': annual_vol,
        'activity_pct': activity_pct,
        'long_pct': long_pct,
        'short_pct': short_pct,
    }


def run_stage1(df_is: pd.DataFrame) -> tuple:
    """Run Stage 1 optimization - Core parameters"""
    
    print("\n" + "=" * 80)
    print("STAGE 1: CORE PARAMETERS OPTIMIZATION")
    print("=" * 80)
    
    # Define grid
    param_grid = {
        'momentum_window': [15, 20, 25],
        'entry_threshold': [0.008, 0.010, 0.012, 0.015],
        'exit_threshold': [0.002, 0.003, 0.004, 0.005],
        'adx_trending_threshold': [18, 20, 22, 25],
    }
    
    fixed_params = {
        'adx_window': 14,
        'weekly_vol_updates': True,
        'update_frequency': 5,
        'use_regime_scaling': False,  # Stage 1: NO regime scaling
        'vol_window': 63,
        'vol_percentile_window': 252,
    }
    
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())
    combinations = list(product(*param_values))
    
    print(f"\n  Parameters: {param_names}")
    print(f"  Combinations: {len(combinations)}")
    print(f"  Estimated time: {len(combinations) * 5 / 60:.0f} minutes")
    print(f"\n  Starting at: {datetime.now().strftime('%H:%M:%S')}")
    
    # Run optimization
    results = []
    best_sharpe = -999
    best_params = None
    
    for i, combo in enumerate(combinations, 1):
        params = dict(zip(param_names, combo))
        params.update(fixed_params)
        
        try:
            signal = generate_trendimpulse_v6_signal(df_is, **params)
            metrics = calculate_metrics(signal, df_is['ret'])
            
            result = {**params, **metrics}
            results.append(result)
            
            if metrics['sharpe'] > best_sharpe:
                best_sharpe = metrics['sharpe']
                best_params = params.copy()
            
            if i % 20 == 0 or i == len(combinations):
                print(f"    [{i:3d}/{len(combinations)}] Best: {best_sharpe:.3f} Sharpe")
        
        except Exception as e:
            print(f"    [ERROR] Combo {i}: {e}")
            continue
    
    print(f"\n  Completed at: {datetime.now().strftime('%H:%M:%S')}")
    
    # Analyze results
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('sharpe', ascending=False)
    best = results_df.iloc[0]
    
    print(f"\n  STAGE 1 RESULTS:")
    print(f"    Best IS Sharpe:  {best['sharpe']:.3f}")
    print(f"    Activity:        {best['activity_pct']:.1f}%")
    print(f"    Best Parameters:")
    print(f"      momentum_window:        {best['momentum_window']:.0f}")
    print(f"      entry_threshold:        {best['entry_threshold']:.4f}")
    print(f"      exit_threshold:         {best['exit_threshold']:.4f}")
    print(f"      adx_trending_threshold: {best['adx_trending_threshold']:.0f}")
    
    return results_df, best_params, best_sharpe


def run_stage2(df_is: pd.DataFrame, stage1_params: dict, stage1_sharpe: float) -> tuple:
    """Run Stage 2 optimization - Regime scaling"""
    
    print("\n" + "=" * 80)
    print("STAGE 2: REGIME SCALING OPTIMIZATION")
    print("=" * 80)
    
    print(f"\n  Using Stage 1 best params (Sharpe: {stage1_sharpe:.3f})")
    
    # Define grid
    param_grid = {
        'low_vol_threshold': [0.35, 0.40, 0.45],
        'medium_vol_threshold': [0.70, 0.75, 0.80],
        'low_vol_scale': [1.3, 1.5, 1.7],
        'medium_vol_scale': [0.6, 0.8, 1.0],
        'high_vol_scale': [0.5, 0.7, 0.9],
    }
    
    # Fixed params from Stage 1
    fixed_params = {
        **stage1_params,
        'use_regime_scaling': True,  # Stage 2: YES regime scaling
    }
    
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())
    combinations = list(product(*param_values))
    
    print(f"\n  Parameters: {param_names}")
    print(f"  Combinations: {len(combinations)}")
    print(f"  Estimated time: {len(combinations) * 6 / 60:.0f} minutes")
    print(f"\n  Starting at: {datetime.now().strftime('%H:%M:%S')}")
    
    # Run optimization
    results = []
    best_sharpe = -999
    best_params = None
    
    for i, combo in enumerate(combinations, 1):
        params = dict(zip(param_names, combo))
        params.update(fixed_params)
        
        try:
            signal = generate_trendimpulse_v6_signal(df_is, **params)
            metrics = calculate_metrics(signal, df_is['ret'])
            
            result = {**params, **metrics}
            results.append(result)
            
            if metrics['sharpe'] > best_sharpe:
                best_sharpe = metrics['sharpe']
                best_params = params.copy()
            
            if i % 25 == 0 or i == len(combinations):
                improvement = best_sharpe - stage1_sharpe
                print(f"    [{i:3d}/{len(combinations)}] Best: {best_sharpe:.3f} " +
                      f"(+{improvement:+.3f} vs Stage 1)")
        
        except Exception as e:
            print(f"    [ERROR] Combo {i}: {e}")
            continue
    
    print(f"\n  Completed at: {datetime.now().strftime('%H:%M:%S')}")
    
    # Analyze results
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('sharpe', ascending=False)
    best = results_df.iloc[0]
    improvement = best['sharpe'] - stage1_sharpe
    
    print(f"\n  STAGE 2 RESULTS:")
    print(f"    Best IS Sharpe:    {best['sharpe']:.3f}")
    print(f"    Improvement:       +{improvement:.3f} vs Stage 1")
    print(f"    Activity:          {best['activity_pct']:.1f}%")
    print(f"    Regime Parameters:")
    print(f"      low_vol_threshold:    {best['low_vol_threshold']:.2f}")
    print(f"      medium_vol_threshold: {best['medium_vol_threshold']:.2f}")
    print(f"      low_vol_scale:        {best['low_vol_scale']:.1f}")
    print(f"      medium_vol_scale:     {best['medium_vol_scale']:.1f}")
    print(f"      high_vol_scale:       {best['high_vol_scale']:.1f}")
    
    return results_df, best_params, best['sharpe'], improvement


def main():
    ap = argparse.ArgumentParser(
        description="TrendImpulse V6 - Complete Optimization (Both Stages)"
    )
    ap.add_argument("--csv-close", required=True, help="Close prices canonical CSV")
    ap.add_argument("--csv-high", required=True, help="High prices canonical CSV")
    ap.add_argument("--csv-low", required=True, help="Low prices canonical CSV")
    ap.add_argument("--outdir", required=True, help="Output directory for results")
    args = ap.parse_args()

    print("=" * 80)
    print("TRENDIMPULSE V6 - COMPLETE OPTIMIZATION")
    print("Stage 1: Core Parameters + Stage 2: Regime Scaling")
    print("=" * 80)
    print("\n  Total combinations: 192 + 243 = 435")
    print("  Expected runtime: 25-45 minutes")
    print("  In-Sample: 2000-2018 ONLY")
    print("  Out-Sample: 2019-2025 (not touched)")

    # ========== LOAD DATA ==========
    print("\n[1] Loading OHLC data...")
    
    df_close = pd.read_csv(args.csv_close, parse_dates=['date'])
    df_high = pd.read_csv(args.csv_high, parse_dates=['date'])
    df_low = pd.read_csv(args.csv_low, parse_dates=['date'])
    
    df = df_close[['date', 'price']].copy()
    df = df.merge(df_high[['date', 'price']].rename(columns={'price': 'high'}), on='date', how='inner')
    df = df.merge(df_low[['date', 'price']].rename(columns={'price': 'low'}), on='date', how='inner')
    df['ret'] = df['price'].pct_change()
    
    print(f"  Total rows: {len(df)}")
    print(f"  Date range: {df['date'].min()} to {df['date'].max()}")
    
    # ========== SPLIT IS/OOS ==========
    print("\n[2] Splitting In-Sample / Out-of-Sample...")
    
    df['year'] = df['date'].dt.year
    is_cutoff = 2019
    
    df_is = df[df['year'] < is_cutoff].copy()
    df_oos = df[df['year'] >= is_cutoff].copy()
    
    print(f"  In-Sample:  {len(df_is)} rows ({df_is['year'].min()}-{df_is['year'].max()})")
    print(f"  Out-Sample: {len(df_oos)} rows ({df_oos['year'].min()}-{df_oos['year'].max()})")
    
    # ========== RUN STAGE 1 ==========
    print("\n[3] Running Stage 1...")
    
    stage1_results, stage1_best_params, stage1_sharpe = run_stage1(df_is)
    
    # ========== RUN STAGE 2 ==========
    print("\n[4] Running Stage 2...")
    
    stage2_results, final_params, final_sharpe, improvement = run_stage2(
        df_is, stage1_best_params, stage1_sharpe
    )
    
    # ========== SAVE RESULTS ==========
    print("\n[5] Saving results...")
    
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    
    # Stage 1 results
    stage1_path = outdir / "stage1_full_results.csv"
    stage1_results.to_csv(stage1_path, index=False)
    print(f"  Saved: {stage1_path}")
    
    # Stage 2 results
    stage2_path = outdir / "stage2_full_results.csv"
    stage2_results.to_csv(stage2_path, index=False)
    print(f"  Saved: {stage2_path}")
    
    # Best parameters (final)
    best_params_dict = {
        'optimization_date': datetime.now().isoformat(),
        'is_period': f"{df_is['year'].min()}-{df_is['year'].max()}",
        'is_rows': len(df_is),
        'total_combinations_tested': len(stage1_results) + len(stage2_results),
        'stage1_sharpe': float(stage1_sharpe),
        'stage2_sharpe': float(final_sharpe),
        'improvement': float(improvement),
        'best_parameters': {
            # Core parameters from Stage 1
            'momentum_window': int(final_params['momentum_window']),
            'entry_threshold': float(final_params['entry_threshold']),
            'exit_threshold': float(final_params['exit_threshold']),
            'adx_trending_threshold': float(final_params['adx_trending_threshold']),
            # Regime scaling from Stage 2
            'low_vol_threshold': float(final_params['low_vol_threshold']),
            'medium_vol_threshold': float(final_params['medium_vol_threshold']),
            'low_vol_scale': float(final_params['low_vol_scale']),
            'medium_vol_scale': float(final_params['medium_vol_scale']),
            'high_vol_scale': float(final_params['high_vol_scale']),
            # Fixed parameters
            'adx_window': 14,
            'weekly_vol_updates': True,
            'update_frequency': 5,
            'use_regime_scaling': True,
            'vol_window': 63,
            'vol_percentile_window': 252,
        },
        'is_performance': {
            'sharpe': float(final_sharpe),
            'annual_return': float(stage2_results.iloc[0]['annual_return']),
            'annual_vol': float(stage2_results.iloc[0]['annual_vol']),
            'activity_pct': float(stage2_results.iloc[0]['activity_pct']),
        },
        'next_step': "Run OOS validation ONCE - never adjust parameters after",
    }
    
    best_path = outdir / "optimized_params.json"
    with open(best_path, 'w') as f:
        json.dump(best_params_dict, f, indent=2)
    print(f"  Saved: {best_path}")
    
    # ========== FINAL SUMMARY ==========
    print("\n" + "=" * 80)
    print("OPTIMIZATION COMPLETE")
    print("=" * 80)
    
    print(f"\n  Results:")
    print(f"    ✅ Tested 435 combinations (192 + 243)")
    print(f"    ✅ Stage 1 Best: {stage1_sharpe:.3f} Sharpe")
    print(f"    ✅ Stage 2 Best: {final_sharpe:.3f} Sharpe")
    print(f"    ✅ Improvement: +{improvement:.3f}")
    print(f"    ✅ No forward bias (OOS never touched)")
    
    if improvement < 0.02:
        print(f"\n  ⚠️  NOTE: Small improvement (<0.02)")
        print(f"      Regime scaling may not be worth the complexity")
    elif improvement > 0.10:
        print(f"\n  ✅ EXCELLENT: Large improvement (>0.10)")
        print(f"      Regime scaling adds significant value")
    
    print(f"\n  Next Steps:")
    print(f"    1. Review results in: {outdir}")
    print(f"    2. Run OOS validation (ONCE ONLY):")
    print(f"       python tools\\validate_trendimpulse_v6_oos.py \\")
    print(f"         --optimized-params {best_path} \\")
    print(f"         --csv-close <path> \\")
    print(f"         --csv-high <path> \\")
    print(f"         --csv-low <path> \\")
    print(f"         --outdir {outdir}")
    print(f"\n    3. NEVER adjust parameters based on OOS results!")
    
    print("\n" + "=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())