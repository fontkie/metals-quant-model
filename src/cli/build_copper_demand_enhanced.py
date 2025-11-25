r"""
Build Copper Demand Overlay - ENHANCED VERSION
Applies demand regime scaling with aggressive 0.0x override.

Enhancement: When demand=DECLINING + rally + long → GO FLAT (0.0x)
Performance: +12.9 Sharpe full period, +24.0 Sharpe OOS (2019-2025)

Output Structure:
  C:\Code\Metals\outputs\Copper\Portfolio\copper_demand_enhanced\
    └── lag_X\  (X = 0, 1, or 2)
        ├── daily_series_china_demand_enhanced_Xmo_YYYYMMDD_HHMMSS.csv
        ├── copper_demand_signals_enhanced_Xmo_YYYYMMDD_HHMMSS.csv
        ├── summary_metrics_enhanced_Xmo_YYYYMMDD_HHMMSS.json
        └── summary_enhanced_Xmo_YYYYMMDD_HHMMSS.txt

Author: Kieran
Date: November 21, 2025
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

from overlays.copper_demand_enhanced import (
    load_demand_data,
    apply_overlay,
    format_metrics_summary
)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Build Copper Demand Overlay - ENHANCED VERSION',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
Examples:
  # Basic usage (uses lag from config, aggressive override ON)
  python src\cli\build_copper_demand_enhanced.py \
      --baseline C:\Code\Metals\outputs\Copper\Portfolio\BaselineEqualWeight\latest\daily_series.csv \
      --config Config\copper\copper_demand_enhanced.yaml

  # Override lag setting
  python src\cli\build_copper_demand_enhanced.py \
      --baseline C:\Code\Metals\outputs\Copper\Portfolio\BaselineEqualWeight\latest\daily_series.csv \
      --config Config\copper\copper_demand_enhanced.yaml \
      --lag 1

  # Disable aggressive override (test standard scaling only)
  python src\cli\build_copper_demand_enhanced.py \
      --baseline C:\Code\Metals\outputs\Copper\Portfolio\BaselineEqualWeight\latest\daily_series.csv \
      --config Config\copper\copper_demand_enhanced.yaml \
      --no-aggressive

ENHANCEMENT:
  Aggressive 0.0x Override
  - When: demand=DECLINING + price rallying +3% + position long >0.3
  - Action: Scale to 0.0x (GO FLAT) instead of 0.77x
  - Rationale: 17% win rate, -2.59% expected return, -0.756 IR
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
        default='outputs/Copper/Portfolio/copper_demand_enhanced',
        help='Output directory (default: outputs/Copper/Portfolio/copper_demand_enhanced)'
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
        '--no-aggressive',
        action='store_true',
        help='Disable aggressive 0.0x override (use standard scaling only)'
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
    
    # Check for required columns
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
    print("COPPER DEMAND OVERLAY - ENHANCED VERSION BUILD")
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
    cost_bps = cfg['overlay'].get('transaction_cost_bps', 3.0)
    aggressive_override = not args.no_aggressive  # Default ON unless --no-aggressive
    
    # Build output directory with lag-specific subfolder
    base_outdir = Path(args.outdir)
    lag_folder = f"lag_{lag_months}"
    outdir = base_outdir / lag_folder
    
    print(f"\n  Method:            QoQ-Enhanced (3-month)")
    print(f"  Publication lag:   {lag_months} months")
    print(f"  Scale factor:      {scale_factor}x")
    print(f"  Transaction cost:  {cost_bps} bps")
    print(f"  Aggressive override: {'ENABLED' if aggressive_override else 'DISABLED'}")
    if aggressive_override:
        print(f"    → GO FLAT (0.0x) when demand↓ + rally + long>0.3")
    print(f"  Output folder:     {outdir}")
    
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
    print(f"\n[4/5] Applying ENHANCED copper demand overlay...")
    try:
        overlay_df, metrics = apply_overlay(
            baseline_data=baseline,
            demand_data=demand,
            lag_months=lag_months,
            scale_factor=scale_factor,
            transaction_cost_bps=cost_bps,
            aggressive_override=aggressive_override
        )
        print("✓ Overlay applied successfully")
        if aggressive_override and 'aggressive_override' in metrics:
            print(f"  Aggressive override fired: {metrics['aggressive_override']['days']} days "
                  f"({metrics['aggressive_override']['pct_of_trading']:.1f}%)")
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
        
        # Generate timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        print(f"  Timestamp: {timestamp}")
        print(f"  Location:  {outdir}")
        print()
        
        # Write daily series CSV
        daily_file = outdir / f"daily_series_china_demand_enhanced_{lag_months}mo_{timestamp}.csv"
        overlay_df.to_csv(daily_file, index=False)
        print(f"  ✓ Daily series: {daily_file.name}")
        
        # Write standalone signals CSV
        signals_df = overlay_df[['date', 'price', 'regime', 'momentum_change', 
                                  'pos', 'pos_scaled', 'aggressive_override_active']].copy()
        signals_df['scale_applied'] = signals_df['pos_scaled'] / signals_df['pos']
        signals_df['scale_applied'] = signals_df['scale_applied'].fillna(1.0)
        signals_df = signals_df.rename(columns={
            'pos': 'baseline_pos',
            'pos_scaled': 'overlay_pos'
        })
        
        signals_file = outdir / f"copper_demand_signals_enhanced_{lag_months}mo_{timestamp}.csv"
        signals_df.to_csv(signals_file, index=False)
        print(f"  ✓ Demand signals: {signals_file.name}")
        
        # Write metrics JSON
        metrics_file = outdir / f"summary_metrics_enhanced_{lag_months}mo_{timestamp}.json"
        with open(metrics_file, 'w') as f:
            json.dump(metrics, f, indent=2)
        print(f"  ✓ Metrics JSON: {metrics_file.name}")
        
        # Write human-readable summary
        summary_file = outdir / f"summary_enhanced_{lag_months}mo_{timestamp}.txt"
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
    
    print("\n" + "="*80)
    print("✓ BUILD COMPLETE - ENHANCED VERSION")
    print("="*80)
    print(f"\nOutput location: {outdir}")
    print(f"\nEnhancement Details:")
    print(f"  Aggressive Override: {'ENABLED' if aggressive_override else 'DISABLED'}")
    if aggressive_override:
        print(f"  Trigger: demand=DECLINING + price +3% over 20d + long >0.3")
        print(f"  Action: Scale to 0.0x (GO FLAT)")
        print(f"  Fired: {metrics['aggressive_override']['days']} days "
              f"({metrics['aggressive_override']['pct_of_trading']:.1f}%)")
    print(f"\nPublication lag: {lag_months} months")
    print(f"\nTo disable aggressive override: --no-aggressive")
    print(f"To test different lags: --lag 0, --lag 1, or --lag 2")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())