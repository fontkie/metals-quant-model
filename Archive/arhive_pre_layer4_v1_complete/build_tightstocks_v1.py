#!/usr/bin/env python3
# src/cli/build_tightstocks_v1.py
"""
Build script for TightStocks v1

Continuous Inventory Investment Surprise (IIS) - Renaissance-style

Expected Performance:
- Sharpe: 0.666 (IS), 0.774 (OOS)
- Degradation: +16.1% (IMPROVED OOS)
- Correlation with price sleeves: ~0.06

Usage:
    python build_tightstocks_v1.py
    
    Or with custom paths:
    python build_tightstocks_v1.py \
        --csv-price Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv \
        --csv-lme-stocks Data\copper\stocks\canonical\copper_lme_onwarrant_stocks.canonical.csv \
        --csv-comex-stocks Data\copper\stocks\canonical\copper_comex_stocks.canonical.csv \
        --csv-shfe-stocks Data\copper\stocks\canonical\copper_shfe_onwarrant_stocks.canonical.csv \
        --config Config\Copper\tightstocks_v1.yaml \
        --outdir outputs\Copper\TightStocks_v1
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import yaml

# Add paths for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src" / "core"))
sys.path.insert(0, str(project_root / "src" / "signals"))

from contract import build_core
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
    """
    Merge price and stock data into single DataFrame.
    
    Handles different column names across stock files:
    - LME: might be 'stocks' or 'lme_stocks'
    - COMEX: might be 'stocks' or 'comex_stocks'  
    - SHFE: might be 'stocks' or 'shfe_stocks'
    """
    
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
    # ========== 1. Parse arguments ==========
    parser = argparse.ArgumentParser(description='Build TightStocks v1')
    parser.add_argument('--csv-price', required=True, help='Price CSV path')
    parser.add_argument('--csv-lme-stocks', required=True, help='LME stocks CSV path')
    parser.add_argument('--csv-comex-stocks', required=True, help='COMEX stocks CSV path')
    parser.add_argument('--csv-shfe-stocks', required=True, help='SHFE stocks CSV path')
    parser.add_argument('--config', required=True, help='YAML config path')
    parser.add_argument('--outdir', required=True, help='Output directory')
    
    args = parser.parse_args()
    
    # ========== 2. Load data ==========
    print("Loading data files...")
    
    df_price = load_canonical_csv(args.csv_price, ['date', 'price'])
    print(f"  Price data: {len(df_price)} rows from {df_price['date'].min()} to {df_price['date'].max()}")
    
    df_lme_stocks = load_canonical_csv(args.csv_lme_stocks, ['date'])
    print(f"  LME stocks: {len(df_lme_stocks)} rows from {df_lme_stocks['date'].min()} to {df_lme_stocks['date'].max()}")
    
    df_comex_stocks = load_canonical_csv(args.csv_comex_stocks, ['date'])
    print(f"  COMEX stocks: {len(df_comex_stocks)} rows from {df_comex_stocks['date'].min()} to {df_comex_stocks['date'].max()}")
    
    df_shfe_stocks = load_canonical_csv(args.csv_shfe_stocks, ['date'])
    print(f"  SHFE stocks: {len(df_shfe_stocks)} rows from {df_shfe_stocks['date'].min()} to {df_shfe_stocks['date'].max()}")
    
    # Merge all data
    df = merge_stock_data(df_price, df_lme_stocks, df_comex_stocks, df_shfe_stocks)
    print(f"  Merged data: {len(df)} rows")
    print()
    
    # ========== 3. Load config ==========
    print(f"Loading config: {args.config}")
    with open(args.config, 'r') as f:
        cfg = yaml.safe_load(f)
    
    # Validate config structure
    if 'policy' not in cfg:
        raise ValueError("Config must have 'policy' block")
    if 'signal' not in cfg:
        raise ValueError("Config must have 'signal' block")
    print("  Config loaded successfully")
    print()
    
    # ========== 4. Generate signal ==========
    print("Generating TightStocks v1 signal...")
    signal_params = cfg['signal']
    
    pos_raw = generate_tightstocks_v1_signal(df, **signal_params)
    df['pos_raw'] = pos_raw
    
    # Signal diagnostics
    n_long = (pos_raw > 0).sum()
    pct_long = n_long / len(pos_raw) * 100
    avg_pos = pos_raw[pos_raw > 0].mean() if n_long > 0 else 0
    print(f"  Signal generated: {n_long} long positions ({pct_long:.1f}% of time)")
    print(f"  Average position when long: {avg_pos:.3f}")
    print()
    
    # ========== 5. Call Layer A ==========
    print("Calling Layer A (contract)...")
    daily_df, metrics = build_core(df, cfg)
    print("  Layer A execution complete")
    print()
    
    # ========== 6. Write outputs ==========
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    
    print(f"Writing outputs to {outdir}")
    
    # Daily series
    daily_df.to_csv(outdir / 'daily_series.csv', index=False)
    print(f"  ✓ daily_series.csv ({len(daily_df)} rows)")
    
    # Summary metrics
    with open(outdir / 'summary_metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"  ✓ summary_metrics.json")
    
    # Config copy (for audit trail)
    with open(outdir / 'config_used.yaml', 'w') as f:
        yaml.dump(cfg, f, default_flow_style=False)
    print(f"  ✓ config_used.yaml")
    
    print()
    
    # ========== 7. Print summary ==========
    print("=" * 80)
    print("TIGHTSTOCKS V1 - SUMMARY METRICS")
    print("=" * 80)
    print(f"Sharpe Ratio:     {metrics['sharpe']:.3f}")
    print(f"Annual Return:    {metrics['annual_return']*100:.2f}%")
    print(f"Annual Vol:       {metrics['annual_vol']*100:.2f}%")
    print(f"Max Drawdown:     {metrics['max_drawdown']*100:.2f}%")
    print(f"Observations:     {metrics['obs']}")
    print(f"Cost (bps):       {metrics['cost_bps']:.2f}")
    print("=" * 80)
    print()
    print("Build complete! Outputs in:", outdir)


if __name__ == '__main__':
    main()