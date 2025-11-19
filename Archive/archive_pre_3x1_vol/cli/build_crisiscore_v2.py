#!/usr/bin/env python3
# src/cli/build_crisiscore_v2.py
r"""
Build script for CrisisCore v2

Multi-dimensional crisis detection using:
- HY credit spreads (60% weight) - PRIMARY signal
- VIX (25% weight) - CONFIRMATION signal  
- Velocity (15% weight) - ACCELERATION detector

Four-tier regime classification:
- NORMAL: Full exposure
- STRESS: Mild concern
- PRE_CRISIS: Elevated risk
- CRISIS: High risk

Used as DIRECTIONAL amplifier with TightnessCore, not blanket reducer.

Usage:
    python build_crisiscore_v2.py ^
        --csv-hy C:\Code\Metals\Data\Macro\pricing\canonical\us_hy_index.canonical.csv ^
        --csv-vix C:\Code\Metals\Data\Macro\pricing\canonical\vix_iv.canonical.csv ^
        --config C:\Code\Metals\Config\Copper\crisiscore_v2.yaml ^
        --outdir C:\Code\Metals\outputs\Crisis\CrisisCore_v2
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

# Add paths for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src" / "overlays"))

from crisiscore_v2 import run_crisiscore_detection


def load_canonical_csv(path: str, required_cols: list) -> pd.DataFrame:
    """Load and validate canonical CSV"""
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])

    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}' in {path}")

    return df.sort_values("date").reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="Build CrisisCore v2")
    parser.add_argument("--csv-hy", required=True, help="HY spread canonical CSV")
    parser.add_argument("--csv-vix", required=True, help="VIX canonical CSV")
    parser.add_argument("--config", required=True, help="YAML config file")
    parser.add_argument("--outdir", required=True, help="Output directory")

    args = parser.parse_args()

    print("=" * 80)
    print("CrisisCore v2 - Build Process")
    print("=" * 80)
    print("\nMulti-Dimensional Crisis Detection:")
    print("  • HY credit spreads (60% weight) - PRIMARY signal")
    print("  • VIX volatility (25% weight) - CONFIRMATION")
    print("  • Velocity (15% weight) - ACCELERATION detector")
    print("\nUsage: Directional amplifier with TightnessCore")

    # ========== 1. LOAD CONFIG ==========
    print("\n[1/5] Loading configuration...")
    with open(args.config, "r") as f:
        config = yaml.safe_load(f)

    print(f"  ✓ Lookback: {config['parameters']['lookback']} days")
    print(f"  ✓ HY crisis threshold: {config['credit_stress']['crisis']} bps")
    print(f"  ✓ VIX crisis threshold: {config['vix_stress']['crisis']}")
    print(f"  ✓ Composite weights: {config['composite_weights']['credit_stress']:.0%} credit, "
          f"{config['composite_weights']['vix_stress']:.0%} VIX, "
          f"{config['composite_weights']['velocity']:.0%} velocity")

    # ========== 2. LOAD HY SPREADS ==========
    print("\n[2/5] Loading HY spreads...")
    df_hy = load_canonical_csv(args.csv_hy, ["date", "price"])
    
    # Convert to basis points (assuming price is in decimal form like 0.05 = 500 bps)
    # Adjust this if your data format is different
    hy_spread = df_hy.set_index("date")["price"] * 100
    
    print(f"  ✓ Loaded {len(hy_spread)} observations")
    print(f"  ✓ Date range: {hy_spread.index[0].date()} to {hy_spread.index[-1].date()}")
    print(f"  ✓ Range: [{hy_spread.min():.0f}, {hy_spread.max():.0f}] bps")
    print(f"  ✓ Mean: {hy_spread.mean():.0f} bps")

    # ========== 3. LOAD VIX ==========
    print("\n[3/5] Loading VIX...")
    df_vix = load_canonical_csv(args.csv_vix, ["date"])
    
    # Determine which column has VIX data (could be 'price', 'iv', or 'vix')
    vix_col = None
    for col in ["iv", "vix", "price"]:
        if col in df_vix.columns:
            vix_col = col
            break
    
    if vix_col is None:
        raise ValueError(f"Could not find VIX column in {args.csv_vix}. Available columns: {df_vix.columns.tolist()}")
    
    vix_series = df_vix.set_index("date")[vix_col]
    
    print(f"  ✓ Loaded {len(vix_series)} observations")
    print(f"  ✓ Date range: {vix_series.index[0].date()} to {vix_series.index[-1].date()}")
    print(f"  ✓ Range: [{vix_series.min():.1f}, {vix_series.max():.1f}]")
    print(f"  ✓ Mean: {vix_series.mean():.1f}")

    # ========== 4. ALIGN DATA ==========
    print("\n[4/5] Aligning data and running detection...")
    
    # Combine and align on common dates
    data_combined = pd.DataFrame({
        'hy_spread': hy_spread,
        'vix': vix_series
    })
    data_clean = data_combined.dropna()
    
    print(f"  ✓ Original HY: {len(hy_spread)} days")
    print(f"  ✓ Original VIX: {len(vix_series)} days")
    print(f"  ✓ Aligned: {len(data_clean)} days")
    print(f"  ✓ Date range: {data_clean.index[0].date()} to {data_clean.index[-1].date()}")

    # Prepare data dict for detection
    data_dict = {
        'hy_spread': data_clean['hy_spread'],
        'vix': data_clean['vix']
    }

    # Run detection
    results = run_crisiscore_detection(data_dict, config)
    
    print(f"  ✓ Processed {len(results['regimes'])} days")

    # ========== 5. PRINT DISTRIBUTION ==========
    print("\n" + "=" * 80)
    print("REGIME DISTRIBUTION")
    print("=" * 80)

    regime_counts = results['regimes']['regime'].value_counts()
    total = len(results['regimes'])

    for regime in ['NORMAL', 'STRESS', 'PRE_CRISIS', 'CRISIS']:
        count = regime_counts.get(regime, 0)
        pct = count / total * 100
        expected_pct = config['expected_distribution'].get(regime.lower(), 0) * 100
        indicator = "✓" if abs(pct - expected_pct) < 10 else "⚠"
        print(f"{regime:<15} {count:>6} days ({pct:>5.1f}%) [Expected: {expected_pct:.0f}%] {indicator}")

    # ========== 6. VALIDATE HISTORICAL CRISES ==========
    print("\n" + "=" * 80)
    print("HISTORICAL CRISIS VALIDATION")
    print("=" * 80)

    validation_periods = [
        ('2008-09-01', '2008-11-30', 'GFC 2008', 'CRISIS'),
        ('2020-03-01', '2020-03-31', 'COVID 2020', 'CRISIS'),
        ('2011-08-01', '2011-08-31', 'Europe 2011', 'PRE_CRISIS'),
        ('2002-07-01', '2002-10-31', 'Enron 2002', 'CRISIS'),
        ('2018-12-01', '2018-12-31', 'Dec 2018', 'STRESS'),
        ('2022-02-01', '2022-03-31', 'Ukraine 2022', 'STRESS')
    ]

    print(f"\n{'Period':<20} {'Expected':<15} {'Detected':<15} {'% Match':>8} {'Avg HY':>8} {'Avg VIX':>8}")
    print("-" * 85)

    for start, end, label, expected in validation_periods:
        mask = (results['regimes'].index >= start) & (results['regimes'].index <= end)
        period_data = results['regimes'][mask]
        
        if len(period_data) == 0:
            print(f"{label:<20} {expected:<15} {'NO DATA':<15} {'N/A':>8} {'N/A':>8} {'N/A':>8}")
            continue
        
        detected = period_data['regime'].mode()[0] if len(period_data['regime'].mode()) > 0 else 'Mixed'
        pct_match = (period_data['regime'] == expected).sum() / len(period_data) * 100
        avg_hy = period_data['hy_spread'].mean()
        avg_vix = period_data['vix'].mean()
        
        indicator = "✅" if detected == expected or pct_match > 30 else "⚠️" if pct_match > 10 else "❌"
        
        print(f"{label:<20} {expected:<15} {detected:<15} {pct_match:>7.0f}% {avg_hy:>8.0f} {avg_vix:>8.1f} {indicator}")

    # ========== 7. SCORE STATISTICS ==========
    print("\n" + "=" * 80)
    print("CRISIS SCORE STATISTICS")
    print("=" * 80)

    print(f"\nComposite Crisis Score:")
    print(f"  Mean:   {results['scores']['composite_crisis'].mean():.3f}")
    print(f"  Median: {results['scores']['composite_crisis'].median():.3f}")
    print(f"  Std:    {results['scores']['composite_crisis'].std():.3f}")
    print(f"  Max:    {results['scores']['composite_crisis'].max():.3f}")

    print(f"\nComponent Scores (mean):")
    print(f"  Credit Stress: {results['scores']['credit_stress'].mean():.3f}")
    print(f"  VIX Stress:    {results['scores']['vix_stress'].mean():.3f}")
    print(f"  Velocity:      {results['scores']['velocity'].mean():.3f}")

    # ========== 8. WRITE OUTPUTS ==========
    print("\n[5/5] Writing outputs...")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Scores CSV
    scores_csv = outdir / "crisiscore_v2_scores.csv"
    results['scores'].index.name = 'date'
    results['scores'].reset_index().to_csv(scores_csv, index=False)
    print(f"  ✓ {scores_csv}")

    # Regimes CSV
    regimes_csv = outdir / "crisiscore_v2_regimes.csv"
    results['regimes'].index.name = 'date'
    results['regimes'].reset_index().to_csv(regimes_csv, index=False)
    print(f"  ✓ {regimes_csv}")

    # Summary metrics
    metrics = {
        'total_days': int(total),
        'regime_distribution': {k: int(v) for k, v in regime_counts.items()},
        'composite_score_mean': float(results['scores']['composite_crisis'].mean()),
        'composite_score_std': float(results['scores']['composite_crisis'].std()),
        'date_range': {
            'start': str(results['regimes'].index[0].date()),
            'end': str(results['regimes'].index[-1].date())
        }
    }
    
    metrics_json = outdir / "summary_metrics.json"
    with open(metrics_json, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"  ✓ {metrics_json}")

    # ========== SUMMARY ==========
    print("\n" + "=" * 80)
    print("✅ CRISISCORE V2 BUILD COMPLETE")
    print("=" * 80)

    print("\nKey Features:")
    print("  • Multi-dimensional: HY spreads (60%) + VIX (25%) + Velocity (15%)")
    print("  • More stable: Credit stress less volatile than VIX alone")
    print("  • Earlier warning: Velocity detects acceleration")
    print("  • Four regimes: Normal/Stress/Pre-Crisis/Crisis")
    print("  • Data-driven: Thresholds from 25 years of history")

    print("\n⚠️  Usage Note:")
    print("  CrisisCore is a DIRECTIONAL amplifier, not a blanket reducer.")
    print("  Use with TightnessCore in crisis_directional_overlay.py:")
    print("    • Crisis + Tight markets → Amplify bullish")
    print("    • Crisis + Loose markets → Amplify bearish")
    print("    • ChopCore overrides when fundamentals are neutral (20-80)")

    print(f"\nOutputs written to: {outdir}")
    print()


if __name__ == "__main__":
    main()