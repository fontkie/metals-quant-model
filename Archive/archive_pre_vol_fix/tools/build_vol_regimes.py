#!/usr/bin/env python3
r"""
Volatility Regime Classifier
=============================
Calculate realized volatility and classify into LOW/MEDIUM/HIGH regimes.

Vol Regimes (Percentile-based):
  - LOW: Vol < 33rd percentile (calm markets)
  - MEDIUM: Vol 33-67th percentile (normal volatility)
  - HIGH: Vol > 67th percentile (stressed markets)

Method:
  - 63-day realized volatility (3 months)
  - Percentile rank over rolling 252-day window (1 year)
  - Annualized to % terms

Author: Ex-Renaissance Quant
Date: November 12, 2025
Location: C:\Code\Metals\tools\build_vol_regimes.py
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys

# ============================================================================
# CONFIGURATION
# ============================================================================

# Volatility parameters
VOL_WINDOW = 63              # Days for realized vol calculation (3 months)
PERCENTILE_WINDOW = 252      # Days for percentile ranking (1 year)
LOW_VOL_PERCENTILE = 0.33    # Bottom third = LOW
HIGH_VOL_PERCENTILE = 0.67   # Top third = HIGH

# Determine base directory
if hasattr(sys, 'frozen'):
    BASE_DIR = Path(sys.executable).parent.parent
else:
    BASE_DIR = Path(__file__).parent.parent

# Input path
DATA_DIR = BASE_DIR / 'Data' / 'copper' / 'pricing' / 'canonical'
CLOSE_PATH = DATA_DIR / 'copper_lme_3mo.canonical.csv'

# Output path
OUTPUT_DIR = BASE_DIR / 'outputs' / 'Copper' / 'VolRegime'

# ============================================================================
# VOLATILITY CALCULATION
# ============================================================================

def calculate_realized_vol(prices, window=63, annualization_factor=252):
    """
    Calculate realized volatility from price series.
    
    Args:
        prices: Series of closing prices
        window: Rolling window for vol calculation (default 63 = 3 months)
        annualization_factor: Days per year (default 252)
        
    Returns:
        Series: Annualized realized volatility
    """
    # Calculate returns
    returns = prices.pct_change()
    
    # Rolling standard deviation
    vol = returns.rolling(window=window).std()
    
    # Annualize
    vol_annualized = vol * np.sqrt(annualization_factor)
    
    return vol_annualized

def calculate_vol_percentile(vol_series, window=252):
    """
    Calculate percentile rank of volatility over rolling window.
    
    Args:
        vol_series: Series of volatility values
        window: Rolling window for percentile calculation
        
    Returns:
        Series: Percentile rank (0-1)
    """
    # Rolling percentile rank
    percentile = vol_series.rolling(window=window).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1],
        raw=False
    )
    
    return percentile

def classify_vol_regime(vol_percentile, low_threshold=0.33, high_threshold=0.67):
    """
    Classify volatility regime based on percentile.
    
    Args:
        vol_percentile: Series of percentile ranks (0-1)
        low_threshold: Threshold for LOW regime
        high_threshold: Threshold for HIGH regime
        
    Returns:
        Series: Vol regime classifications
    """
    vol_regime = pd.Series('MEDIUM', index=vol_percentile.index)
    
    vol_regime[vol_percentile < low_threshold] = 'LOW'
    vol_regime[vol_percentile > high_threshold] = 'HIGH'
    
    return vol_regime

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n" + "="*80)
    print("VOLATILITY REGIME CLASSIFIER")
    print("="*80 + "\n")
    
    # Verify input file exists
    print("Checking input file...")
    if not CLOSE_PATH.exists():
        print(f"ERROR: Price file not found: {CLOSE_PATH}")
        print("\nPlease ensure data file exists in:")
        print(f"  {DATA_DIR}")
        return 1
    print(f"  ✓ Found: {CLOSE_PATH.name}\n")
    
    # Load price data
    print("Loading copper prices...")
    df = pd.read_csv(CLOSE_PATH)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    
    print(f"Loaded {len(df)} days of price data")
    print(f"Date range: {df['date'].min().date()} to {df['date'].max().date()}\n")
    
    # Calculate realized volatility
    print(f"Calculating realized volatility (window={VOL_WINDOW} days)...")
    df['realized_vol'] = calculate_realized_vol(
        df['price'],
        window=VOL_WINDOW
    )
    
    # Calculate percentile rank
    print(f"Calculating percentile ranks (window={PERCENTILE_WINDOW} days)...")
    df['vol_percentile'] = calculate_vol_percentile(
        df['realized_vol'],
        window=PERCENTILE_WINDOW
    )
    
    # Classify regime
    print("Classifying volatility regimes...")
    print(f"  LOW regime: Vol percentile < {LOW_VOL_PERCENTILE:.0%}")
    print(f"  MEDIUM regime: Vol percentile {LOW_VOL_PERCENTILE:.0%}-{HIGH_VOL_PERCENTILE:.0%}")
    print(f"  HIGH regime: Vol percentile > {HIGH_VOL_PERCENTILE:.0%}\n")
    
    df['vol_regime'] = classify_vol_regime(
        df['vol_percentile'],
        low_threshold=LOW_VOL_PERCENTILE,
        high_threshold=HIGH_VOL_PERCENTILE
    )
    
    # Distribution (after warmup period)
    warmup_days = max(VOL_WINDOW, PERCENTILE_WINDOW)
    df_valid = df.iloc[warmup_days:].copy()
    
    distribution = df_valid['vol_regime'].value_counts()
    total_days = len(df_valid)
    
    print("-" * 80)
    print("VOLATILITY REGIME DISTRIBUTION")
    print("-" * 80)
    for regime in ['LOW', 'MEDIUM', 'HIGH']:
        if regime in distribution.index:
            count = distribution[regime]
            pct = (count / total_days) * 100
            print(f"{regime:10s}: {count:5d} days ({pct:5.1f}%)")
    
    # Summary statistics
    print("\n" + "-" * 80)
    print("REALIZED VOLATILITY STATISTICS")
    print("-" * 80)
    vol_clean = df['realized_vol'].dropna()
    print(f"Mean Vol:   {vol_clean.mean()*100:.2f}%")
    print(f"Median Vol: {vol_clean.median()*100:.2f}%")
    print(f"Min Vol:    {vol_clean.min()*100:.2f}%")
    print(f"Max Vol:    {vol_clean.max()*100:.2f}%")
    print(f"Std Vol:    {vol_clean.std()*100:.2f}%")
    
    # Show regime thresholds in vol terms
    print("\n" + "-" * 80)
    print("REGIME THRESHOLDS (Approximate)")
    print("-" * 80)
    low_vol_threshold = df_valid['realized_vol'].quantile(LOW_VOL_PERCENTILE)
    high_vol_threshold = df_valid['realized_vol'].quantile(HIGH_VOL_PERCENTILE)
    print(f"LOW regime:    Vol < {low_vol_threshold*100:.2f}%")
    print(f"MEDIUM regime: Vol {low_vol_threshold*100:.2f}%-{high_vol_threshold*100:.2f}%")
    print(f"HIGH regime:   Vol > {high_vol_threshold*100:.2f}%")
    
    # Save output
    print("\n" + "-" * 80)
    print("Saving results...")
    
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save full results
    output_cols = ['date', 'price', 'realized_vol', 'vol_percentile', 'vol_regime']
    output_df = df[output_cols].copy()
    
    output_path = output_dir / 'vol_regimes.csv'
    output_df.to_csv(output_path, index=False)
    print(f"Saved: {output_path}")
    
    print("\n" + "="*80)
    print("✓ VOLATILITY CLASSIFICATION COMPLETE")
    print("="*80 + "\n")
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)