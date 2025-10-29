# src/cli/build_trendcore_v2.py
"""
TrendCore v2.0 Build Script (Layer B CLI Wrapper)
--------------------------------------------------
Reads canonical CSV + YAML, calls Layer A, writes outputs.
"""

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

# Import Layer A core
import sys

sys.path.append(str(Path(__file__).parent.parent))
from core.contract import build_core
from signals.trendcore import generate_trendcore_signal


def main():
    ap = argparse.ArgumentParser(
        description="Build TrendCore v2.0 (Copper) — canonical CSV + YAML"
    )
    ap.add_argument("--csv", required=True, help="Path to canonical CSV")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--config", required=True, help="Path to YAML config")
    args = ap.parse_args()

    # ========== 1. LOAD CANONICAL CSV ==========
    print(f"[TrendCore] Loading canonical CSV: {args.csv}")
    df = pd.read_csv(args.csv, parse_dates=["date"])

    # Validate schema
    assert (
        "date" in df.columns and "price" in df.columns
    ), "Canonical CSV must have lowercase 'date' and 'price' columns"

    print(
        f"[TrendCore] Loaded {len(df)} rows from {df['date'].min()} to {df['date'].max()}"
    )

    # ========== 2. LOAD YAML CONFIG ==========
    print(f"[TrendCore] Loading config: {args.config}")
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

    print(f"[TrendCore] Config validated ✓")

    # ========== 3. CALCULATE RETURNS (NEEDED FOR LAYER A) ==========
    df["ret"] = df["price"].pct_change().fillna(0.0)

    # ========== 4. GENERATE SIGNAL ==========
    print(f"[TrendCore] Generating signal...")

    ma_cfg = signal_cfg["moving_average"]

    df["pos_raw"] = generate_trendcore_signal(
        df=df,
        ma_lookback=ma_cfg["lookback_days"],
        buffer_pct=ma_cfg.get("buffer_pct", 0.0),
        ma_shift=ma_cfg.get("shift_bars", 1),
    )

    # ========== 5. RUN LAYER A CORE ==========
    print(f"[TrendCore] Running Layer A execution contract...")
    daily_df, metrics = build_core(df, cfg)

    # ========== 6. WRITE OUTPUTS ==========
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Write daily series
    daily_series_path = outdir / "daily_series.csv"
    daily_df.to_csv(daily_series_path, index=False)
    print(f"[TrendCore] Wrote daily_series.csv → {daily_series_path}")

    # Write metrics
    metrics_path = outdir / "summary_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"[TrendCore] Wrote summary_metrics.json → {metrics_path}")

    # ========== 7. PRINT SUMMARY ==========
    print("\n" + "=" * 60)
    print("TrendCore v2.0 Build Complete")
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
