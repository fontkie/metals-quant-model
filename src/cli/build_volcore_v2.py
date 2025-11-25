#!/usr/bin/env python3
# src/cli/build_volcore_v2.py
"""
Build script for VolCore v2 - Fixed Vol Targeting + IS/OOS Validated

Changes from v1:
- FIXED: Vol targeting using strategy returns (always_on), not underlying vol
- IS/OOS validated parameters (2011-2018 IS, 2019-2025 OOS)
- Leverage cap increased from 1.5 to 2.5

Output Structure:
    outputs/Copper/VolCore_v2/
    ├── 20251124_143522/          # Timestamped run
    │   ├── daily_series.csv
    │   ├── summary_metrics.json
    │   └── config_used.yaml
    └── latest/                    # Copy of most recent run

Usage:
    python build_volcore_v2.py ^
        --csv-price Data/copper/pricing/canonical/copper_lme_3mo.canonical.csv ^
        --csv-iv Data/copper/pricing/canonical/copper_lme_1mo_impliedvol.canonical.csv ^
        --config Config/Copper/volcore_v2.yaml ^
        --outdir outputs/Copper/VolCore_v2
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


def calculate_realized_vol(returns, window=21):
    return returns.rolling(window=window).std() * np.sqrt(252) * 100


def calculate_vol_spread_zscore(iv, rv, lookback=252):
    vol_spread = iv - rv
    zscore = (vol_spread - vol_spread.rolling(lookback).mean()) / vol_spread.rolling(lookback).std()
    return zscore, vol_spread


def generate_volcore_v2_signal(df, short_entry_zscore=1.5, long_entry_zscore=-1.0,
                                short_exit_zscore=0.5, long_exit_zscore=-0.3,
                                rv_window=21, zscore_lookback=252, min_hold_days=5,
                                longs_only=False, shorts_only=False):
    df = df.copy()
    rv = calculate_realized_vol(df['ret'], window=rv_window)
    zscore, vol_spread = calculate_vol_spread_zscore(df['iv'], rv, lookback=zscore_lookback)
    
    df['rv'] = rv
    df['vol_spread'] = vol_spread
    df['vol_spread_zscore'] = zscore
    
    pos_raw = pd.Series(0.0, index=df.index)
    current_pos = 0
    days_held = 0
    
    for i in range(1, len(df)):
        prev_z = zscore.iloc[i-1]
        if pd.isna(prev_z):
            pos_raw.iloc[i] = current_pos
            continue
        
        if current_pos != 0:
            days_held += 1
        else:
            days_held = 0
        
        new_pos = current_pos
        
        if current_pos == 0:
            if prev_z > short_entry_zscore and not longs_only:
                new_pos = -1
                days_held = 0
            elif prev_z < long_entry_zscore and not shorts_only:
                new_pos = 1
                days_held = 0
        elif current_pos == 1:
            if days_held >= min_hold_days and prev_z > long_exit_zscore:
                new_pos = 0
                if prev_z > short_entry_zscore and not longs_only:
                    new_pos = -1
                    days_held = 0
        elif current_pos == -1:
            if days_held >= min_hold_days and prev_z < short_exit_zscore:
                new_pos = 0
                if prev_z < long_entry_zscore and not shorts_only:
                    new_pos = 1
                    days_held = 0
        
        pos_raw.iloc[i] = new_pos
        current_pos = new_pos
    
    return pos_raw, df


def apply_vol_targeting(positions, returns, target_vol=0.10, vol_lookback=63, leverage_cap=2.5):
    """Vol targeting using strategy returns (always_on method)."""
    pos_lagged = positions.shift(1)
    strategy_returns = pos_lagged * returns
    strategy_vol = strategy_returns.ewm(span=vol_lookback, adjust=False).std() * np.sqrt(252)
    strategy_vol = strategy_vol.clip(lower=0.02)
    leverage = (target_vol / strategy_vol).shift(1).clip(upper=leverage_cap).fillna(1.0)
    return leverage, strategy_vol


def execute_with_costs(positions_scaled, returns, cost_bps=1.5):
    pos_lagged = positions_scaled.shift(1)
    pnl_gross = pos_lagged * returns
    trades = positions_scaled.diff().abs().fillna(0)
    costs = trades * cost_bps / 10000
    pnl_net = pnl_gross - costs
    return pnl_gross, pnl_net, trades, costs


def calculate_metrics(pnl_net, positions, warmup=252):
    pnl = pnl_net.iloc[warmup:]
    pos = positions.iloc[warmup:]
    
    if len(pnl) < 100:
        return {'error': 'Insufficient data'}
    
    ann_ret = pnl.mean() * 252
    ann_vol = pnl.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
    
    cum_ret = (1 + pnl).cumprod()
    max_dd = (cum_ret / cum_ret.expanding().max() - 1).min()
    
    long_pct = (pos == 1).mean() * 100
    short_pct = (pos == -1).mean() * 100
    flat_pct = (pos == 0).mean() * 100
    trades = (positions.diff().abs() > 0).iloc[warmup:].sum()
    trades_per_year = trades / (len(pnl) / 252)
    
    return {
        'sharpe': float(sharpe), 'annual_return': float(ann_ret),
        'annual_vol': float(ann_vol), 'max_drawdown': float(max_dd),
        'long_pct': float(long_pct), 'short_pct': float(short_pct),
        'flat_pct': float(flat_pct), 'trades_per_year': float(trades_per_year),
        'obs': int(len(pnl)),
    }


def main():
    print("=" * 70)
    print("VOLCORE V2 - Build (Fixed Vol Targeting)")
    print("=" * 70)
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-price", default=r"Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv")
    parser.add_argument("--csv-iv", default=r"Data\copper\pricing\canonical\copper_lme_1mo_impliedvol.canonical.csv")
    parser.add_argument("--config", default=r"Config\Copper\volcore_v2.yaml")
    parser.add_argument("--outdir", default=r"outputs\Copper\VolCore_v2")
    args = parser.parse_args()
    
    # Load data
    print("\n[1/5] Loading data...")
    df_price = pd.read_csv(args.csv_price, parse_dates=['date'])
    df_price['ret'] = df_price['price'].pct_change()
    df_iv = pd.read_csv(args.csv_iv, parse_dates=['date'])
    
    df = pd.merge(df_price, df_iv, on='date', how='left')
    df['iv'] = df['iv'].ffill()
    df = df[df['iv'].notna()].reset_index(drop=True)
    print(f"  ✓ {len(df)} days from {df['date'].min().date()} to {df['date'].max().date()}")
    
    # Load config
    print("\n[2/5] Loading config...")
    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    signal_params = cfg['signal']
    sizing = cfg['policy']['sizing']
    print(f"  ✓ Short entry z > {signal_params['entry_thresholds']['short_zscore']}")
    print(f"  ✓ Long entry z < {signal_params['entry_thresholds']['long_zscore']}")
    print(f"  ✓ Strategy type: {sizing.get('strategy_type', 'NOT SET')}")
    
    # Generate signal
    print("\n[3/5] Generating signal...")
    pos_raw, df = generate_volcore_v2_signal(
        df, short_entry_zscore=signal_params['entry_thresholds']['short_zscore'],
        long_entry_zscore=signal_params['entry_thresholds']['long_zscore'],
        short_exit_zscore=signal_params['exit_thresholds']['short_zscore'],
        long_exit_zscore=signal_params['exit_thresholds']['long_zscore'],
        rv_window=signal_params['realized_vol']['window_days'],
        zscore_lookback=signal_params['zscore']['lookback_days'],
        min_hold_days=signal_params['holding']['min_days'],
    )
    df['pos_raw'] = pos_raw
    print(f"  ✓ Long: {(pos_raw==1).sum()} Short: {(pos_raw==-1).sum()} Flat: {(pos_raw==0).sum()}")
    
    # Vol targeting
    print("\n[4/5] Applying vol targeting (strategy returns method)...")
    leverage, _ = apply_vol_targeting(pos_raw, df['ret'], sizing['ann_target'],
                                       sizing['vol_lookback_days_default'], sizing['leverage_cap_default'])
    pos_scaled = pos_raw * leverage
    df['pos'] = pos_scaled
    df['leverage'] = leverage
    
    warmup = 252
    print(f"  ✓ Avg leverage: {leverage.iloc[warmup:].mean():.3f}x")
    print(f"  ✓ Cap hit: {(leverage.iloc[warmup:] >= sizing['leverage_cap_default']*0.99).mean()*100:.1f}%")
    
    # Execute
    print("\n[5/5] Executing with costs...")
    cost_bps = cfg['policy']['costs']['one_way_bps_default']
    pnl_gross, pnl_net, trades, costs = execute_with_costs(pos_scaled, df['ret'], cost_bps)
    df['pnl_gross'] = pnl_gross
    df['pnl_net'] = pnl_net
    
    metrics = calculate_metrics(pnl_net, pos_raw, warmup)
    metrics['cost_bps'] = cost_bps
    
    # Write outputs with timestamp and latest folder
    base_outdir = Path(args.outdir)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    timestamped_dir = base_outdir / timestamp
    latest_dir = base_outdir / 'latest'
    
    timestamped_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nWriting outputs to {timestamped_dir}")
    
    daily_cols = ['date','price','ret','iv','rv','vol_spread','vol_spread_zscore',
                  'pos_raw','leverage','pos','pnl_gross','pnl_net']
    df[[c for c in daily_cols if c in df.columns]].to_csv(timestamped_dir/'daily_series.csv', index=False)
    print(f"  ✓ daily_series.csv")
    
    with open(timestamped_dir/'summary_metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"  ✓ summary_metrics.json")
    
    with open(timestamped_dir/'config_used.yaml', 'w') as f:
        yaml.dump(cfg, f)
    print(f"  ✓ config_used.yaml")
    
    # Update "latest" folder (copy for Windows compatibility)
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    shutil.copytree(timestamped_dir, latest_dir)
    print(f"  ✓ Updated latest/ folder")
    
    # Summary
    print("\n" + "=" * 70)
    print("VOLCORE V2 - COMPLETE")
    print("=" * 70)
    print(f"  Sharpe:     {metrics['sharpe']:+.3f}")
    print(f"  Return:     {metrics['annual_return']*100:+.2f}%")
    print(f"  Vol:        {metrics['annual_vol']*100:.2f}% (target: {sizing['ann_target']*100}%)")
    print(f"  Max DD:     {metrics['max_drawdown']*100:.2f}%")
    print(f"  Trades/yr:  {metrics['trades_per_year']:.1f}")
    
    vol_error = abs(metrics['annual_vol'] - sizing['ann_target']) / sizing['ann_target'] * 100
    print(f"\n  Vol error: {vol_error:.1f}% {'✓' if vol_error < 15 else '⚠'}")
    print(f"\n  Outputs:")
    print(f"    Timestamped: {timestamped_dir}")
    print(f"    Latest:      {latest_dir}")


if __name__ == "__main__":
    main()