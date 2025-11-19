#!/usr/bin/env python3
"""
VS Code Environment Diagnostics
--------------------------------
Run this to check if your environment is set up correctly.

USAGE: python diagnose.py
"""

import sys
import os
from pathlib import Path

print("=" * 70)
print("VS Code Environment Diagnostics")
print("=" * 70)

# 1. Check working directory
cwd = os.getcwd()
print(f"\n1. Working Directory:")
print(f"   Current: {cwd}")
print(f"   Expected: Should end with 'Metals' (or your repo name)")
is_repo_root = Path('src').exists() and Path('Config').exists()
print(f"   Status: {'✅ Looks correct' if is_repo_root else '❌ Not in repo root!'}")

# 2. Check Python executable
print(f"\n2. Python Executable:")
print(f"   Path: {sys.executable}")
in_venv = '.venv' in sys.executable or 'venv' in sys.executable
print(f"   Status: {'✅ Using venv' if in_venv else '⚠️  Not using venv (might be OK)'}")

# 3. Check Python version
print(f"\n3. Python Version:")
print(f"   Version: {sys.version.split()[0]}")
print(f"   Status: {'✅ 3.8+' if sys.version_info >= (3, 8) else '❌ Need 3.8+'}")

# 4. Check if required files exist
print(f"\n4. File Check:")
files_to_check = [
    ("src/signals/trendcore.py", "Signal file"),
    ("src/core/contract.py", "Contract file"),
    ("src/cli/build_trendcore_v3.py", "Build script"),
    ("test_signal_v3.py", "Test script"),
    ("Config/Copper/trendcore.yaml", "Config file"),
]
all_exist = True
for file_path, description in files_to_check:
    exists = Path(file_path).exists()
    all_exist = all_exist and exists
    status = "✅" if exists else "❌"
    print(f"   {status} {description}: {file_path}")

# 5. Check file timestamp
trendcore_path = Path("src/signals/trendcore.py")
if trendcore_path.exists():
    import time
    mtime = trendcore_path.stat().st_mtime
    mtime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
    print(f"\n5. Signal File Timestamp:")
    print(f"   Last modified: {mtime_str}")
    print(f"   (If old, you may not have replaced the file)")

# 6. Try importing trendcore
print(f"\n6. Import Check:")
try:
    # Force fresh import
    if 'src.signals.trendcore' in sys.modules:
        del sys.modules['src.signals.trendcore']
    
    from src.signals.trendcore import generate_trendcore_signal
    import inspect
    
    # Get module location
    import src.signals.trendcore as trendcore_module
    module_path = Path(trendcore_module.__file__).resolve()
    print(f"   ✅ Successfully imported trendcore")
    print(f"   Location: {module_path}")
    
    # Check signature
    sig = inspect.signature(generate_trendcore_signal)
    params = list(sig.parameters.keys())
    print(f"   Parameters: {params}")
    
    # Determine version
    has_v3_params = all(p in params for p in ['fast_ma', 'slow_ma', 'range_threshold'])
    has_v2_params = any(p in params for p in ['ma_lookback', 'buffer_pct'])
    
    if has_v3_params:
        print(f"   ✅ Has v3 parameters (fast_ma, slow_ma, range_threshold)")
    elif has_v2_params:
        print(f"   ❌ Has v2 parameters (ma_lookback, buffer_pct)")
        print(f"   → You need to replace src/signals/trendcore.py with v3 version!")
    else:
        print(f"   ⚠️  Unknown version (unexpected parameters)")
    
    # Check for v3 features in source
    source = inspect.getsource(trendcore_module)
    features = {
        'range_scale': 'range_scale' in source,
        'quality_scale': 'quality_scale' in source or 'trend_quality' in source,
        'vol_scale': 'vol_scale' in source or 'vol_percentile' in source,
        'dual_MA': 'ma_fast' in source and 'ma_slow' in source,
    }
    
    print(f"\n7. v3 Features Check:")
    print(f"   Dual MA (fast/slow):  {'✅' if features['dual_MA'] else '❌'}")
    print(f"   Rangebound filter:    {'✅' if features['range_scale'] else '❌'}")
    print(f"   Trend quality filter: {'✅' if features['quality_scale'] else '❌'}")
    print(f"   Vol regime filter:    {'✅' if features['vol_scale'] else '❌'}")
    
    all_features = all(features.values())
    
except ImportError as e:
    print(f"   ❌ Cannot import trendcore")
    print(f"   Error: {e}")
    print(f"   → Check that you're in repo root directory")
    all_features = False
except Exception as e:
    print(f"   ❌ Error checking import: {e}")
    all_features = False

# 8. Check for __pycache__
print(f"\n8. Cache Folders:")
try:
    pycache_dirs = list(Path('.').rglob('__pycache__'))
    if pycache_dirs:
        print(f"   Found {len(pycache_dirs)} cache folder(s)")
        for d in pycache_dirs[:5]:  # Show first 5
            print(f"   - {d}")
        if len(pycache_dirs) > 5:
            print(f"   ... and {len(pycache_dirs) - 5} more")
        print(f"   ⚠️  Consider deleting cache if having import issues")
    else:
        print(f"   ✅ No cache folders found (clean)")
except Exception as e:
    print(f"   ⚠️  Could not check for cache: {e}")

# 9. Check required packages
print(f"\n9. Required Packages:")
required_packages = ['pandas', 'numpy', 'yaml']
all_packages_ok = True
for pkg in required_packages:
    try:
        if pkg == 'yaml':
            import yaml as imported_pkg
        else:
            imported_pkg = __import__(pkg)
        version = getattr(imported_pkg, '__version__', 'unknown')
        print(f"   ✅ {pkg}: {version}")
    except ImportError:
        print(f"   ❌ {pkg}: NOT INSTALLED")
        all_packages_ok = False

# 10. Overall status
print("\n" + "=" * 70)
print("OVERALL STATUS")
print("=" * 70)

issues = []
if not is_repo_root:
    issues.append("Not in repo root directory")
if not all_exist:
    issues.append("Some required files missing")
if not all_packages_ok:
    issues.append("Some required packages missing")
    
# Check if using v3
try:
    from src.signals.trendcore import generate_trendcore_signal
    import inspect
    sig = inspect.signature(generate_trendcore_signal)
    params = list(sig.parameters.keys())
    if 'ma_lookback' in params:
        issues.append("Still using v2 signal (need to replace file)")
    elif 'fast_ma' not in params:
        issues.append("Signal file has unexpected structure")
except:
    issues.append("Cannot import signal file")

if not issues:
    print("✅ Everything looks good!")
    print("\nYou should be able to run:")
    print("  python test_signal_v3.py")
    print("  python src\\cli\\build_trendcore_v3.py --csv ... --config ... --outdir ...")
else:
    print("❌ Issues found:")
    for issue in issues:
        print(f"  - {issue}")
    print("\nRecommended actions:")
    if not is_repo_root:
        print("  1. Navigate to repo root directory")
    if "v2 signal" in str(issues):
        print("  2. Replace src/signals/trendcore.py with trendcore_v3_CORRECT.py")
        print("  3. Delete all __pycache__ folders")
    if not all_packages_ok:
        print("  4. Install missing packages: pip install pandas numpy pyyaml")

print("=" * 70)
