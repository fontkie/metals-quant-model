#!/usr/bin/env python3
"""
Extract Vol Regimes from Adaptive Portfolio Output
===================================================

Extracts vol regime classification from adaptive portfolio regime_log.csv

Input: regime_log.csv (from adaptive portfolio)
Output: vol_regimes.csv (for 9-state classification)

Location: Tools\extract_vol_regimes.py
Usage: Called by Scripts\run_extract_vol.bat

Author: Ex-Renaissance Quant
Date: November 12, 2025
"""

import pandas as pd
import sys
from pathlib import Path


def extract_vol_regimes(regime_log_file, output_file):
    """Extract vol regimes from adaptive portfolio regime log."""
    
    print("="*80)
    print("EXTRACTING VOL REGIMES FROM ADAPTIVE PORTFOLIO")
    print("="*80)
    
    print(f"\n1. Loading {regime_log_file}...")
    
    # Read with error handling for malformed lines
    df = pd.read_csv(regime_log_file, on_bad_lines='skip')
    print(f"   ✓ Read {len(df):,} rows")
    
    # Remove duplicate header rows
    df = df[df['date'] != 'date']
    
    # Convert date
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    
    print(f"   ✓ After cleaning: {len(df):,} valid dates")
    
    # Extract vol regime from composite regime column
    print("\n2. Extracting vol regime...")
    df['vol_regime'] = df['regime'].str.split('_').str[0].str.upper()
    
    # Filter to only valid vol regimes
    valid_regimes = ['LOW', 'MEDIUM', 'HIGH']
    df = df[df['vol_regime'].isin(valid_regimes)]
    
    print(f"   ✓ Extracted {len(df):,} valid vol regime classifications")
    
    # Statistics
    print("\n3. Vol Regime Distribution:")
    vol_dist = df['vol_regime'].value_counts().sort_index()
    total = len(df)
    for regime, count in vol_dist.items():
        pct = (count / total) * 100
        print(f"   {regime:10s}: {count:5,d} days ({pct:5.1f}%)")
    
    # Save
    print(f"\n4. Saving to {output_file}...")
    output = df[['date', 'vol_regime']].copy()
    output.to_csv(output_file, index=False)
    print("   ✓ Saved")
    
    print(f"\nDate range: {output['date'].min().date()} to {output['date'].max().date()}")
    
    print("\n" + "="*80)
    print("✓ VOL REGIME EXTRACTION COMPLETE")
    print("="*80)


def main():
    """Main execution."""
    if len(sys.argv) != 3:
        print("Usage: python extract_vol_regimes.py <regime_log.csv> <output.csv>")
        print("\nExample:")
        print("  python extract_vol_regimes.py regime_log.csv vol_regimes.csv")
        sys.exit(1)
    
    regime_log_file = sys.argv[1]
    output_file = sys.argv[2]
    
    # Validate input exists
    if not Path(regime_log_file).exists():
        print(f"ERROR: File not found: {regime_log_file}")
        sys.exit(1)
    
    # Extract
    extract_vol_regimes(regime_log_file, output_file)


if __name__ == '__main__':
    main()