r"""
Build Copper Demand Overlay
Applies demand regime scaling to baseline portfolio.

This script:
1. Loads baseline portfolio (e.g., 33/33/33 blended sleeves)
2. Loads Copper demand proxy data
3. Applies regime-based position scaling
4. Outputs enhanced portfolio with overlay metrics
5. Outputs standalone demand signals for monitoring

Output Structure:
  C:\Code\Metals\outputs\Copper\Portfolio\copper_demand\
    └── lag_X\  (X = 0, 1, or 2)
        ├── daily_series_china_demand_Xmo_YYYYMMDD_HHMMSS.csv
        ├── copper_demand_signals_Xmo_YYYYMMDD_HHMMSS.csv
        ├── summary_metrics_Xmo_YYYYMMDD_HHMMSS.json
        └── summary_Xmo_YYYYMMDD_HHMMSS.txt

Author: Kieran
Date: November 20, 2025
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import yaml

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from overlays.copper_demand import (
    load_demand_data,
    apply_overlay,
    format_metrics_summary
)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Build Copper Demand Overlay',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
Examples:
  # Basic usage (uses lag from config)
  python src\cli\build_copper_demand.py \
      --baseline C:\Code\Metals\outputs\Copper\Portfolio\BaselineEqualWeight\latest\daily_series.csv \
      --config Config\copper\copper_demand.yaml

  # Override lag setting (test 1-month lag)
  python src\cli\build_copper_demand.py \
      --baseline C:\Code\Metals\outputs\Copper\Portfolio\BaselineEqualWeight\latest\daily_series.csv \
      --config Config\copper\copper_demand.yaml \
      --lag 1

  # Specify custom output directory
  python src\cli\build_copper_demand.py \
      --baseline C:\Code\Metals\outputs\Copper\Portfolio\BaselineEqualWeight\latest\daily_series.csv \
      --config Config\copper\copper_demand.yaml \
      --outdir outputs\Copper\Portfolio\copper_demand

Output Location:
  Files go to: C:\Code\Metals\outputs\Copper\Portfolio\copper_demand\lag_X\
  where X is the lag in months (0, 1, or 2)
        """
    )
    
    parser.add_argument(
        '--baseline',
        required=True,
        help='Path to baseline portfolio CSV'
    )
    
    parser.add_argument(
        '--config',
        required=True,
        help='Path to YAML config file'
    )
    
    parser.add_argument(
        '--outdir',
        default='outputs/Copper/Portfolio/copper_demand',
        help='Output directory (default: outputs/Copper/Portfolio/copper_demand)'
    )
    
    parser.add_argument(
        '--lag',
        type=int,
        default=None,
        help='Override publication lag (months). Default: use config value'
    )
    
    parser.add_argument(
        '--scale',
        type=float,
        default=None,
        help='Override scale factor. Default: use config value'
    )
    
    parser.add_argument(
        '--method',
        type=str,
        default=None,
        choices=['yoy', 'qoq'],
        help='Override momentum method (yoy or qoq). Default: use config value'
    )
    
    return parser.parse_args()


