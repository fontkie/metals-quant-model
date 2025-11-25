#!/usr/bin/env python3
# src/cli/build_tightness_index_v3.py
"""
Build script for Tightness Index V3

Multi-layer physical market tightness framework:
- Layer 1A: LME Micro Tightness (exchange-specific)
- Layer 1B: Global Macro Tightness (total visible stocks)
- Layer 1C: Divergence Detection (relocation vs genuine tightness)

Expected Output:
- Tightness score (0-100) with confidence level
- Diagnostics: days consumption, weeks coverage, divergence patterns

Usage:
    python build_tightness_index_v3.py \
        --csv-lme-stocks Data/copper/pricing/canonical/copper_lme_onwarrant_stocks.canonical.csv \
        --csv-comex-stocks Data/copper/pricing/canonical/copper_comex_stocks.canonical.csv \
        --csv-shfe-stocks Data/copper/pricing/canonical/copper_shfe_onwarrant_stocks.canonical.csv \
        --csv-fut-3mo Data/copper/pricing/canonical/copper_lme_3mo_fut.canonical.csv \
        --csv-fut-12mo Data/copper/pricing/canonical/copper_lme_12mo_fut.canonical.csv \
        --config Config/Copper/tightness_index_v3.yaml \
        --outdir outputs/Copper/TightnessIndex_v3
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml
import numpy as np

# Add paths for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src" / "overlays"))

from tightness_index_v3 import run_tightness_index, load_config


def load_canonical_csv(path: str, required_cols: list) -> pd.DataFrame:
    """Load and validate canonical CSV"""
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}' in {path}")
    
    return df.sort_values("date").reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="Build Tightness Index v3")
    parser.add_argument("--csv-lme-stocks", required=True, help="LME on-warrant stocks canonical CSV")
    parser.add_argument("--csv-comex-stocks", required=True, help="COMEX stocks canonical CSV")
    parser.add_argument("--csv-shfe-stocks", required=True, help="SHFE on-warrant stocks canonical CSV")
    parser.add_argument("--csv-fut-3mo", required=True, help="LME 3mo futures canonical CSV")
    parser.add_argument("--csv-fut-12mo", required=True, help="LME 12mo futures canonical CSV")
    parser.add_argument("--config", required=True, help="YAML config file")
    parser.add_argument("--outdir", required=True, help="Output directory")
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("TIGHTNESS INDEX V3 - BUILD PROCESS")
    print("=" * 80)
    print()
    print("Three-Layer Physical Market Tightness Framework:")
    print("  • Layer 1A: LME Micro Tightness (exchange-specific signals)")
    print("  • Layer 1B: Global Macro Tightness (total visible stocks)")
    print("  • Layer 1C: Divergence Detection (relocation filter)")
    print()
    
    # ========== 1. LOAD CONFIG ==========
    print("[1/5] Loading configuration...")
    config_path = project_root / args.config
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    annual_demand = config['demand']['annual_demand_kt']
    lme_weight = config['integration']['lme_weight']
    global_weight = config['integration']['global_weight']
    
    print(f"  ✓ Config loaded from: {config_path.name}")
    print(f"  ✓ Annual demand: {annual_demand:,} kt")
    print(f"  ✓ LME weight: {lme_weight:.0%}")
    print(f"  ✓ Global weight: {global_weight:.0%}")
    print()
    
    # ========== 2. LOAD STOCK DATA ==========
    print("[2/5] Loading copper market data...")
    
    # LME on-warrant stocks
    df_lme = load_canonical_csv(str(project_root / args.csv_lme_stocks), ["date", "stocks"])
    lme_stocks = df_lme.set_index('date')['stocks']
    print(f"  ✓ LME on-warrant: {len(lme_stocks):,} days ({lme_stocks.index[0].date()} to {lme_stocks.index[-1].date()})")
    
    # COMEX stocks
    df_comex = load_canonical_csv(str(project_root / args.csv_comex_stocks), ["date", "stocks"])
    comex_stocks = df_comex.set_index('date')['stocks']
    print(f"  ✓ COMEX stocks: {len(comex_stocks):,} days ({comex_stocks.index[0].date()} to {comex_stocks.index[-1].date()})")
    
    # SHFE on-warrant stocks
    df_shfe = load_canonical_csv(str(project_root / args.csv_shfe_stocks), ["date", "stocks"])
    shfe_stocks = df_shfe.set_index('date')['stocks']
    print(f"  ✓ SHFE on-warrant: {len(shfe_stocks):,} days ({shfe_stocks.index[0].date()} to {shfe_stocks.index[-1].date()})")
    print()
    
    # ========== 3. CALCULATE FORWARD CURVE SPREAD ==========
    print("[3/5] Calculating forward curve spread...")
    
    df_3mo = load_canonical_csv(str(project_root / args.csv_fut_3mo), ["date", "price"])
    fut_3mo = df_3mo.set_index('date')['price']
    
    df_12mo = load_canonical_csv(str(project_root / args.csv_fut_12mo), ["date", "price"])
    fut_12mo = df_12mo.set_index('date')['price']
    
    # Calculate spread: (3mo - 12mo) / 12mo * 100
    # Positive = backwardation (tight), Negative = contango (loose)
    spread_3mo_12mo = ((fut_3mo - fut_12mo) / fut_12mo * 100).fillna(0)
    
    mean_backwardation = config['layer_1a_lme_micro']['spread_thresholds']['mean_backwardation']
    print(f"  ✓ 3mo-12mo spread calculated")
    print(f"  ✓ Historical mean: {spread_3mo_12mo.mean():.2f}% (config expects: {mean_backwardation:.2f}%)")
    print()
    
    # ========== 4. RUN TIGHTNESS INDEX ==========
    print("[4/5] Running tightness index calculation...")
    print("  This may take a minute...")
    
    # Prepare data dictionary
    data = {
        'lme_onwarrant': lme_stocks,
        'comex_stocks': comex_stocks,
        'shfe_stocks': shfe_stocks,
        'spread_3mo_12mo': spread_3mo_12mo
    }
    
    # Run calculation
    scores, diagnostics = run_tightness_index(data, config)
    print("  ✓ Calculation complete")
    print()
    
    # ========== 5. DISPLAY STATISTICS ==========
    print("=" * 80)
    print("TIGHTNESS INDEX STATISTICS")
    print("=" * 80)
    print()
    
    print("Final Tightness Score:")
    print(f"  Mean: {scores['final_tightness_score'].mean():.1f}/100")
    print(f"  Median: {scores['final_tightness_score'].median():.1f}/100")
    print(f"  Std: {scores['final_tightness_score'].std():.1f}")
    print(f"  Range: [{scores['final_tightness_score'].min():.1f}, {scores['final_tightness_score'].max():.1f}]")
    print()
    
    print("Component Scores (mean):")
    print(f"  LME Micro: {scores['lme_micro_score'].mean():.1f}/100")
    print(f"  Global Macro: {scores['global_macro_score'].mean():.1f}/100")
    print(f"  Divergence Adjustment: {scores['divergence_adjustment'].mean():.2f}×")
    print()
    
    # Divergence pattern distribution
    print("Divergence Pattern Distribution:")
    pattern_counts = diagnostics['pattern'].value_counts()
    for pattern, count in pattern_counts.items():
        pct = count / len(diagnostics) * 100
        print(f"  {pattern:30s}: {count:5d} days ({pct:5.1f}%)")
    print()
    
    # Recent period analysis
    print("=" * 80)
    print("RECENT PERIOD ANALYSIS (Last 12 months)")
    print("=" * 80)
    print()
    
    recent = scores[scores.index >= (scores.index[-1] - pd.Timedelta(days=365))]
    recent_diag = diagnostics[diagnostics.index >= (diagnostics.index[-1] - pd.Timedelta(days=365))]
    
    print(f"Recent Tightness Score: {recent['final_tightness_score'].mean():.1f}/100")
    print(f"Current (latest): {recent['final_tightness_score'].iloc[-1]:.1f}/100")
    print()
    
    print("Recent Divergence Patterns:")
    recent_patterns = recent_diag['pattern'].value_counts()
    for pattern, count in recent_patterns.items():
        pct = count / len(recent_diag) * 100
        print(f"  {pattern:30s}: {count:3d} days ({pct:5.1f}%)")
    print()
    
    # Key historical episodes
    print("=" * 80)
    print("KEY HISTORICAL EPISODES")
    print("=" * 80)
    print()
    
    episodes = [
        ('2018-07-01', '2018-08-31', 'Jul-Aug 2018 (Escondida Risk)'),
        ('2021-09-01', '2021-12-31', '2021 Q3-Q4 (Inventory Squeeze)'),
        ('2025-01-01', '2025-10-31', '2025 YTD (Current Period)'),
    ]
    
    for start, end, label in episodes:
        ep_scores = scores[(scores.index >= start) & (scores.index <= end)]
        ep_diag = diagnostics[(diagnostics.index >= start) & (diagnostics.index <= end)]
        
        if len(ep_scores) == 0:
            continue
        
        print(f"{label}:")
        print(f"  Avg Tightness: {ep_scores['final_tightness_score'].mean():.1f}/100")
        print(f"  Avg LME Micro: {ep_scores['lme_micro_score'].mean():.1f}/100")
        print(f"  Avg Global Macro: {ep_scores['global_macro_score'].mean():.1f}/100")
        
        # Dominant pattern
        if len(ep_diag) > 0:
            dominant_pattern = ep_diag['pattern'].mode()[0] if len(ep_diag['pattern'].mode()) > 0 else 'UNKNOWN'
            print(f"  Dominant Pattern: {dominant_pattern}")
        print()
    
    # ========== 6. SAVE OUTPUTS ==========
    print("=" * 80)
    print("[5/5] Saving results...")
    print("=" * 80)
    print()
    
    output_dir = project_root / args.outdir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save scores
    scores_file = output_dir / 'tightness_index_v3_scores.csv'
    scores.index.name = 'date'
    scores.reset_index().to_csv(scores_file, index=False)
    print(f"  ✓ Saved scores: {scores_file}")
    
    # Save diagnostics
    diagnostics_file = output_dir / 'tightness_index_v3_diagnostics.csv'
    diagnostics.index.name = 'date'
    diagnostics.reset_index().to_csv(diagnostics_file, index=False)
    print(f"  ✓ Saved diagnostics: {diagnostics_file}")
    
    # Save summary metrics
    summary = {
        'tightness_score': {
            'mean': float(scores['final_tightness_score'].mean()),
            'median': float(scores['final_tightness_score'].median()),
            'std': float(scores['final_tightness_score'].std()),
            'min': float(scores['final_tightness_score'].min()),
            'max': float(scores['final_tightness_score'].max()),
            'current': float(scores['final_tightness_score'].iloc[-1])
        },
        'component_scores': {
            'lme_micro_mean': float(scores['lme_micro_score'].mean()),
            'global_macro_mean': float(scores['global_macro_score'].mean()),
            'divergence_adjustment_mean': float(scores['divergence_adjustment'].mean())
        },
        'recent_12m': {
            'mean': float(recent['final_tightness_score'].mean()),
            'current': float(recent['final_tightness_score'].iloc[-1])
        },
        'config': {
            'annual_demand_kt': annual_demand,
            'lme_weight': lme_weight,
            'global_weight': global_weight
        }
    }
    
    summary_file = output_dir / 'summary_metrics.json'
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"  ✓ Saved summary: {summary_file}")
    
    print()
    print("=" * 80)
    print("✓ TIGHTNESS INDEX V3 BUILD COMPLETE")
    print("=" * 80)
    print()
    
    print("Key Features:")
    print("  • Multi-layer: LME micro + Global macro + Divergence detection")
    print("  • Relocation filter: Distinguishes genuine tightness from reshuffling")
    print("  • Global coverage: LME + COMEX + SHFE total visible stocks")
    print("  • Confidence scoring: High when aligned, low when divergent")
    print()
    
    print(f"Outputs saved to: {output_dir}")
    print("  1. tightness_index_v3_scores.csv - Daily scores and components")
    print("  2. tightness_index_v3_diagnostics.csv - Confidence levels and patterns")
    print("  3. summary_metrics.json - Performance statistics")
    print()
    
    print("Next Steps:")
    print("  1. Review scores and patterns in output CSVs")
    print("  2. Integrate with crisis directional framework")
    print("  3. Backtest combined system")


if __name__ == "__main__":
    main()