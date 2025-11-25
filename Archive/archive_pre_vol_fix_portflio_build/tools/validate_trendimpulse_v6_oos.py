# tools/validate_trendimpulse_v6_oos.py
"""
TrendImpulse V6 - Out-of-Sample Validation
RUN THIS ONCE AFTER OPTIMIZATION - NEVER ADJUST PARAMETERS AFTER

Takes optimized parameters from Stage 2 and tests on 2019-2025 data.
Reports honest results. No cherry-picking.

CRITICAL: This is run ONCE. Results reported honestly.
Never go back and adjust parameters based on OOS results.
"""

import argparse
import sys
from pathlib import Path
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


def calculate_detailed_metrics(positions: pd.Series, returns: pd.Series) -> dict:
    """Calculate comprehensive strategy metrics"""
    strat_returns = positions.shift(1) * returns
    
    valid = strat_returns.dropna()
    
    # Basic metrics
    sharpe = calculate_sharpe(strat_returns)
    annual_return = valid.mean() * 252 if len(valid) > 0 else 0.0
    annual_vol = valid.std() * np.sqrt(252) if len(valid) > 0 else 0.0
    
    # Drawdown
    cum_returns = (1 + valid).cumprod()
    running_max = cum_returns.expanding().max()
    drawdown = (cum_returns - running_max) / running_max
    max_drawdown = drawdown.min()
    
    # Activity
    activity_pct = (positions.abs() > 0.01).mean() * 100
    long_pct = (positions > 0.01).mean() * 100
    short_pct = (positions < -0.01).mean() * 100
    
    # Win rate
    wins = (valid > 0).sum()
    losses = (valid < 0).sum()
    win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.0
    
    return {
        'sharpe': sharpe,
        'annual_return': annual_return,
        'annual_vol': annual_vol,
        'max_drawdown': max_drawdown,
        'activity_pct': activity_pct,
        'long_pct': long_pct,
        'short_pct': short_pct,
        'win_rate': win_rate,
        'n_days': len(valid),
    }