def load_config(config_path: str) -> dict:
    """
    Load and validate YAML configuration.
    
    Args:
        config_path: Path to YAML config file
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If config doesn't exist
        ValueError: If config is invalid
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_file, 'r') as f:
        cfg = yaml.safe_load(f)
    
    # Validate required sections
    required_sections = ['overlay', 'data']
    for section in required_sections:
        if section not in cfg:
            raise ValueError(f"Config missing required section: {section}")
    
    return cfg


def load_baseline_portfolio(baseline_path: str) -> pd.DataFrame:
    """
    Load baseline portfolio CSV.
    
    Args:
        baseline_path: Path to baseline portfolio CSV
        
    Returns:
        DataFrame with baseline portfolio data
        
    Raises:
        FileNotFoundError: If baseline doesn't exist
        ValueError: If baseline missing required columns
    """
    baseline_file = Path(baseline_path)
    
    if not baseline_file.exists():
        raise FileNotFoundError(f"Baseline portfolio not found: {baseline_path}")
    
    baseline = pd.read_csv(baseline_file)
    baseline['date'] = pd.to_datetime(baseline['date'])
    
    # Check for required columns - adapt to BaselineEqualWeight format
    required_cols = ['date', 'price', 'ret', 'portfolio_pos', 'pnl_gross']
    missing_cols = [col for col in required_cols if col not in baseline.columns]
    
    if missing_cols:
        raise ValueError(
            f"Baseline portfolio missing required columns: {missing_cols}\n"
            f"Available columns: {baseline.columns.tolist()}"
        )
    
    return baseline


def main():
    """Main build function."""
    args = parse_args()
    
    print("="*80)
    print("COPPER DEMAND OVERLAY - BUILD")
    print("="*80)
    print(f"\nBaseline:  {args.baseline}")
    print(f"Config:    {args.config}")
    print(f"Output:    {args.outdir}")
    
    # Load configuration
    print("\n[1/5] Loading configuration...")
    try:
        cfg = load_config(args.config)
        print(f"✓ Config loaded: {cfg['overlay']['name']}")
    except Exception as e:
        print(f"✗ Error loading config: {e}")
        return 1
    
    # Get parameters (with CLI overrides)
    lag_months = args.lag if args.lag is not None else cfg['overlay'].get('lag_months', 2)
    scale_factor = args.scale if args.scale is not None else cfg['overlay'].get('scale_factor', 1.3)
    method = args.method if args.method is not None else cfg['overlay'].get('method', 'qoq')
    cost_bps = cfg['overlay'].get('transaction_cost_bps', 3.0)
    
    # Build output directory with lag-specific subfolder
    base_outdir = Path(args.outdir)
    lag_folder = f"lag_{lag_months}"
    outdir = base_outdir / lag_folder
    
    print(f"\n  Method:          {method.upper()} ({'12-month' if method == 'yoy' else '3-month'})")
    print(f"  Publication lag: {lag_months} months")
    print(f"  Scale factor:    {scale_factor}x")
    print(f"  Transaction cost: {cost_bps} bps")
    print(f"  Output folder:   {outdir}")
    
    # Load baseline portfolio
    print("\n[2/5] Loading baseline portfolio...")
    try:
        baseline = load_baseline_portfolio(args.baseline)
        print(f"✓ Baseline loaded: {len(baseline):,} days")
        print(f"  Date range: {baseline['date'].min().date()} to {baseline['date'].max().date()}")
    except Exception as e:
        print(f"✗ Error loading baseline: {e}")
        return 1
    
    # Load demand data
    print("\n[3/5] Loading copper demand proxy...")
    try:
        # Build demand data path from config
        demand_path = Path(cfg['data']['demand_proxy']['filepath'])
        demand = load_demand_data(str(demand_path))
        print(f"✓ Demand data loaded: {len(demand)} months")
        print(f"  Date range: {demand['date'].min().date()} to {demand['date'].max().date()}")
    except Exception as e:
        print(f"✗ Error loading demand data: {e}")
        return 1
    
    # Apply overlay
    print(f"\n[4/5] Applying {method.upper()} copper demand overlay...")
    try:
        overlay_df, metrics = apply_overlay(
            baseline_data=baseline,
            demand_data=demand,
            lag_months=lag_months,
            scale_factor=scale_factor,
            transaction_cost_bps=cost_bps,
            method=method
        )
        print("✓ Overlay applied successfully")
    except Exception as e:
        print(f"✗ Error applying overlay: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Write outputs
    print("\n[5/5] Writing outputs...")
    try:
        # Create lag-specific subdirectory
        outdir.mkdir(parents=True, exist_ok=True)
        
        # Generate timestamp with date AND time for version tracking
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        print(f"  Timestamp: {timestamp}")
        print(f"  Location:  {outdir}")
        print()
        
        # Write daily series CSV (full overlay results)
        daily_file = outdir / f"daily_series_china_demand_{method}_{lag_months}mo_{timestamp}.csv"
        overlay_df.to_csv(daily_file, index=False)
        print(f"  ✓ Daily series: {daily_file.name}")
        
        # Write standalone signals CSV (regime classifications only)
        signals_df = overlay_df[['date', 'price', 'regime', 'momentum_change', 'pos', 'pos_scaled']].copy()
        signals_df['scale_applied'] = signals_df['pos_scaled'] / signals_df['pos']
        signals_df['scale_applied'] = signals_df['scale_applied'].fillna(1.0)
        signals_df = signals_df.rename(columns={
            'pos': 'baseline_pos',
            'pos_scaled': 'overlay_pos'
        })
        
        signals_file = outdir / f"copper_demand_signals_{method}_{lag_months}mo_{timestamp}.csv"
        signals_df.to_csv(signals_file, index=False)
        print(f"  ✓ Demand signals: {signals_file.name}")
        
        # Write metrics JSON
        metrics_file = outdir / f"summary_metrics_{method}_{lag_months}mo_{timestamp}.json"
        with open(metrics_file, 'w') as f:
            json.dump(metrics, f, indent=2)
        print(f"  ✓ Metrics JSON: {metrics_file.name}")
        
        # Write human-readable summary
        summary_file = outdir / f"summary_{method}_{lag_months}mo_{timestamp}.txt"
        with open(summary_file, 'w') as f:
            f.write(format_metrics_summary(metrics))
        print(f"  ✓ Summary text: {summary_file.name}")
        
    except Exception as e:
        print(f"✗ Error writing outputs: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Print summary
    print("\n" + format_metrics_summary(metrics))
    
    # Validation check: NEUTRAL regime should match baseline
    valid = overlay_df[overlay_df['regime'].notna()]
    neutral = valid[valid['regime'] == 'NEUTRAL']
    
    if len(neutral) > 0:
        neutral_baseline = neutral['pnl_gross'].dropna()
        neutral_overlay = neutral['pnl_net_overlay'].dropna()
        
        if len(neutral_baseline) > 0 and len(neutral_overlay) > 0:
            neutral_baseline_sharpe = (
                neutral_baseline.mean() / neutral_baseline.std() * (252**0.5)
            )
            neutral_overlay_sharpe = (
                neutral_overlay.mean() / neutral_overlay.std() * (252**0.5)
            )
            diff = abs(neutral_overlay_sharpe - neutral_baseline_sharpe)
            
            print("\nCRITICAL VALIDATION CHECK:")
            print(f"  NEUTRAL regime baseline: {neutral_baseline_sharpe:.3f}")
            print(f"  NEUTRAL regime overlay:  {neutral_overlay_sharpe:.3f}")
            print(f"  Difference:              {diff:.3f}")
            
            if diff < 0.01:
                print("  ✓ PASS - NEUTRAL regime matches baseline")
            else:
                print("  ⚠ WARNING - NEUTRAL regime does not match baseline")
                print("  This may indicate an implementation issue")
    
    print("\n" + "="*80)
    print("✓ BUILD COMPLETE")
    print("="*80)
    print(f"\nOutput location: {outdir}")
    print(f"\nFiles generated:")
    print(f"  1. Full overlay:     {daily_file.name}")
    print(f"  2. Signals only:     {signals_file.name}")
    print(f"  3. Metrics (JSON):   {metrics_file.name}")
    print(f"  4. Summary (TXT):    {summary_file.name}")
    print(f"\nMethod: {method.upper()} ({'12-month momentum' if method == 'yoy' else '3-month momentum'})")
    print(f"Publication lag: {lag_months} months")
    print(f"\nTo test different lags: --lag 0, --lag 1, or --lag 2")
    print(f"To test different methods: --method yoy or --method qoq")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())