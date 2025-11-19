#!/usr/bin/env python3
"""
Build TrendImpulse v3
--------------------
Fast momentum strategy with 3-day holds and cooldown.

Usage:
    python build_trendimpulse_v3.py
"""

import sys
import os
import json
import yaml
import pandas as pd
import numpy as np
from pathlib import Path

# Import strategy components
from trendimpulse_v3_final import generate_trendimpulse_signal
from contract import build_core


def main():
    """Main build process"""

    print("=" * 70)
    print("TrendImpulse v3 - Fast Momentum Strategy")
    print("=" * 70)
    print()

    # ========== 1. LOAD PRICE DATA ==========
    price_file = "/mnt/project/copper_lme_3mo_canonical.csv"
    print(f"Loading price data: {price_file}")

    df = pd.read_csv(price_file, parse_dates=["date"])
    df.columns = df.columns.str.lower()

    # Validate schema
    assert (
        "date" in df.columns and "price" in df.columns
    ), "CSV must have lowercase 'date' and 'price' columns"

    print(f"  Loaded {len(df)} rows from {df['date'].min()} to {df['date'].max()}")
    print()

    # ========== 2. LOAD CONFIG ==========
    config_path = "trendimpulse_v3.yaml"
    print(f"Loading config: {config_path}")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    print(f"  Strategy: {config['strategy']['name']}")
    print(f"  Version: {config['strategy']['version']}")
    print()

    # ========== 3. GENERATE SIGNAL ==========
    print("Generating TrendImpulse signal...")
    signal_params = config["signal"]
    print(f"  Momentum window: {signal_params.get('momentum_window', 20)}d")
    print(f"  Min momentum: {signal_params.get('min_momentum_pct', 0.005)*100}%")
    print(f"  Vol filter: {signal_params.get('vol_filter', True)}")
    print(
        f"  Vol percentile threshold: {signal_params.get('vol_percentile_threshold', 0.85)*100}%"
    )
    print()

    df["pos_raw"] = generate_trendimpulse_signal(
        df,
        momentum_window=signal_params.get("momentum_window", 20),
        min_momentum_pct=signal_params.get("min_momentum_pct", 0.005),
        vol_filter=signal_params.get("vol_filter", True),
        vol_window=signal_params.get("vol_window", 63),
        vol_percentile_threshold=signal_params.get("vol_percentile_threshold", 0.85),
    )

    # ========== 3.5 SIGNAL DIAGNOSTICS ==========
    pos_raw_stats = {
        "mean": df["pos_raw"].mean(),
        "mean_abs": df["pos_raw"].abs().mean(),
        "std": df["pos_raw"].std(),
        "min": df["pos_raw"].min(),
        "max": df["pos_raw"].max(),
        "pct_nonzero": (df["pos_raw"] != 0).mean() * 100,
    }

    print("=" * 70)
    print("SIGNAL DIAGNOSTICS (pos_raw)")
    print("=" * 70)
    print(f"  Mean:          {pos_raw_stats['mean']:+.4f}")
    print(f"  Mean |pos|:    {pos_raw_stats['mean_abs']:.4f}")
    print(f"  Std Dev:       {pos_raw_stats['std']:.4f}")
    print(f"  Min:           {pos_raw_stats['min']:+.4f}")
    print(f"  Max:           {pos_raw_stats['max']:+.4f}")
    print(f"  % Non-zero:    {pos_raw_stats['pct_nonzero']:.1f}%")
    print("=" * 70)
    print()

    # ========== 4. BUILD LAYER A CONFIG ==========
    # Convert our config to Layer A format
    layer_a_config = {
        "policy": {
            "sizing": {
                "ann_target": config["execution"]["ann_target"],
                "vol_lookback_days_default": 63,
                "leverage_cap_default": config["execution"]["leverage_cap"],
            },
            "costs": {
                "one_way_bps_default": config["execution"]["cost_bps"],
            },
        }
    }

    # ========== 5. RUN LAYER A EXECUTION ==========
    print("Running through Layer A execution contract...")
    result_df, metrics = build_core(df=df, cfg=layer_a_config)
    print("  Execution complete")
    print()

    # ========== 5.5 POSITION DIAGNOSTICS ==========
    pos_final_stats = {
        "mean": result_df["pos"].mean(),
        "mean_abs": result_df["pos"].abs().mean(),
        "std": result_df["pos"].std(),
        "min": result_df["pos"].min(),
        "max": result_df["pos"].max(),
    }

    print("=" * 70)
    print("POSITION DIAGNOSTICS (after vol targeting)")
    print("=" * 70)
    print(f"  Mean:          {pos_final_stats['mean']:+.4f}")
    print(f"  Mean |pos|:    {pos_final_stats['mean_abs']:.4f}")
    print(f"  Std Dev:       {pos_final_stats['std']:.4f}")
    print(f"  Min:           {pos_final_stats['min']:+.4f}")
    print(f"  Max:           {pos_final_stats['max']:+.4f}")
    print("=" * 70)
    print()

    # ========== 6. PRINT SUMMARY ==========
    print("=" * 70)
    print("PERFORMANCE SUMMARY")
    print("=" * 70)
    print(f"Annual Return:       {metrics['annual_return']*100:>8.2f}%")
    print(
        f"Annual Vol:          {metrics['annual_vol']*100:>8.2f}%  (target: {config['execution']['ann_target']*100:.1f}%)"
    )
    print(f"Sharpe Ratio:        {metrics['sharpe']:>8.2f}")
    print(f"Max Drawdown:        {metrics['max_drawdown']*100:>8.2f}%")
    print(f"Observations:        {metrics['obs']:>8.0f}")
    print(f"Activity Rate:       {pos_raw_stats['pct_nonzero']:>8.1f}%")
    print("=" * 70)
    print()

    # ========== 7. SAVE OUTPUTS ==========
    output_dir = Path(config["output"]["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    # Daily series
    daily_path = output_dir / "daily_series.csv"
    result_df.to_csv(daily_path, index=False)
    print(f"Daily series saved: {daily_path}")

    # Summary metrics
    metrics_enhanced = {
        **metrics,
        "signal_stats": pos_raw_stats,
        "position_stats": pos_final_stats,
    }

    metrics_path = output_dir / "summary_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics_enhanced, f, indent=2)
    print(f"Metrics saved: {metrics_path}")

    print()
    print("Build complete!")
    print("=" * 70)

    return metrics, result_df


if __name__ == "__main__":
    metrics, results_df = main()