def main():
    ap = argparse.ArgumentParser(
        description="TrendImpulse V6 - OOS Validation (Run Once)"
    )
    ap.add_argument("--optimized-params", required=True, help="Stage 2 best params JSON")
    ap.add_argument("--csv-close", required=True, help="Close prices canonical CSV")
    ap.add_argument("--csv-high", required=True, help="High prices canonical CSV")
    ap.add_argument("--csv-low", required=True, help="Low prices canonical CSV")
    ap.add_argument("--outdir", required=True, help="Output directory for results")
    args = ap.parse_args()

    print("=" * 80)
    print("TRENDIMPULSE V6 - OUT-OF-SAMPLE VALIDATION")
    print("⚠️  RUN ONCE - REPORT HONESTLY - NEVER ADJUST PARAMETERS AFTER")
    print("=" * 80)

    # ========== LOAD OPTIMIZED PARAMETERS ==========
    print("\n[1] Loading optimized parameters...")
    
    with open(args.optimized_params, 'r') as f:
        optimized = json.load(f)
    
    params = optimized['best_parameters']
    is_sharpe = optimized['is_performance']['sharpe']
    
    print(f"  Stage 2 Best IS Sharpe: {is_sharpe:.3f}")
    print(f"  Parameters:")
    for key, val in params.items():
        if key in ['momentum_window', 'entry_threshold', 'exit_threshold', 'adx_trending_threshold']:
            print(f"    {key}: {val}")
    
    # ========== LOAD DATA ==========
    print("\n[2] Loading OHLC data...")
    
    df_close = pd.read_csv(args.csv_close, parse_dates=['date'])
    df_high = pd.read_csv(args.csv_high, parse_dates=['date'])
    df_low = pd.read_csv(args.csv_low, parse_dates=['date'])
    
    df = df_close[['date', 'price']].copy()
    df = df.merge(df_high[['date', 'price']].rename(columns={'price': 'high'}), on='date', how='inner')
    df = df.merge(df_low[['date', 'price']].rename(columns={'price': 'low'}), on='date', how='inner')
    df['ret'] = df['price'].pct_change()
    
    print(f"  Total rows: {len(df)}")
    
    # ========== SPLIT IS/OOS ==========
    print("\n[3] Splitting data...")
    
    df['year'] = df['date'].dt.year
    is_cutoff = 2019
    
    df_is = df[df['year'] < is_cutoff].copy()
    df_oos = df[df['year'] >= is_cutoff].copy()
    
    print(f"  In-Sample:  {len(df_is)} rows ({df_is['year'].min()}-{df_is['year'].max()})")
    print(f"  Out-Sample: {len(df_oos)} rows ({df_oos['year'].min()}-{df_oos['year'].max()})")
    
    # ========== GENERATE SIGNALS ==========
    print("\n[4] Generating signals with optimized parameters...")
    
    print(f"  Generating IS signal (for comparison)...")
    signal_is = generate_trendimpulse_v6_signal(df_is, **params)
    
    print(f"  Generating OOS signal...")
    signal_oos = generate_trendimpulse_v6_signal(df_oos, **params)
    
    # ========== CALCULATE METRICS ==========
    print("\n[5] Calculating metrics...")
    
    metrics_is = calculate_detailed_metrics(signal_is, df_is['ret'])
    metrics_oos = calculate_detailed_metrics(signal_oos, df_oos['ret'])
    
    # ========== REPORT RESULTS ==========
    print("\n" + "=" * 80)
    print("VALIDATION RESULTS")
    print("=" * 80)
    
    print(f"\n  IN-SAMPLE (2000-2018):")
    print(f"    Sharpe:         {metrics_is['sharpe']:.3f}")
    print(f"    Annual Return:  {metrics_is['annual_return']*100:+.2f}%")
    print(f"    Annual Vol:     {metrics_is['annual_vol']*100:.2f}%")
    print(f"    Max Drawdown:   {metrics_is['max_drawdown']*100:.2f}%")
    print(f"    Activity:       {metrics_is['activity_pct']:.1f}%")
    print(f"    Win Rate:       {metrics_is['win_rate']*100:.1f}%")
    
    print(f"\n  OUT-OF-SAMPLE (2019-2025):")
    print(f"    Sharpe:         {metrics_oos['sharpe']:.3f}")
    print(f"    Annual Return:  {metrics_oos['annual_return']*100:+.2f}%")
    print(f"    Annual Vol:     {metrics_oos['annual_vol']*100:.2f}%")
    print(f"    Max Drawdown:   {metrics_oos['max_drawdown']*100:.2f}%")
    print(f"    Activity:       {metrics_oos['activity_pct']:.1f}%")
    print(f"    Win Rate:       {metrics_oos['win_rate']*100:.1f}%")
    
    # Degradation analysis
    degradation = metrics_is['sharpe'] - metrics_oos['sharpe']
    oos_pct = (metrics_oos['sharpe'] / metrics_is['sharpe'] * 100) if metrics_is['sharpe'] > 0 else 0
    
    print(f"\n  DEGRADATION ANALYSIS:")
    print(f"    Degradation:    {degradation:+.3f} Sharpe points")
    print(f"    OOS as % of IS: {oos_pct:.1f}%")
    
    # Verdict
    print(f"\n  VERDICT:")
    if oos_pct < 40:
        print(f"    ❌ SEVERE forward bias (OOS < 40% of IS)")
        print(f"       Parameters are overfit to historical data")
        print(f"       Consider simpler model or more data")
    elif oos_pct < 60:
        print(f"    ⚠️  MODERATE forward bias (OOS 40-60% of IS)")
        print(f"       Some overfitting present")
        print(f"       Use with caution")
    elif oos_pct < 120:
        print(f"    ✅ ACCEPTABLE degradation (OOS 60-120% of IS)")
        print(f"       Normal generalization, no obvious forward bias")
        print(f"       Parameters are reasonable")
    else:
        print(f"    ⚠️  OOS outperforms IS (OOS > 120% of IS)")
        print(f"       Either lucky or data issue")
        print(f"       Review carefully")
    
    # Expected performance
    print(f"\n  PRODUCTION EXPECTATIONS:")
    if metrics_oos['sharpe'] > 0.3:
        print(f"    Expected live Sharpe: {metrics_oos['sharpe']:.3f}")
        print(f"    Expected activity: {metrics_oos['activity_pct']:.1f}%")
        print(f"    Status: Acceptable for deployment")
    else:
        print(f"    Expected live Sharpe: {metrics_oos['sharpe']:.3f}")
        print(f"    Status: Below target (0.30+ Sharpe)")
        print(f"    Consider: Simpler model or more data")
    
    # ========== SAVE RESULTS ==========
    print(f"\n[6] Saving results...")
    
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    
    # Save validation report
    validation_report = {
        'validation_date': datetime.now().isoformat(),
        'parameters': params,
        'is_performance': {k: float(v) if isinstance(v, (int, float, np.number)) else v 
                          for k, v in metrics_is.items()},
        'oos_performance': {k: float(v) if isinstance(v, (int, float, np.number)) else v 
                           for k, v in metrics_oos.items()},
        'degradation': {
            'sharpe_degradation': float(degradation),
            'oos_as_pct_of_is': float(oos_pct),
        },
        'verdict': 'acceptable' if 60 <= oos_pct <= 120 else 
                  'overfit' if oos_pct < 60 else 'lucky',
        'recommended_for_production': bool(metrics_oos['sharpe'] > 0.3 and 60 <= oos_pct <= 120),
    }
    
    report_path = outdir / "oos_validation_report.json"
    with open(report_path, 'w') as f:
        json.dump(validation_report, f, indent=2)
    print(f"  Saved: {report_path}")
    
    # Save daily series for both periods
    df_is['signal'] = signal_is
    df_is['strat_ret'] = signal_is.shift(1) * df_is['ret']
    
    df_oos['signal'] = signal_oos
    df_oos['strat_ret'] = signal_oos.shift(1) * df_oos['ret']
    
    is_path = outdir / "daily_series_is.csv"
    oos_path = outdir / "daily_series_oos.csv"
    
    df_is.to_csv(is_path, index=False)
    df_oos.to_csv(oos_path, index=False)
    
    print(f"  Saved: {is_path}")
    print(f"  Saved: {oos_path}")
    
    # ========== FINAL SUMMARY ==========
    print(f"\n" + "=" * 80)
    print("OOS VALIDATION COMPLETE")
    print("=" * 80)
    
    print(f"\n  ⚠️  CRITICAL REMINDERS:")
    print(f"      1. This was run ONCE on unseen data")
    print(f"      2. Never adjust parameters based on these results")
    print(f"      3. These are honest expectations for live performance")
    print(f"      4. If deploying, use these OOS metrics for risk management")
    
    print(f"\n  Next Steps:")
    if validation_report['recommended_for_production']:
        print(f"    ✅ Strategy ready for production deployment")
        print(f"    1. Update config YAML with optimized parameters")
        print(f"    2. Run full 4-layer build (vol targeting + costs)")
        print(f"    3. Integrate into portfolio with TrendMedium + MomentumCore")
    else:
        print(f"    ⚠️  Strategy needs improvement before deployment")
        print(f"    1. Consider simpler model (TrendImpulse V5?)")
        print(f"    2. Or wait for more data")
        print(f"    3. Or use existing strategies (TrendMedium V2 works great)")
    
    print(f"\n" + "=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())