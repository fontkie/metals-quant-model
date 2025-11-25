#!/usr/bin/env python3
# src/cli/build_tightstocks_v2_fixed.py
"""
Build script for TightStocks v2 - FIXED VERSION

Uses proper vol targeting (strategy returns method) and full execution layer
with validation and turnover metrics.

Expected Performance (with proper vol targeting):
- Sharpe: 0.55-0.75
- Realized vol: 10% ± 15%
- Correlation with price sleeves: ~0.06

Output Structure:
    outputs/Copper/TightStocks_v2/
    ├── 20251124_143522/          # Timestamped run
    │   ├── daily_series.csv
    │   ├── summary_metrics.json
    │   ├── config_used.yaml
    │   ├── turnover_metrics.json
    │   └── validation.json
    └── latest/                    # Copy of most recent run

Usage:
    python build_tightstocks_v2_fixed.py ^
        --csv-price Data/copper/pricing/canonical/copper_lme_3mo.canonical.csv ^
        --csv-lme-stocks Data/copper/stocks/canonical/copper_lme_onwarrant_stocks.canonical.csv ^
        --csv-comex-stocks Data/copper/stocks/canonical/copper_comex_stocks.canonical.csv ^
        --csv-shfe-stocks Data/copper/stocks/canonical/copper_shfe_onwarrant_stocks.canonical.csv ^
        --config Config/Copper/tightstocks_v2.yaml ^
        --outdir outputs/Copper/TightStocks_v2
"""

import argparse
import json
import sys
import shutil
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np
import yaml

# Add paths for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src" / "core"))
sys.path.insert(0, str(project_root / "src" / "signals"))

# Import from project modules
from vol_targeting import target_volatility, classify_strategy_type
from execution import execute_single_sleeve
from tightstocks_v1 import generate_tightstocks_v1_signal


def load_canonical_csv(path: str, required_cols: list) -> pd.DataFrame:
    """Load and validate canonical CSV format."""
    if not Path(path).exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    
    df = pd.read_csv(path, parse_dates=['date'])
    
    # Validate required columns
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in {path}: {missing}")
    
    # Sort by date
    df = df.sort_values('date').reset_index(drop=True)
    
    return df


def merge_stock_data(
    df_price: pd.DataFrame,
    df_lme_stocks: pd.DataFrame,
    df_comex_stocks: pd.DataFrame,
    df_shfe_stocks: pd.DataFrame
) -> pd.DataFrame:
    """Merge price and stock data into single DataFrame."""
    
    # Start with price data
    df = df_price[['date', 'price']].copy()
    
    # Merge LME stocks
    lme_col = 'lme_stocks' if 'lme_stocks' in df_lme_stocks.columns else 'stocks'
    df_lme = df_lme_stocks[['date', lme_col]].copy()
    df_lme = df_lme.rename(columns={lme_col: 'lme_stocks'})
    df = df.merge(df_lme, on='date', how='left')
    
    # Merge COMEX stocks
    comex_col = 'comex_stocks' if 'comex_stocks' in df_comex_stocks.columns else 'stocks'
    df_comex = df_comex_stocks[['date', comex_col]].copy()
    df_comex = df_comex.rename(columns={comex_col: 'comex_stocks'})
    df = df.merge(df_comex, on='date', how='left')
    
    # Merge SHFE stocks
    shfe_col = 'shfe_stocks' if 'shfe_stocks' in df_shfe_stocks.columns else 'stocks'
    df_shfe = df_shfe_stocks[['date', shfe_col]].copy()
    df_shfe = df_shfe.rename(columns={shfe_col: 'shfe_stocks'})
    df = df.merge(df_shfe, on='date', how='left')
    
    return df


