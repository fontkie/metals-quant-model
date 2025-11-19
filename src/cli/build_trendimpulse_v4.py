#!/usr/bin/env python3
# src/cli/build_trendimpulse_v4.py
"""
Build TrendImpulse v4
---------------------
Quality momentum strategy with regime specialization.

Expected Performance:
  - Gross Sharpe: 0.483
  - Net Sharpe: 0.421 @ 3bp
  - Turnover: ~630x
  - Activity: ~90%
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
from src.signals.trendimpulse_v4 import generate_trendimpulse_signal


def main():
    """Main build process"""

    ap = argparse.ArgumentParser(
        description="Build TrendImpulse v4 (Copper) - canonical CSV + YAML"
    )
    ap.add_argument("--csv", required=True, help="Path to canonical CSV")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--config", required=True, help="Path to YAML config")
    args = ap.parse_args()

    # ========== 1. LOAD CANONICAL CSV ==========
    print(f"[TrendImpulse v4] Loading canonical CSV: {args.csv}")
    df = pd.read_csv(args.csv, parse_dates=["date"])

    # Validate schema
    assert (
        "date" in df.columns and "price" in df.columns
    ), "Canonical CSV must have lowercase 'date' and 'price' columns"

    print(
        f"[TrendImpulse v4] Loaded {len(df)} rows from {df['date'].min()} to {df['date'].max()}"
    )

    # ========== 2. LOAD YAML CONFIG ==========
    print(f"[TrendImpulse v4] Loading config: {args.config}")
    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f)

    # Validate required blocks
    assert "policy" in cfg, "Config must have 'policy' block"
    assert "signal" in cfg, "Config must have 'signal' block"

    # ========== 3. GENERATE SIGNAL ==========
    print(f"[TrendImpulse v4] Generating signal...")

    signal_cfg = cfg["signal"]

    df["pos_raw"] = generate_trendimpulse_signal(
        df,
        momentum_window=signal_cfg.get("momentum_window", 20),
        entry_threshold=signal_cfg.get("entry_threshold", 0.010),
        exit_threshold=signal_cfg.get("exit_threshold", 0.003),
        weekly_vol_updates=signal_cfg.get("weekly_vol_updates", True),
        update_frequency=signal_cfg.get("update_frequency", 5),
        use_regime_scaling=signal_cfg.get("use_regime_scaling", True),
        vol_window=signal_cfg.get("vol_window", 63),
        vol_percentile_window=signal_cfg.get("vol_percentile_window", 252),
        low_vol_threshold=signal_cfg.get("low_vol_threshold", 0.40),
        medium_vol_threshold=signal_cfg.get("medium_vol_threshold", 0.75),
        low_vol_scale=signal_cfg.get("low_vol_scale", 1.5),
        medium_vol_scale=signal_cfg.get("medium_vol_scale", 0.4),
        high_vol_scale=signal_cfg.get("high_vol_scale", 0.7),
    )

    # ========== 3.5 SIGNAL DIAGNOSTICS ==========
    pos_raw_stats = {
        "mean": df["pos_raw"].mean(),
        "mean_abs": df["pos_raw"].abs().mean(),
        "std": df["pos_raw"].std(),
        "min": df["pos_raw"].min(),
        "max": df["pos_raw"].max(),
        "pct_nonzero": (df["pos_raw"].abs() > 0.01).mean() * 100,
    }

    print("\n" + "=" * 70)
    print("SIGNAL DIAGNOSTICS (pos_raw)")
    print("=" * 70)
    print(f"  Mean:          {pos_raw_stats['mean']:+.4f}")
    print(f"  Mean |pos|:    {pos_raw_stats['mean_abs']:.4f}")
    print(f"  Std Dev:       {pos_raw_stats['std']:.4f}")
    print(f"  Min:           {pos_raw_stats['min']:+.4f}")
    print(f"  Max:           {pos_raw_stats['max']:+.4f}")
    print(f"  % Active:      {pos_raw_stats['pct_nonzero']:.1f}%")
    print("=" * 70 + "\n")

    # ========== 4. RUN LAYER A EXECUTION ==========
    print(f"[TrendImpulse v4] Running Layer A execution contract...")

    result, metrics = build_core(df=df, cfg=cfg)

    # ========== 4.5 POSITION DIAGNOSTICS ==========
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

    # Calculate turnover
    turnover = result["trade"].abs().sum()
    gross_sharpe = result["pnl_gross"].mean() / result["pnl_gross"].std() * np.sqrt(252)

    # ========== 5. SAVE OUTPUTS ==========
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Daily series
    daily_path = outdir / "daily_series.csv"
    result.to_csv(daily_path, index=False)
    print(f"[TrendImpulse v4] Saved daily series: {daily_path}")

    # Summary metrics
    metrics_enhanced = {
        **metrics,
        "gross_sharpe": float(gross_sharpe),
        "turnover": float(turnover),
    }

    metrics_path = outdir / "summary_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics_enhanced, f, indent=2)
    print(f"[TrendImpulse v4] Saved metrics: {metrics_path}")

    # Save diagnostics
    diagnostics = {
        "signal_stats": pos_raw_stats,
        "position_stats": pos_final_stats,
        "metrics": metrics_enhanced,
    }
    diag_path = outdir / "diagnostics.json"
    with open(diag_path, "w") as f:
        json.dump(diagnostics, f, indent=2)
    print(f"[TrendImpulse v4] Saved diagnostics: {diag_path}")

    # ========== 6. PRINT SUMMARY ==========
    print("\n" + "=" * 70)
    print("TrendImpulse v4 Build Complete")
    print("=" * 70)
    print(f"\nPerformance Metrics:")
    print(f"  Gross Sharpe:   {gross_sharpe:+.2f}")
    print(f"  Net Sharpe:     {metrics['sharpe']:+.2f}")
    print(f"  Annual Return:  {metrics['annual_return']*100:+.2f}%")
    print(f"  Annual Vol:     {metrics['annual_vol']*100:.2f}%")
    print(f"  Max Drawdown:   {metrics['max_drawdown']*100:.2f}%")
    print(f"  Turnover:       {turnover:.1f}x")
    print(f"  Activity:       {pos_raw_stats['pct_nonzero']:.1f}%")

    print(f"\nExpected v4 Performance:")
    print(f"  Gross Sharpe:   ~0.48")
    print(f"  Net Sharpe:     ~0.42")
    print(f"  Turnover:       ~630x")
    print(f"  Activity:       ~90%")

    # Check if results match expectations
    print("\n" + "=" * 70)
    if abs(gross_sharpe - 0.483) < 0.05 and abs(metrics["sharpe"] - 0.421) < 0.05:
        print("✅ Results match expected v4 performance!")
    else:
        print("⚠️  Results differ from expected v4 performance")
        print(f"   Got: Gross {gross_sharpe:.2f}, Net {metrics['sharpe']:.2f}")
        print(f"   Expected: Gross ~0.48, Net ~0.42")
    print("=" * 70)

    print(f"\nOutputs written to: {outdir}")
    print("=" * 70 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
