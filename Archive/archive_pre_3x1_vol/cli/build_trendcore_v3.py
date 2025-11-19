# src/cli/build_trendcore_v3.py
"""
TrendCore v3 Build Script WITH DIAGNOSTICS
-------------------------------------------
Dual MA trend following with rangebound awareness.

Expected Performance:
  - Sharpe: 0.51 (unconditional)
  - Sharpe: 2.0-2.5 (in trending regimes)
  - Max DD: -13.7%
  - Annual Vol: ~4.6%
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
from src.signals.trendcore import generate_trendcore_signal


def main():
    ap = argparse.ArgumentParser(
        description="Build TrendCore v3 (Copper) — canonical CSV + YAML"
    )
    ap.add_argument("--csv", required=True, help="Path to canonical CSV")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--config", required=True, help="Path to YAML config")
    args = ap.parse_args()

    # ========== 1. LOAD CANONICAL CSV ==========
    print(f"[TrendCore v3] Loading canonical CSV: {args.csv}")
    df = pd.read_csv(args.csv, parse_dates=["date"])

    # Validate schema
    assert (
        "date" in df.columns and "price" in df.columns
    ), "Canonical CSV must have lowercase 'date' and 'price' columns"

    print(
        f"[TrendCore v3] Loaded {len(df)} rows from {df['date'].min()} to {df['date'].max()}"
    )

    # ========== 2. LOAD YAML CONFIG ==========
    print(f"[TrendCore v3] Loading config: {args.config}")
    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f)

    # Validate required blocks
    assert "policy" in cfg, "Config must have 'policy' block"
    assert "signal" in cfg, "Config must have 'signal' block"

    # ========== 3. GENERATE SIGNAL ==========
    print(f"[TrendCore v3] Generating signal...")

    signal_cfg = cfg.get("signal", {}).get("moving_average", {})

    # Try new v3 parameter names first, fall back to v2 if needed
    try:
        # v3 style with named parameters
        df["pos_raw"] = generate_trendcore_signal(
            df,
            fast_ma=signal_cfg.get("fast_lookback_days", 30),
            slow_ma=signal_cfg.get("slow_lookback_days", 100),
            vol_lookback=cfg["policy"]["sizing"].get("vol_lookback_days_default", 63),
            range_threshold=signal_cfg.get("range_threshold", 0.10),
        )
        print("[TrendCore v3] ✅ Using v3 signal parameters (fast_ma, slow_ma, etc.)")
    except TypeError as e:
        # v2 compatibility - if function expects old parameters
        print(f"[TrendCore v3] ⚠️  WARNING: Using v2-compatible parameter names!")
        print(f"[TrendCore v3] Error was: {e}")
        df["pos_raw"] = generate_trendcore_signal(
            df,
            ma_lookback=signal_cfg.get("fast_lookback_days", 30),
            buffer_pct=0.0,
            ma_shift=1,
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
        print(f"   Expected mean |pos_raw| around 0.35-0.45 for v3")
        print(f"   Got: {pos_raw_stats['mean_abs']:.3f}")
        print("\n   This suggests the v3 scaling factors are NOT being applied.")
        print("   Check that your trendcore.py has the v3 code with:")
        print("     - range_scale (rangebound detection)")
        print("     - quality_scale (trend quality)")
        print("     - vol_scale (volatility regime)")
        print("\n   The signal should return scaled values, not just ±1!")
        print("=" * 70 + "\n")
    else:
        print("✅ Signal scaling looks correct for v3")
        print("=" * 70 + "\n")

    # ========== 4. RUN LAYER A EXECUTION ==========
    print(f"[TrendCore v3] Running Layer A execution contract...")

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
    print(f"[TrendCore v3] Saved daily series: {daily_path}")

    # Summary metrics
    metrics_path = outdir / "summary_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"[TrendCore v3] Saved metrics: {metrics_path}")

    # Save diagnostics
    diagnostics = {
        "signal_stats": pos_raw_stats,
        "position_stats": pos_final_stats,
        "metrics": metrics,
    }
    diag_path = outdir / "diagnostics.json"
    with open(diag_path, "w") as f:
        json.dump(diagnostics, f, indent=2)
    print(f"[TrendCore v3] Saved diagnostics: {diag_path}")

    # ========== 6. PRINT SUMMARY ==========
    print("\n" + "=" * 70)
    print("TrendCore v3 Build Complete")
    print("=" * 70)
    print(f"\nPerformance Metrics:")
    print(f"  Annual Return:  {metrics['annual_return']*100:+.2f}%")
    print(f"  Annual Vol:     {metrics['annual_vol']*100:.2f}%")
    print(f"  Sharpe Ratio:   {metrics['sharpe']:+.2f}")
    print(f"  Max Drawdown:   {metrics['max_drawdown']*100:.2f}%")
    print(f"\nExpected v3 Performance:")
    print(f"  Annual Return:  ~+2.25%")
    print(f"  Annual Vol:     ~4.6%")
    print(f"  Sharpe Ratio:   ~0.51")
    print(f"  Max Drawdown:   ~-13.7%")

    # Check if results match expectations
    print("\n" + "=" * 70)
    if (
        abs(metrics["sharpe"] - 0.51) < 0.05
        and abs(metrics["annual_vol"] - 0.046) < 0.01
    ):
        print("✅ Results match expected v3 performance!")
    else:
        print("⚠️  Results DO NOT match expected v3 performance")
        if metrics["annual_vol"] > 0.08:
            print("\n   DIAGNOSIS: Vol is too high!")
            print(f"   Got: {metrics['annual_vol']*100:.1f}%")
            print(f"   Expected: ~4.6%")
            print("\n   Likely cause: Signal is not properly scaled")
            print("   The v3 scaling factors are not being applied.")
        elif metrics["sharpe"] < 0.3:
            print("\n   DIAGNOSIS: Sharpe is too low!")
            print(f"   Got: {metrics['sharpe']:.2f}")
            print(f"   Expected: ~0.51")
    print("=" * 70)

    print(f"\nOutputs written to: {outdir}")
    print("=" * 70 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