def main():
    print("=" * 70)
    print("TIGHTSTOCKS V2 - Build (Fixed Vol Targeting)")
    print("=" * 70)
    
    # ========== 1. Parse arguments ==========
    parser = argparse.ArgumentParser(description='Build TightStocks v2 (Fixed)')
    parser.add_argument('--csv-price', required=True, help='Price CSV path')
    parser.add_argument('--csv-lme-stocks', required=True, help='LME stocks CSV path')
    parser.add_argument('--csv-comex-stocks', required=True, help='COMEX stocks CSV path')
    parser.add_argument('--csv-shfe-stocks', required=True, help='SHFE stocks CSV path')
    parser.add_argument('--config', required=True, help='YAML config path')
    parser.add_argument('--outdir', required=True, help='Output directory')
    
    args = parser.parse_args()
    
    # ========== 2. Load data ==========
    print("\n[1/5] Loading data...")
    
    df_price = load_canonical_csv(args.csv_price, ['date', 'price'])
    print(f"  Price data: {len(df_price)} rows from {df_price['date'].min()} to {df_price['date'].max()}")
    
    df_lme_stocks = load_canonical_csv(args.csv_lme_stocks, ['date'])
    print(f"  LME stocks: {len(df_lme_stocks)} rows")
    
    df_comex_stocks = load_canonical_csv(args.csv_comex_stocks, ['date'])
    print(f"  COMEX stocks: {len(df_comex_stocks)} rows")
    
    df_shfe_stocks = load_canonical_csv(args.csv_shfe_stocks, ['date'])
    print(f"  SHFE stocks: {len(df_shfe_stocks)} rows")
    
    # Merge all data
    df = merge_stock_data(df_price, df_lme_stocks, df_comex_stocks, df_shfe_stocks)
    df['ret'] = df['price'].pct_change()
    print(f"  Merged data: {len(df)} rows")
    
    # ========== 3. Load config ==========
    print("\n[2/5] Loading config...")
    with open(args.config, 'r') as f:
        cfg = yaml.safe_load(f)
    
    # Validate config structure
    if 'policy' not in cfg:
        raise ValueError("Config must have 'policy' block")
    if 'signal' not in cfg:
        raise ValueError("Config must have 'signal' block")
    
    # Extract parameters
    signal_params = cfg['signal']
    sizing = cfg['policy']['sizing']
    target_vol = sizing.get('ann_target', 0.10)
    leverage_cap = sizing.get('leverage_cap_default', 2.5)
    vol_lookback = sizing.get('vol_lookback_days_default', 63)
    strategy_type = sizing.get('strategy_type', 'always_on')
    cost_bps = cfg['policy']['costs'].get('one_way_bps_default', 3.0)
    
    print(f"  ✓ Strategy type: {strategy_type}")
    print(f"  ✓ Target vol: {target_vol*100:.0f}%")
    print(f"  ✓ Leverage cap: {leverage_cap}x")
    
    # ========== 4. Generate signal ==========
    print("\n[3/5] Generating TightStocks signal...")
    pos_raw = generate_tightstocks_v1_signal(df, **signal_params)
    df['pos_raw'] = pos_raw
    
    n_long = (pos_raw > 0.01).sum()
    pct_long = n_long / len(pos_raw) * 100
    avg_pos = pos_raw[pos_raw > 0.01].mean() if n_long > 0 else 0
    print(f"  ✓ Long positions: {n_long} ({pct_long:.1f}% of time)")
    print(f"  ✓ Average position when long: {avg_pos:.3f}")
    
    # Auto-classify diagnostics
    auto_classification = classify_strategy_type(pos_raw)
    if auto_classification != strategy_type:
        print(f"  ⚠️  Config says '{strategy_type}' but auto-classification says '{auto_classification}'")
    
    # ========== 5. Apply vol targeting ==========
    print(f"\n[4/5] Applying vol targeting (strategy_type='{strategy_type}')...")
    
    # Calculate strategy returns for vol targeting
    strategy_returns_raw = pos_raw.shift(1) * df['ret']
    
    # Use project's vol targeting module
    leverage, realized_vol_est = target_volatility(
        strategy_returns=strategy_returns_raw,
        underlying_returns=df['ret'],
        positions=pos_raw,
        target_vol=target_vol,
        strategy_type=strategy_type,
        lambda_decay=0.94,
        vol_floor=0.02,
        vol_cap=0.40,
        max_leverage=leverage_cap,
        min_history=63,
    )
    
    pos_scaled = pos_raw * leverage
    df['pos'] = pos_scaled
    df['leverage'] = leverage
    
    # Diagnostics
    warmup = 260
    leverage_used = leverage.iloc[warmup:]
    print(f"  Leverage stats:")
    print(f"    Mean:     {leverage_used.mean():.3f}x")
    print(f"    Median:   {leverage_used.median():.3f}x")
    print(f"    Max:      {leverage_used.max():.3f}x (cap: {leverage_cap:.1f}x)")
    cap_hit_pct = (leverage_used >= leverage_cap * 0.99).sum() / len(leverage_used) * 100
    print(f"    Cap hit:  {cap_hit_pct:.1f}% of time")
    
    # Check realized vol
    strat_ret = df['pos'].shift(1) * df['ret']
    realized_vol = strat_ret.iloc[warmup:].std() * np.sqrt(252)
    print(f"  Realized vol: {realized_vol*100:.2f}% (target: {target_vol*100:.1f}%)")
    
    if realized_vol < target_vol * 0.85:
        print(f"  ⚠️  Vol shortfall: {(1 - realized_vol/target_vol)*100:.1f}%")
    
    # ========== 6. Execute with costs ==========
    print("\n[5/5] Executing with costs...")
    
    result_df, metrics, turnover_metrics, validation = execute_single_sleeve(
        positions=df['pos'],
        returns=df['ret'],
        cost_bps=cost_bps,
        expected_vol=target_vol,
    )
    
    # Add date and other columns back
    result_df['date'] = df['date'].values
    result_df['price'] = df['price'].values
    result_df['pos_raw'] = df['pos_raw'].values
    result_df['leverage'] = df['leverage'].values
    
    print("  ✓ Execution complete")
    
    # ========== 7. Write outputs with timestamp ==========
    base_outdir = Path(args.outdir)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    timestamped_dir = base_outdir / timestamp
    latest_dir = base_outdir / 'latest'
    
    timestamped_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nWriting outputs to {timestamped_dir}")
    
    # Daily series - reorder columns
    daily_cols = ['date', 'price', 'pos_raw', 'leverage', 'pos', 'pos_for_ret', 
                  'trade', 'cost', 'pnl_gross', 'pnl_net']
    result_df[[c for c in daily_cols if c in result_df.columns]].to_csv(
        timestamped_dir / 'daily_series.csv', index=False
    )
    print(f"  ✓ daily_series.csv ({len(result_df)} rows)")
    
    # Summary metrics
    metrics['cost_bps'] = cost_bps
    metrics['obs'] = len(result_df)
    
    with open(timestamped_dir / 'summary_metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"  ✓ summary_metrics.json")
    
    # Config copy
    with open(timestamped_dir / 'config_used.yaml', 'w') as f:
        yaml.dump(cfg, f, default_flow_style=False)
    print(f"  ✓ config_used.yaml")
    
    # Turnover metrics
    with open(timestamped_dir / 'turnover_metrics.json', 'w') as f:
        json.dump(turnover_metrics, f, indent=2)
    print(f"  ✓ turnover_metrics.json")
    
    # Validation results
    validation_serializable = {k: bool(v) for k, v in validation.items()}
    with open(timestamped_dir / 'validation.json', 'w') as f:
        json.dump(validation_serializable, f, indent=2)
    print(f"  ✓ validation.json")
    
    # Update "latest" folder (copy for Windows compatibility)
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    shutil.copytree(timestamped_dir, latest_dir)
    print(f"  ✓ Updated latest/ folder")
    
    # ========== 8. Print summary ==========
    print("\n" + "=" * 70)
    print("TIGHTSTOCKS V2 - COMPLETE")
    print("=" * 70)
    print(f"  Sharpe:     {metrics['sharpe']:+.3f}")
    print(f"  Return:     {metrics['annual_return']*100:+.2f}%")
    print(f"  Vol:        {metrics['annual_vol']*100:.2f}% (target: {target_vol*100:.0f}%)")
    print(f"  Max DD:     {metrics['max_drawdown']*100:.2f}%")
    print(f"  Trades/yr:  {turnover_metrics['trades_per_year']:.1f}")
    
    vol_error = abs(metrics['annual_vol'] - target_vol) / target_vol * 100
    print(f"\n  Vol error: {vol_error:.1f}% {'✓' if vol_error < 15 else '⚠'}")
    
    print(f"\n  Turnover:   {turnover_metrics['annual_turnover']:.2f}x per year")
    print(f"  Cost drag:  {metrics['cost_drag_sharpe']:.3f} Sharpe points")
    
    print("\n  Validation checks:")
    for check, passed in validation.items():
        status = "✓" if passed else "✗"
        print(f"    {status} {check}")
    
    print(f"\n  Outputs:")
    print(f"    Timestamped: {timestamped_dir}")
    print(f"    Latest:      {latest_dir}")


if __name__ == '__main__':
    main()