# src/cli/build_trendmedium.py
"""
TrendMedium Build Script WITH DIAGNOSTICS
------------------------------------------
Dual MA trend following (25/70) for medium-term trends.

Expected Performance:
  - Sharpe: ~0.45-0.55 (unconditional)
  - Faster response than TrendCore
  - Targets 2-4 month trends
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml
import numpy as np

# Import Layer A core
sys.path.append(str(Path(__file__).parent.parent.parent))
from src.core.contract import build_core
from src.signals.trendmedium import generate_trendmedium_signal


def main():
    ap = argparse.ArgumentParser(
        description="Build TrendMedium (Copper) – canonical CSV + YAML"
    )
    ap.add_argument("--csv", required=True, help="Path to canonical CSV")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--config", required=True, help="Path to YAML config")
    args = ap.parse_args()

    # ========== 1. LOAD CANONICAL CSV ==========
    print(f"[TrendMedium] Loading canonical CSV: {args.csv}")
    df = pd.read_csv(args.csv, parse_dates=["date"])

    # Validate schema
    assert (
        "date" in df.columns and "price" in df.columns
    ), "Canonical CSV must have lowercase 'date' and 'price' columns"

    print(
        f"[TrendMedium] Loaded {len(df)} rows from {df['date'].min()} to {df['date'].max()}"
    )

    # ========== 2. LOAD YAML CONFIG ==========
    print(f"[TrendMedium] Loading config: {args.config}")
    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f)

    # Validate required blocks
    assert "policy" in cfg, "Config must have 'policy' block"
    assert "signal" in cfg, "Config must have 'signal' block"

    # ========== 3. GENERATE SIGNAL ==========
    print(f"[TrendMedium] Generating signal with 25/70 MAs...")

    signal_cfg = cfg.get("signal", {}).get("moving_average", {})

    df["pos_raw"] = generate_trendmedium_signal(
        df,
        fast_ma=signal_cfg.get("fast_lookback_days", 25),
        slow_ma=signal_cfg.get("slow_lookback_days", 70),
        vol_lookback=cfg["policy"]["sizing"].get("vol_lookback_days_default", 63),
        range_threshold=signal_cfg.get("range_threshold", 0.10),
    )

    # ========== 3.5 DIAGNOSTIC: CHECK SIGNAL SCALING ==========
    pos_raw_stats = {
        "mean": df["pos_raw"].mean(),
        "mean_abs": df["pos_raw"].abs().mean(),
        "std": df["pos_raw"].std(),
        "min": df["pos_raw"].min(),
        "max": df["pos_raw"].max(),
        "pct_nonzero": (df["pos_raw"] != 0).mean() * 100,
    }

    print("\n" + "=" * 70)
    print("SIGNAL DIAGNOSTICS (pos_raw from signal generator)")
    print("=" * 70)
    print(f"  Mean:          {pos_raw_stats['mean']:+.4f}")
    print(f"  Mean |pos|:    {pos_raw_stats['mean_abs']:.4f}")
    print(f"  Std Dev:       {pos_raw_stats['std']:.4f}")
    print(f"  Min:           {pos_raw_stats['min']:+.4f}")
    print(f"  Max:           {pos_raw_stats['max']:+.4f}")
    print(f"  % Non-zero:    {pos_raw_stats['pct_nonzero']:.1f}%")
    print("=" * 70)

    # Check if signal looks properly scaled
    if pos_raw_stats["mean_abs"] > 0.7:
        print("⚠️  WARNING: Signal looks UNSCALED!")
        print(f"   Expected mean |pos_raw| around 0.35-0.45")
        print(f"   Got: {pos_raw_stats['mean_abs']:.3f}")
        print("\n   This suggests scaling factors are NOT being applied.")
        print("=" * 70 + "\n")
    else:
        print("✅ Signal scaling looks correct")
        print("=" * 70 + "\n")

    # ========== 4. RUN LAYER A EXECUTION ==========
    print(f"[TrendMedium] Running Layer A execution contract...")

    result, metrics = build_core(df=df, cfg=cfg)

    # ========== 4.5 DIAGNOSTIC: CHECK FINAL POSITIONS ==========
    pos_final_stats = {
        "mean": result["pos"].mean(),
        "mean_abs": result["pos"].abs().mean(),
        "std": result["pos"].std(),
        "min": result["pos"].min(),
        "max": result["pos"].max(),
    }

    print("\n" + "=" * 70)
    print("POSITION DIAGNOSTICS (after vol targeting)")
    print("=" * 70)
    print(f"  Mean:          {pos_final_stats['mean']:+.4f}")
    print(f"  Mean |pos|:    {pos_final_stats['mean_abs']:.4f}")
    print(f"  Std Dev:       {pos_final_stats['std']:.4f}")
    print(f"  Min:           {pos_final_stats['min']:+.4f}")
    print(f"  Max:           {pos_final_stats['max']:+.4f}")
    print("=" * 70 + "\n")

    # ========== 5. SAVE OUTPUTS ==========
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Daily series
    daily_path = outdir / "daily_series.csv"
    result.to_csv(daily_path, index=False)
    print(f"[TrendMedium] Saved daily series: {daily_path}")

    # Summary metrics
    metrics_path = outdir / "summary_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"[TrendMedium] Saved metrics: {metrics_path}")

    # Save diagnostics
    diagnostics = {
        "signal_stats": pos_raw_stats,
        "position_stats": pos_final_stats,
        "metrics": metrics,
    }
    diag_path = outdir / "diagnostics.json"
    with open(diag_path, "w") as f:
        json.dump(diagnostics, f, indent=2)
    print(f"[TrendMedium] Saved diagnostics: {diag_path}")

    # ========== 6. PRINT SUMMARY ==========
    print("\n" + "=" * 70)
    print("TrendMedium Build Complete")
    print("=" * 70)
    print(f"\nPerformance Metrics:")
    print(f"  Annual Return:  {metrics['annual_return']*100:+.2f}%")
    print(f"  Annual Vol:     {metrics['annual_vol']*100:.2f}%")
    print(f"  Sharpe Ratio:   {metrics['sharpe']:+.2f}")
    print(f"  Max Drawdown:   {metrics['max_drawdown']*100:.2f}%")
    print(f"\nExpected Performance:")
    print(f"  Sharpe Ratio:   ~0.45-0.55")
    print(f"  Annual Vol:     ~4-5%")
    print(f"  Target:         Medium-term trends (2-4 months)")

    # Check if results match expectations
    print("\n" + "=" * 70)
    if 0.40 <= metrics["sharpe"] <= 0.60 and 0.03 <= metrics["annual_vol"] <= 0.06:
        print("✅ Results within expected range!")
    else:
        print("⚠️  Results outside expected range")
        if metrics["annual_vol"] > 0.08:
            print("\n   DIAGNOSIS: Vol is too high!")
            print(f"   Got: {metrics['annual_vol']*100:.1f}%")
            print(f"   Expected: ~4-5%")
            print("\n   Likely cause: Signal is not properly scaled")
        elif metrics["sharpe"] < 0.3:
            print("\n   DIAGNOSIS: Sharpe is too low!")
            print(f"   Got: {metrics['sharpe']:.2f}")
            print(f"   Expected: ~0.45-0.55")
    print("=" * 70)

    print(f"\nOutputs written to: {outdir}")
    print("=" * 70 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())