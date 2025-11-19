# tools/validate_outputs.py
"""
Validate Sleeve Outputs Against Spec
-------------------------------------
Checks that daily_series.csv and summary_metrics.json match the contract.
"""

import argparse
import json
from pathlib import Path

import pandas as pd
import numpy as np


def validate_daily_series(df: pd.DataFrame) -> list[str]:
    """Validate daily_series.csv schema and integrity."""
    errors = []

    # Required columns
    required_cols = [
        "date",
        "price",
        "ret",
        "pos",
        "pos_for_ret_t",
        "trade",
        "cost",
        "pnl_gross",
        "pnl_net",
    ]

    for col in required_cols:
        if col not in df.columns:
            errors.append(f"❌ Missing required column: {col}")

    if errors:
        return errors

    # Check for NaNs in critical columns
    for col in ["pnl_net", "pos", "ret"]:
        if df[col].isna().sum() > len(df) * 0.01:  # Allow <1% NaNs (edge effects)
            errors.append(f"❌ Too many NaNs in {col}: {df[col].isna().sum()}")

    # Check pos_for_ret_t = pos.shift(1)
    expected_pos_for_ret = df["pos"].shift(1).fillna(0.0)
    if not np.allclose(df["pos_for_ret_t"].fillna(0), expected_pos_for_ret, atol=1e-6):
        errors.append(f"❌ pos_for_ret_t ≠ pos.shift(1) (T→T+1 violation)")

    # Check trade = pos.diff()
    expected_trade = df["pos"].diff().fillna(0.0)
    if not np.allclose(df["trade"].fillna(0), expected_trade, atol=1e-6):
        errors.append(f"❌ trade ≠ pos.diff() (turnover calculation error)")

    # Check pnl_gross = pos_for_ret_t * ret
    expected_pnl_gross = df["pos_for_ret_t"] * df["ret"]
    if not np.allclose(
        df["pnl_gross"].fillna(0), expected_pnl_gross.fillna(0), atol=1e-8
    ):
        errors.append(f"❌ pnl_gross ≠ pos_for_ret_t * ret")

    # Check costs are negative or zero
    if (df["cost"] > 0).any():
        errors.append(f"❌ Costs must be ≤ 0 (found positive values)")

    return errors


def validate_metrics(metrics: dict) -> list[str]:
    """Validate summary_metrics.json schema."""
    errors = []

    required_keys = [
        "annual_return",
        "annual_vol",
        "sharpe",
        "max_drawdown",
        "obs",
        "cost_bps",
    ]

    for key in required_keys:
        if key not in metrics:
            errors.append(f"❌ Missing required metric: {key}")

    if errors:
        return errors

    # Check types and ranges
    if not isinstance(metrics["obs"], int):
        errors.append(f"❌ 'obs' must be integer, got {type(metrics['obs'])}")

    if metrics["annual_vol"] < 0:
        errors.append(f"❌ annual_vol must be ≥ 0, got {metrics['annual_vol']}")

    if not -1 <= metrics["max_drawdown"] <= 0:
        errors.append(
            f"❌ max_drawdown must be in [-1, 0], got {metrics['max_drawdown']}"
        )

    return errors


def main():
    ap = argparse.ArgumentParser(description="Validate sleeve outputs")
    ap.add_argument("--outdir", required=True, help="Output directory to validate")
    args = ap.parse_args()

    outdir = Path(args.outdir)

    print(f"🔍 Validating outputs in: {outdir}\n")

    # ========== CHECK FILES EXIST ==========
    daily_series_path = outdir / "daily_series.csv"
    metrics_path = outdir / "summary_metrics.json"

    if not daily_series_path.exists():
        print(f"❌ Missing daily_series.csv")
        return 1

    if not metrics_path.exists():
        print(f"❌ Missing summary_metrics.json")
        return 1

    # ========== LOAD & VALIDATE ==========
    df = pd.read_csv(daily_series_path, parse_dates=["date"])
    with open(metrics_path, "r") as f:
        metrics = json.load(f)

    errors_daily = validate_daily_series(df)
    errors_metrics = validate_metrics(metrics)

    # ========== REPORT ==========
    all_errors = errors_daily + errors_metrics

    if all_errors:
        print("❌ VALIDATION FAILED\n")
        for err in all_errors:
            print(err)
        return 1
    else:
        print("✅ ALL CHECKS PASSED\n")
        print(f"   Rows:          {len(df):,}")
        print(f"   Date range:    {df['date'].min()} → {df['date'].max()}")
        print(f"   Sharpe:        {metrics['sharpe']:.2f}")
        print(f"   Annual vol:    {metrics['annual_vol']:.2%}")
        print(f"   Max drawdown:  {metrics['max_drawdown']:.2%}\n")
        return 0


if __name__ == "__main__":
    exit(main())
