#!/usr/bin/env python3
r"""
Macro Regime Classifier
=======================
Combine ChopCore and CrisisCore outputs into 3 macro states: NORMAL/CHOP/CRISIS

Macro States:
  - CRISIS: Credit stress periods (CrisisCore = CRISIS or PRE_CRISIS)
  - CHOP: Macro confusion periods (ChopCore = MILD_CHOP or HIGH_CHOP)
  - NORMAL: Business as usual (everything else)

Priority Hierarchy:
  1. CRISIS trumps CHOP (if both present, classify as CRISIS)
  2. CHOP trumps NORMAL
  3. Otherwise NORMAL

Author: Ex-Renaissance Quant + Kieran
Date: November 13, 2025
Location: C:\Code\Metals\tools\build_macro_regimes.py
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys

# ============================================================================
# CONFIGURATION
# ============================================================================

# Determine base directory
if hasattr(sys, 'frozen'):
    BASE_DIR = Path(sys.executable).parent.parent
else:
    BASE_DIR = Path(__file__).parent.parent

# Input paths
OUTPUT_DIR = BASE_DIR / 'outputs' / 'Copper'
CHOP_PATH = OUTPUT_DIR / 'ChopCore_v1' / 'chopcore_v1_regimes.csv'
CRISIS_PATH = OUTPUT_DIR / 'CrisisCore_v2' / 'crisiscore_v2_regimes.csv'
VOL_PATH = OUTPUT_DIR / 'VolRegime' / 'vol_regimes.csv'

# Output path
MACRO_OUTPUT_DIR = OUTPUT_DIR / 'MacroRegime'

# ============================================================================
# MACRO STATE CLASSIFICATION
# ============================================================================

def classify_macro_state(crisis_regime, chop_regime):
    """
    Classify macro state based on crisis and chop regimes.
    
    Priority hierarchy:
    1. CRISIS (if crisis_regime in [CRISIS, PRE_CRISIS])
    2. CHOP (if chop_regime in [MILD_CHOP, HIGH_CHOP])
    3. NORMAL (otherwise)
    
    Args:
        crisis_regime: String from CrisisCore
        chop_regime: String from ChopCore
        
    Returns:
        String: NORMAL, CHOP, or CRISIS
    """
    # Handle NaN
    if pd.isna(crisis_regime):
        crisis_regime = 'NORMAL'
    if pd.isna(chop_regime):
        chop_regime = 'NORMAL'
    
    # Priority 1: Crisis
    if crisis_regime in ['CRISIS', 'PRE_CRISIS']:
        return 'CRISIS'
    
    # Priority 2: Chop
    if chop_regime in ['MILD_CHOP', 'HIGH_CHOP']:
        return 'CHOP'
    
    # Default: Normal
    return 'NORMAL'

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n" + "="*80)
    print("MACRO REGIME CLASSIFIER")
    print("="*80 + "\n")
    
    # Load CrisisCore regimes
    print("Loading CrisisCore regimes...")
    if not CRISIS_PATH.exists():
        print(f"ERROR: CrisisCore file not found: {CRISIS_PATH}")
        print("\nPlease ensure CrisisCore regimes exist in:")
        print(f"  {CRISIS_PATH.parent}")
        return 1
    
    crisis_df = pd.read_csv(CRISIS_PATH)
    crisis_df['date'] = pd.to_datetime(crisis_df['date'])
    crisis_df = crisis_df[['date', 'regime']].rename(columns={'regime': 'crisis_regime'})
    print(f"  ✓ Loaded {len(crisis_df)} days of CrisisCore data")
    print(f"  Date range: {crisis_df['date'].min().date()} to {crisis_df['date'].max().date()}")
    
    # Show crisis distribution
    crisis_dist = crisis_df['crisis_regime'].value_counts()
    print(f"\n  Crisis regime distribution:")
    for regime, count in crisis_dist.items():
        pct = (count / len(crisis_df)) * 100
        print(f"    {regime:15s}: {count:5d} days ({pct:5.1f}%)")
    
    # Load ChopCore regimes
    print("\nLoading ChopCore regimes...")
    if not CHOP_PATH.exists():
        print(f"ERROR: ChopCore file not found: {CHOP_PATH}")
        print("\nPlease ensure ChopCore regimes exist in:")
        print(f"  {CHOP_PATH.parent}")
        return 1
    
    chop_df = pd.read_csv(CHOP_PATH)
    chop_df['date'] = pd.to_datetime(chop_df['date'])
    chop_df = chop_df[['date', 'regime']].rename(columns={'regime': 'chop_regime'})
    print(f"  ✓ Loaded {len(chop_df)} days of ChopCore data")
    print(f"  Date range: {chop_df['date'].min().date()} to {chop_df['date'].max().date()}")
    
    # Show chop distribution
    chop_dist = chop_df['chop_regime'].value_counts()
    print(f"\n  Chop regime distribution:")
    for regime, count in chop_dist.items():
        pct = (count / len(chop_df)) * 100
        print(f"    {regime:15s}: {count:5d} days ({pct:5.1f}%)")
    
    # Merge crisis and chop
    print("\nMerging CrisisCore and ChopCore...")
    macro_df = crisis_df.merge(chop_df, on='date', how='outer')
    macro_df = macro_df.sort_values('date').reset_index(drop=True)
    print(f"  ✓ Merged to {len(macro_df)} days")
    
    # Classify macro state
    print("\nClassifying macro states...")
    print("  Priority hierarchy:")
    print("    1. CRISIS (if CrisisCore = CRISIS or PRE_CRISIS)")
    print("    2. CHOP (if ChopCore = MILD_CHOP or HIGH_CHOP)")
    print("    3. NORMAL (otherwise)")
    
    macro_df['macro_state'] = macro_df.apply(
        lambda row: classify_macro_state(row['crisis_regime'], row['chop_regime']),
        axis=1
    )
    
    # Distribution
    macro_dist = macro_df['macro_state'].value_counts()
    total_days = len(macro_df)
    
    print("\n" + "-" * 80)
    print("MACRO STATE DISTRIBUTION")
    print("-" * 80)
    for state in ['NORMAL', 'CHOP', 'CRISIS']:
        if state in macro_dist.index:
            count = macro_dist[state]
            pct = (count / total_days) * 100
            print(f"{state:10s}: {count:5d} days ({pct:5.1f}%)")
    
    # Save macro classification
    print("\n" + "-" * 80)
    print("Saving macro classification...")
    
    output_dir = Path(MACRO_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_cols = ['date', 'crisis_regime', 'chop_regime', 'macro_state']
    output_df = macro_df[output_cols].copy()
    
    macro_path = output_dir / 'macro_regimes.csv'
    output_df.to_csv(macro_path, index=False)
    print(f"  ✓ Saved: {macro_path}")
    
    # Now combine with vol regimes for 9-state classification
    print("\nLoading volatility regimes...")
    if not VOL_PATH.exists():
        print(f"WARNING: Vol regimes file not found: {VOL_PATH}")
        print("Skipping 9-state classification.")
        print("Run build_vol_regimes.py first to generate vol_regimes.csv")
    else:
        vol_df = pd.read_csv(VOL_PATH)
        vol_df['date'] = pd.to_datetime(vol_df['date'])
        vol_df = vol_df[['date', 'vol_regime']].copy()
        print(f"  ✓ Loaded {len(vol_df)} days of vol regime data")
        
        # Merge vol + macro
        print("\nCombining Vol × Macro → 9-state classification...")
        combined_df = vol_df.merge(macro_df[['date', 'macro_state']], on='date', how='inner')
        
        # Create combined state
        combined_df['state'] = combined_df['vol_regime'] + '_' + combined_df['macro_state']
        
        print(f"  ✓ Created 9-state classification for {len(combined_df)} days")
        
        # Distribution
        state_dist = combined_df['state'].value_counts()
        total = len(combined_df)
        
        print("\n" + "-" * 80)
        print("9-STATE DISTRIBUTION (Vol × Macro)")
        print("-" * 80)
        for state in sorted(state_dist.index):
            count = state_dist[state]
            pct = (count / total) * 100
            print(f"{state:25s}: {count:5d} days ({pct:5.1f}%)")
        
        # Save 9-state classification
        nine_state_path = output_dir / 'regime_classification_9state.csv'
        combined_df.to_csv(nine_state_path, index=False)
        print(f"\n  ✓ Saved: {nine_state_path}")
    
    print("\n" + "="*80)
    print("✓ MACRO REGIME CLASSIFICATION COMPLETE")
    print("="*80)
    print(f"\nOutputs saved to: {output_dir}")
    print(f"  - macro_regimes.csv (3 macro states)")
    if VOL_PATH.exists():
        print(f"  - regime_classification_9state.csv (Vol × Macro 9 states)")
    print("="*80 + "\n")
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)