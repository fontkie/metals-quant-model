# src/cli/build_momentumtail_v2.py
"""
MomentumTail v2.0 Build Script (Layer B CLI Wrapper)
-----------------------------------------------------
Reads canonical CSV (price + IV) + YAML, calls Layer A, writes outputs.
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
from signals.momentumtail import generate_momentumtail_signal


def main():
    ap = argparse.ArgumentParser(
        description="Build MomentumTail v2.0 (Copper) — canonical CSV + YAML"
    )
    ap.add_argument("--csv-price", required=True, help="Path to price canonical CSV")
    ap.add_argument("--csv-iv", required=True, help="Path to IV canonical CSV")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--config", required=True, help="Path to YAML config")
    args = ap.parse_args()

    # ========== 1. LOAD CANONICAL CSVs ==========
    print(f"[MomentumTail] Loading price CSV: {args.csv_price}")
    df_price = pd.read_csv(args.csv_price, parse_dates=["date"])

    print(f"[MomentumTail] Loading IV CSV: {args.csv_iv}")
    df_iv = pd.read_csv(args.csv_iv, parse_dates=["date"])

    # Validate schemas
    assert (
        "date" in df_price.columns and "price" in df_price.columns
    ), "Price CSV must have lowercase 'date' and 'price' columns"

    # Find IV column (flexible naming)
    iv_cols = [c for c in df_iv.columns if c != "date"]
    assert (
        len(iv_cols) >= 1
    ), f"IV CSV must have a data column. Found columns: {df_iv.columns.tolist()}"

    # Rename IV column to 'iv' for consistency
    iv_col_name = iv_cols[0]  # Take first non-date column
    df_iv = df_iv.rename(columns={iv_col_name: "iv"})
    print(f"[MomentumTail] Using column '{iv_col_name}' as IV data")

    # Merge on date (outer join to keep all dates)
    df = df_price.merge(df_iv, on="date", how="outer").sort_values("date")

    # Drop rows with missing price
    df = df.dropna(subset=["price"]).reset_index(drop=True)

    # Calculate realized vol as backup for missing IV (pre-2011 data)
    df["ret_for_vol"] = df["price"].pct_change().fillna(0.0)
    df["realized_vol"] = df["ret_for_vol"].rolling(21, min_periods=21).std() * np.sqrt(
        252
    )

    # Fill missing IV with realized vol, then forward-fill any remaining gaps
    df["iv"] = df["iv"].fillna(df["realized_vol"]).fillna(method="ffill")

    # Drop rows where IV is still missing (start of series)
    df = df.dropna(subset=["iv"]).reset_index(drop=True)

    print(
        f"[MomentumTail] Using realized vol proxy for {df['iv'].isna().sum()} missing IV dates"
    )

    print(
        f"[MomentumTail] Merged {len(df)} rows from {df['date'].min()} to {df['date'].max()}"
    )

    # ========== 2. LOAD YAML CONFIG ==========
    print(f"[MomentumTail] Loading config: {args.config}")
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

    print(f"[MomentumTail] Config validated ✓")

    # ========== 3. CALCULATE RETURNS (NEEDED FOR LAYER A) ==========
    df["ret"] = df["price"].pct_change().fillna(0.0)

    # ========== 4. GENERATE SIGNAL ==========
    print(f"[MomentumTail] Generating signal...")

    vol_cfg = signal_cfg["volatility_regime"]
    trend_cfg = signal_cfg["trend_confirmation"]
    mom_cfg = signal_cfg["momentum_persistence"]
    risk_cfg = signal_cfg["risk_controls"]

    df["pos_raw"] = generate_momentumtail_signal(
        df=df,
        iv_ma_lookback=vol_cfg["iv_ma_lookback"],
        iv_spike_threshold=vol_cfg["iv_spike_threshold"],
        donchian_lookback=trend_cfg["donchian_lookback"],
        atr_lookback=mom_cfg["atr_lookback"],
        atr_ma_lookback=mom_cfg["atr_ma_lookback"],
        atr_threshold=mom_cfg["atr_threshold"],
        signal_shift=risk_cfg["signal_shift"],
    )

    # ========== 5. RUN LAYER A CORE ==========
    print(f"[MomentumTail] Running Layer A execution contract...")
    daily_df, metrics = build_core(df, cfg)

    # ========== 6. WRITE OUTPUTS ==========
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Write daily series
    daily_series_path = outdir / "daily_series.csv"
    daily_df.to_csv(daily_series_path, index=False)
    print(f"[MomentumTail] Wrote daily_series.csv → {daily_series_path}")

    # Write metrics
    metrics_path = outdir / "summary_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"[MomentumTail] Wrote summary_metrics.json → {metrics_path}")

    # ========== 7. PRINT SUMMARY ==========
    print("\n" + "=" * 60)
    print("MomentumTail v2.0 Build Complete")
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
