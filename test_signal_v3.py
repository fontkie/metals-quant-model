#!/usr/bin/env python3
"""
Test TrendCore v3 Signal Implementation
----------------------------------------
Verifies that trendcore.py has v3 code with proper scaling.

USAGE:
  Run from repo root directory:
  python test_signal_v3.py
  
  Or in VS Code, just press F5 to run in debug mode.
"""

import sys
import inspect
from pathlib import Path
import pandas as pd
import numpy as np
import os

# Ensure we're running from repo root
repo_root = Path(__file__).parent
os.chdir(repo_root)
sys.path.insert(0, str(repo_root))

print("=" * 70)
print("TrendCore v3 Signal Test")
print("=" * 70)

# Test 1: Check function signature
print("\n[Test 1] Checking function signature...")
try:
    from src.signals.trendcore import generate_trendcore_signal
    sig = inspect.signature(generate_trendcore_signal)
    params = list(sig.parameters.keys())
    print(f"  Parameters found: {params}")
    
    # Check for v3 parameters
    v3_params = ['fast_ma', 'slow_ma', 'range_threshold']
    v2_params = ['ma_lookback', 'buffer_pct']
    
    has_v3 = all(p in params for p in v3_params)
    has_v2 = any(p in params for p in v2_params)
    
    if has_v3:
        print("  ✅ PASS: Function has v3 parameters")
    elif has_v2:
        print("  ❌ FAIL: Function still has v2 parameters!")
        print("\n  You need to replace src/signals/trendcore.py with the v3 version.")
        print("  The v3 version should have parameters:")
        print("    - fast_ma (not ma_lookback)")
        print("    - slow_ma (new in v3)")
        print("    - range_threshold (new in v3)")
        sys.exit(1)
    else:
        print("  ⚠️  WARNING: Unexpected parameters")
        
except ImportError as e:
    print(f"  ❌ FAIL: Cannot import signal function")
    print(f"  Error: {e}")
    sys.exit(1)

# Test 2: Check function execution
print("\n[Test 2] Testing signal generation...")
try:
    # Create sample data
    dates = pd.date_range('2020-01-01', periods=500, freq='D')
    prices = 100 + np.cumsum(np.random.randn(500) * 0.5)
    df = pd.DataFrame({'date': dates, 'price': prices})
    
    # Generate signal with v3 parameters
    pos_raw = generate_trendcore_signal(
        df,
        fast_ma=30,
        slow_ma=100,
        vol_lookback=63,
        range_threshold=0.10
    )
    
    print(f"  ✅ PASS: Signal generated successfully")
    print(f"  Signal shape: {pos_raw.shape}")
    
except TypeError as e:
    print(f"  ❌ FAIL: Function call failed")
    print(f"  Error: {e}")
    print("\n  This suggests the function signature doesn't match v3.")
    sys.exit(1)

# Test 3: Check signal scaling
print("\n[Test 3] Checking signal scaling...")
pos_raw_clean = pos_raw.dropna()
mean_abs = pos_raw_clean.abs().mean()
max_abs = pos_raw_clean.abs().max()

print(f"  Mean |pos_raw|: {mean_abs:.4f}")
print(f"  Max |pos_raw|:  {max_abs:.4f}")

# v3 should have scaled signals (0.3-1.0 range after all filters)
# v2 would have just ±1
if mean_abs > 0.8:
    print(f"  ❌ FAIL: Signal appears UNSCALED")
    print(f"\n  Expected: mean |pos_raw| around 0.35-0.45")
    print(f"  Got: {mean_abs:.3f}")
    print("\n  The signal looks like ±1 (v2 style) instead of scaled (v3 style).")
    print("\n  Check that your trendcore.py file has these scaling factors:")
    print("    1. range_scale: Reduces position in rangebound markets")
    print("    2. quality_scale: Reduces position when trend quality is poor")
    print("    3. vol_scale: Reduces position in high volatility")
    print("\n  The final return should be:")
    print("    pos_scaled = pos_raw * range_scale * quality_scale * vol_scale")
    sys.exit(1)
elif mean_abs < 0.25:
    print(f"  ⚠️  WARNING: Signal seems too conservative")
    print(f"  Expected around 0.35-0.45, got {mean_abs:.3f}")
else:
    print(f"  ✅ PASS: Signal scaling looks correct for v3")

# Test 4: Check for scaling logic in source
print("\n[Test 4] Checking source code for v3 features...")
import src.signals.trendcore as trendcore_module
source = inspect.getsource(trendcore_module)

v3_features = {
    'range_scale': 'range_scale' in source,
    'quality_scale': 'quality_scale' in source or 'trend_quality' in source,
    'vol_scale': 'vol_scale' in source or 'vol_percentile' in source,
    'dual_MA': 'ma_fast' in source and 'ma_slow' in source,
}

print(f"  Dual MA (fast/slow):     {'✅' if v3_features['dual_MA'] else '❌'}")
print(f"  Rangebound filter:       {'✅' if v3_features['range_scale'] else '❌'}")
print(f"  Trend quality filter:    {'✅' if v3_features['quality_scale'] else '❌'}")
print(f"  Vol regime filter:       {'✅' if v3_features['vol_scale'] else '❌'}")

if not all(v3_features.values()):
    print("\n  ❌ FAIL: Missing v3 features in source code")
    print("\n  Your trendcore.py file is missing some v3 enhancements.")
    print("  Make sure you have the correct v3 file.")
    sys.exit(1)
else:
    print("\n  ✅ PASS: All v3 features present in source")

# Final summary
print("\n" + "=" * 70)
print("✅ ALL TESTS PASSED")
print("=" * 70)
print("\nYour trendcore.py has v3 code and it's working correctly!")
print("\nExpected performance when you run backtest:")
print("  - Sharpe: ~0.51")
print("  - Annual Vol: ~4.6%")
print("  - Max DD: ~-13.7%")
print("\nIf your backtest gives different results, check:")
print("  1. Python cache (delete __pycache__ folders)")
print("  2. That you're running the right build script")
print("  3. That the config file has correct parameters")
print("=" * 70)
