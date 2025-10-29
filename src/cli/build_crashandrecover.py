# src/cli/build_crashandrecover_v2.py
"""
CrashAndRecover v2.0 Build Script (Layer B CLI Wrapper)
--------------------------------------------------------
Reads canonical CSV (price + IV + volume) + YAML, calls Layer A, writes outputs.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

# Import Layer A core
import sys

sys.path.append(str(Path(__file__).parent.parent))
from core.contract import build_core
from signals.crashandrecover import generate_crashandrecover_signal


def main():
    ap = argparse.ArgumentParser(
        description="Build CrashAndRecover v2.0 (Copper) — canonical CSV + YAML"
    )
    ap.add_argument("--csv-price", required=True, help="Path to price canonical CSV")
    ap.add_argument("--csv-volume", required=True, help="Path to volume canonical CSV")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--config", required=True, help="Path to YAML config")
    args = ap.parse_args()

    # ========== 1. LOAD CANONICAL CSVs ==========
    print(f"[CrashAndRecover] Loading price CSV: {args.csv_price}")
    df_price = pd.read_csv(args.csv_price, parse_dates=["date"])

    print(f"[CrashAndRecover] Loading volume CSV: {args.csv_volume}")
    df_volume = pd.read_csv(args.csv_volume, parse_dates=["date"])

    # Validate schemas
    assert (
        "date" in df_price.columns and "price" in df_price.columns
    ), "Price CSV must have lowercase 'date' and 'price' columns"

    # Find volume column (flexible naming)
    vol_cols = [c for c in df_volume.columns if c != "date"]
    assert (
        len(vol_cols) >= 1
    ), f"Volume CSV must have a data column. Found: {df_volume.columns.tolist()}"
    df_volume = df_volume.rename(columns={vol_cols[0]: "volume"})

    # Merge price and volume
    df = df_price.merge(df_volume, on="date", how="outer")
    df = df.sort_values("date").reset_index(drop=True)

    # Fill missing volume with forward-fill
    df["volume"] = df["volume"].ffill()

    # Drop rows missing critical data
    df = df.dropna(subset=["price", "volume"]).reset_index(drop=True)

    print(
        f"[CrashAndRecover] Merged {len(df)} rows from {df['date'].min()} to {df['date'].max()}"
    )

    # ========== 2. LOAD YAML CONFIG ==========
    print(f"[CrashAndRecover] Loading config: {args.config}")
    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f)

    # Validate required blocks
    assert "policy" in cfg, "YAML must have 'policy' block"
    assert "signal" in cfg, "YAML must have 'signal' block"

    policy = cfg["policy"]
    signal_cfg = cfg["signal"]

    # Check required policy blocks
    for block in ["calendar", "sizing", "costs", "pnl"]:
        assert block in policy, f"policy.{block} is required"

    assert (
        policy["pnl"]["t_plus_one_pnl"] is True
    ), "policy.pnl.t_plus_one_pnl must be true"

    print(f"[CrashAndRecover] Config validated ✓")

    # ========== 3. CALCULATE RETURNS (NEEDED FOR LAYER A) ==========
    df["ret"] = df["price"].pct_change().fillna(0.0)

    # ========== 4. GENERATE SIGNAL ==========
    print(f"[CrashAndRecover] Generating signal...")

    swing_cfg = signal_cfg["swing_structure"]
    vol_cfg = signal_cfg["volume_confirmation"]
    exit_cfg = signal_cfg["exit_logic"]
    risk_cfg = signal_cfg["risk_controls"]

    df["pos_raw"] = generate_crashandrecover_signal(
        df=df,
        structure_window=swing_cfg["window"],
        atr_lookback=swing_cfg["atr_lookback"],
        atr_tolerance=swing_cfg["atr_tolerance"],
        volume_lookback=vol_cfg["lookback"],
        volume_threshold=vol_cfg["threshold"],
        exit_timeout_days=exit_cfg["timeout_days"],
        signal_shift=risk_cfg["signal_shift"],
    )

    # ========== 5. RUN LAYER A CORE ==========
    print(f"[CrashAndRecover] Running Layer A execution contract...")
    daily_df, metrics = build_core(df, cfg)

    # ========== 6. WRITE OUTPUTS ==========
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Write daily series
    daily_series_path = outdir / "daily_series.csv"
    daily_df.to_csv(daily_series_path, index=False)
    print(f"[CrashAndRecover] Wrote daily_series.csv → {daily_series_path}")

    # Write metrics
    metrics_path = outdir / "summary_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"[CrashAndRecover] Wrote summary_metrics.json → {metrics_path}")

    # ========== 7. PRINT SUMMARY ==========
    print("\n" + "=" * 60)
    print("CrashAndRecover v2.0 Build Complete")
    print("=" * 60)
    print(f"Annual Return:  {metrics['annual_return']:>8.2%}")
    print(f"Annual Vol:     {metrics['annual_vol']:>8.2%}")
    print(f"Sharpe:         {metrics['sharpe']:>8.2f}")
    print(f"Max Drawdown:   {metrics['max_drawdown']:>8.2%}")
    print(f"Observations:   {metrics['obs']:>8,}")
    print(f"Cost (bps):     {metrics['cost_bps']:>8.1f}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
