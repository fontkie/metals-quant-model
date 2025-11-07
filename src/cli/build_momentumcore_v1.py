#!/usr/bin/env python3
# src/cli/build_momentumcore_v1.py
"""
Build script for MomentumCore v1

12-month Time Series Momentum (TSMOM) - Moskowitz, Ooi, Pedersen (2012)

Expected Performance:
- Sharpe: 0.534
- Return: 5.5% annual
- Vol: 10.3% annual
- Turnover: 8x (low)

Usage:
    python build_momentumcore_v1.py
    
    Or with custom paths:
    python build_momentumcore_v1.py \
        --csv-price Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv \
        --config Config\Copper\momentumcore_v1.yaml \
        --outdir outputs\Copper\MomentumCore_v1
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

# Add paths for imports
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src" / "core"))
sys.path.insert(0, str(project_root / "src" / "signals"))

from contract import build_core
from momentumcore_v1 import generate_momentumcore_v1_signal


def load_canonical_csv(path: str, required_cols: list) -> pd.DataFrame:
    """Load and validate canonical CSV"""
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])

    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}' in {path}")

    return df.sort_values("date").reset_index(drop=True)


def main():
    # Default paths matching project structure
    default_price = r"Data\copper\pricing\canonical\copper_lme_3mo.canonical.csv"
    default_config = r"Config\Copper\momentumcore_v1.yaml"
    default_outdir = r"outputs\Copper\MomentumCore_v1"

    parser = argparse.ArgumentParser(description="Build MomentumCore v1")
    parser.add_argument(
        "--csv-price", default=default_price, help="Price canonical CSV"
    )
    parser.add_argument("--config", default=default_config, help="YAML config file")
    parser.add_argument("--outdir", default=default_outdir, help="Output directory")

    args = parser.parse_args()

    print("=" * 70)
    print("MomentumCore v1 - Build Process")
    print("=" * 70)
    print("\nStrategy: 12-month Time Series Momentum (TSMOM)")
    print("  â€¢ Long if price > 12 months ago")
    print("  â€¢ Short if price < 12 months ago")
    print("  â€¢ Vol-scaled to 10% target")
    print("  â€¢ Expected: 0.534 Sharpe, 8x turnover")

    # ========== 1. LOAD PRICE DATA ==========
    print("\n[1/4] Loading price data...")
    df_price = load_canonical_csv(args.csv_price, ["date", "price"])
    df_price["ret"] = df_price["price"].pct_change()
    print(f"  âœ“ Loaded {len(df_price)} price observations")
    print(f"  âœ“ Date range: {df_price['date'].min()} to {df_price['date'].max()}")

    # ========== 2. LOAD CONFIG ==========
    print("\n[2/4] Loading configuration...")
    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f)

    signal_params = cfg["signal"]
    print(f"  âœ“ Strategy: {signal_params.get('description', 'N/A')}")
    print(f"  âœ“ Lookback: {signal_params['momentum']['lookback_days']} days")
    print(f"  âœ“ Vol target: {signal_params['vol_scaling']['target_annual']*100:.0f}%")
    print(f"  âœ“ Max leverage: {signal_params['vol_scaling']['max_leverage']:.1f}x")
    print(f"  âœ“ Longs only: {signal_params['directional']['longs_only']}")

    # ========== 3. GENERATE SIGNAL ==========
    print("\n[3/4] Generating MomentumCore v1 signal...")

    pos_raw = generate_momentumcore_v1_signal(
        df=df_price,
        lookback_days=signal_params["momentum"]["lookback_days"],
        vol_lookback_days=signal_params["vol_scaling"]["lookback_days"],
        vol_target_annual=signal_params["vol_scaling"]["target_annual"],
        max_leverage=signal_params["vol_scaling"]["max_leverage"],
        longs_only=signal_params["directional"]["longs_only"],
    )

    df_price["pos_raw"] = pos_raw

    # Calculate position statistics
    long_days = (pos_raw > 0).sum()
    short_days = (pos_raw < 0).sum()
    flat_days = (pos_raw == 0).sum()

    print(f"  âœ“ Signal generated")
    print(f"  âœ“ Long days:  {long_days} ({long_days/len(df_price)*100:.1f}%)")
    print(f"  âœ“ Short days: {short_days} ({short_days/len(df_price)*100:.1f}%)")
    print(f"  âœ“ Flat days:  {flat_days} ({flat_days/len(df_price)*100:.1f}%)")
    print(f"  âœ“ Mean |position|: {pos_raw.abs().mean():.3f}")

    # ========== 4. BUILD LAYER A ==========
    print("\n[4/4] Building Layer A execution contract...")

    daily_df, metrics = build_core(df_price, cfg)

    print(f"  âœ“ Annual return: {metrics['annual_return']*100:+.2f}%")
    print(f"  âœ“ Annual vol: {metrics['annual_vol']*100:.2f}%")
    print(f"  âœ“ Sharpe ratio: {metrics['sharpe']:+.2f}")
    print(f"  âœ“ Max drawdown: {metrics['max_drawdown']*100:.2f}%")
    print(f"  âœ“ Observations: {metrics['obs']}")

    # ========== 5. WRITE OUTPUTS ==========
    print("\n[5/5] Writing outputs...")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Daily series
    daily_csv = outdir / "daily_series.csv"
    daily_df.to_csv(daily_csv, index=False)
    print(f"  âœ“ {daily_csv}")

    # Summary metrics
    metrics_json = outdir / "summary_metrics.json"
    with open(metrics_json, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"  âœ“ {metrics_json}")

    # ========== SUMMARY ==========
    print("\n" + "=" * 70)
    print("BUILD COMPLETE - MOMENTUMCORE V1")
    print("=" * 70)
    print(f"\nPerformance Summary:")
    print(f"  Sharpe Ratio:    {metrics['sharpe']:+6.2f}")
    print(f"  Annual Return:   {metrics['annual_return']*100:+6.2f}%")
    print(f"  Annual Vol:      {metrics['annual_vol']*100:6.2f}%")
    print(f"  Max Drawdown:    {metrics['max_drawdown']*100:6.2f}%")

    # Calculate turnover
    turnover = daily_df["trade"].abs().sum() * 252 / len(daily_df)
    print(f"  Annual Turnover: {turnover:6.2f}x")

    # Compare to targets
    print(f"\nðŸ“Š vs Expected:")
    expected = cfg["expected_performance"]

    sharpe_status = "âœ…" if metrics["sharpe"] >= expected["sharpe"] * 0.9 else "âš ï¸"
    turnover_status = "âœ…" if turnover <= expected["turnover"] * 1.2 else "âš ï¸"

    print(
        f"  Sharpe: {metrics['sharpe']:.2f} vs {expected['sharpe']:.2f} expected {sharpe_status}"
    )
    print(
        f"  Turnover: {turnover:.1f}x vs {expected['turnover']:.1f}x expected {turnover_status}"
    )

    # Portfolio context
    print(f"\nðŸ“ˆ Portfolio Context:")
    portfolio = cfg["portfolio_metrics"]
    print(f"  Correlation with TrendCore: {portfolio['correlation_trendcore']:.3f}")
    print(
        f"  Correlation with TrendImpulse: {portfolio['correlation_trendimpulse']:.3f}"
    )
    print(f"  â†’ {portfolio['diversification']}")

    print(
        f"\n  Recommended allocation: {portfolio['three_sleeve_optimal_weight']['allocation']}"
    )
    print(
        f"  Expected portfolio Sharpe: {portfolio['three_sleeve_optimal_weight']['expected_sharpe']:.3f}"
    )
    print(
        f"  Improvement vs current: {portfolio['three_sleeve_optimal_weight']['improvement']}"
    )

    # vs HookCore
    vs_hook = cfg["vs_hookcore"]
    print(f"\nðŸ”„ vs HookCore v4 (replaced):")
    print(f"  HookCore v4: {vs_hook['hookcore_v4_sharpe']:.3f} Sharpe")
    print(f"  MomentumCore v1: {vs_hook['momentumcore_v1_sharpe']:.3f} Sharpe")
    print(f"  Improvement: {vs_hook['improvement']}")

    print(f"\nOutputs written to: {outdir}")
    print()


if __name__ == "__main__":
    main()
