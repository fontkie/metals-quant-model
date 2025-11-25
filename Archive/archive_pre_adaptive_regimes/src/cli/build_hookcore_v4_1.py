#!/usr/bin/env python3
# src/cli/build_hookcore_v4_1.py
"""
Build script for HookCore v4.1

V4.1 Changes:
- Academic regime filter (configurable via YAML)
- Only trades in high-vol, choppy markets
- Target: 0.80+ Sharpe, 10-15% activity

Usage:
    python build_hookcore_v4_1.py \
        --csv-price /mnt/project/copper_lme_3mo_canonical.csv \
        --csv-stocks /mnt/project/copper_lme_total_stocks_canonical.csv \
        --csv-iv /mnt/project/copper_lme_1mo_impliedvol_canonical.csv \
        --csv-fut-3mo /mnt/project/copper_lme_3mo_fut_canonical.csv \
        --csv-fut-12mo /mnt/project/copper_lme_12mo_fut_canonical.csv \
        --config hookcore_v4_1.yaml \
        --outdir /mnt/user-data/outputs/Copper/HookCore_v4_1
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
from hookcore_v4_1 import generate_hookcore_v4_signal


def load_canonical_csv(path: str, required_cols: list) -> pd.DataFrame:
    """Load and validate canonical CSV"""
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])

    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}' in {path}")

    return df.sort_values("date").reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="Build HookCore v4.1")
    parser.add_argument("--csv-price", required=True, help="Price canonical CSV")
    parser.add_argument(
        "--csv-stocks", required=False, help="Stocks canonical CSV (optional)"
    )
    parser.add_argument(
        "--csv-iv", required=False, help="Implied vol canonical CSV (optional)"
    )
    parser.add_argument(
        "--csv-fut-3mo", required=False, help="3mo futures canonical CSV (optional)"
    )
    parser.add_argument(
        "--csv-fut-12mo", required=False, help="12mo futures canonical CSV (optional)"
    )
    parser.add_argument("--config", required=True, help="YAML config file")
    parser.add_argument("--outdir", required=True, help="Output directory")

    args = parser.parse_args()

    print("=" * 70)
    print("HookCore v4.1 - Build Process")
    print("=" * 70)
    print("\nV4.1 Changes:")
    print("  • Academic regime filter (configurable thresholds)")
    print("  • Only trade in high-vol, choppy markets")
    print("  • Target: 0.80+ Sharpe, 10-15% activity")

    # ========== 1. LOAD PRICE DATA ==========
    print("\n[1/6] Loading price data...")
    df_price = load_canonical_csv(args.csv_price, ["date", "price"])
    df_price["ret"] = df_price["price"].pct_change()
    print(f"  ✓ Loaded {len(df_price)} price observations")
    print(f"  ✓ Date range: {df_price['date'].min()} to {df_price['date'].max()}")

    # ========== 2. LOAD REGIME DATA ==========
    print("\n[2/6] Loading regime data...")

    # Stocks
    if args.csv_stocks:
        df_stocks = load_canonical_csv(args.csv_stocks, ["date", "stocks"])
        stocks = df_stocks.set_index("date")["stocks"]
        print(f"  ✓ Loaded {len(stocks)} stocks observations")
    else:
        stocks = None
        print("  ⚠ Stocks data not provided (stocks regime filter disabled)")

    # Implied vol
    if args.csv_iv:
        df_iv = load_canonical_csv(args.csv_iv, ["date", "iv"])
        iv_1mo = df_iv.set_index("date")["iv"]
        print(f"  ✓ Loaded {len(iv_1mo)} IV observations")
    else:
        iv_1mo = None
        print("  ⚠ IV data not provided (safety filter disabled)")

    # Curve spread
    if args.csv_fut_3mo and args.csv_fut_12mo:
        df_fut_3mo = load_canonical_csv(args.csv_fut_3mo, ["date", "price"])
        df_fut_12mo = load_canonical_csv(args.csv_fut_12mo, ["date", "price"])

        df_curve = df_fut_3mo.merge(df_fut_3mo, on="date", suffixes=("_3mo", "_12mo"))
        df_curve["spread"] = df_curve["price_3mo"] - df_curve["price_12mo"]
        df_curve["spread_pct"] = (df_curve["spread"] / df_curve["price_12mo"]) * 100

        curve_spread_pct = df_curve.set_index("date")["spread_pct"]
        print(f"  ✓ Loaded {len(curve_spread_pct)} curve observations")
    else:
        curve_spread_pct = None
        print("  ⚠ Curve data not provided (safety filter disabled)")

    # ========== 3. LOAD CONFIG ==========
    print("\n[3/6] Loading configuration...")
    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f)

    signal_params = cfg["signal"]
    print(f"  ✓ Strategy: {signal_params.get('description', 'N/A')}")
    print(
        f"  ✓ BB params: {signal_params['bollinger']['lookback_days']}d / {signal_params['bollinger']['sigma_multiplier']}σ"
    )
    print(f"  ✓ Hold period: {signal_params['holding']['hold_days_trading']} days")

    # Print regime filter status
    academic_enabled = signal_params.get("academic_regime", {}).get("enabled", False)
    if academic_enabled:
        vol_pct = signal_params["academic_regime"]["vol_percentile"]
        trend_pct = signal_params["academic_regime"]["trend_percentile"]
        print(f"  ✓ Academic regime filter: ENABLED")
        print(f"    - Vol threshold: {vol_pct*100:.0f}th percentile")
        print(f"    - Trend threshold: {trend_pct*100:.0f}th percentile")
    else:
        print(f"  ✓ Academic regime filter: DISABLED")

    stocks_enabled = signal_params.get("regime", {}).get("use_regime_filter", False)
    print(f"  ✓ Stocks regime filter: {'ENABLED' if stocks_enabled else 'DISABLED'}")
    print(f"  ✓ Longs only: {signal_params['directional']['longs_only']}")

    # ========== 4. GENERATE SIGNAL ==========
    print("\n[4/6] Generating HookCore v4.1 signal...")

    # Extract academic regime parameters (with defaults)
    academic_params = signal_params.get("academic_regime", {})

    pos_raw = generate_hookcore_v4_signal(
        df=df_price,
        # Bollinger parameters
        bb_lookback=signal_params["bollinger"]["lookback_days"],
        bb_sigma=signal_params["bollinger"]["sigma_multiplier"],
        bb_shift=signal_params["bollinger"]["shift_bars"],
        # Regime data
        stocks=stocks,
        iv_1mo=iv_1mo,
        curve_spread_pct=curve_spread_pct,
        # Stocks regime threshold
        stocks_tight_threshold=signal_params["regime"]["stocks_tight_threshold"],
        # Hold period
        hold_days=signal_params["holding"]["hold_days_trading"],
        # Basic filters
        trend_lookback=signal_params["filters"]["trend_lookback"],
        trend_thresh=signal_params["filters"]["trend_thresh"],
        vol_lookback=signal_params["filters"]["vol_lookback"],
        vol_thresh=signal_params["filters"]["vol_thresh"],
        autocorr_lookback=signal_params["filters"]["autocorr_lookback"],
        autocorr_thresh=signal_params["filters"]["autocorr_thresh"],
        # Academic regime filter (NEW IN V4.1)
        use_academic_regime_filter=academic_params.get("enabled", True),
        regime_vol_lookback=academic_params.get("vol_lookback", 60),
        regime_vol_percentile=academic_params.get("vol_percentile", 0.50),
        regime_trend_ma_fast=academic_params.get("trend_ma_fast", 20),
        regime_trend_ma_slow=academic_params.get("trend_ma_slow", 200),
        regime_trend_percentile=academic_params.get("trend_percentile", 0.50),
        regime_autocorr_lookback=academic_params.get("autocorr_lookback", 20),
    )

    df_price["pos_raw"] = pos_raw

    print(f"  ✓ Signal generated")
    print(f"  ✓ Long days: {(pos_raw > 0).sum()} ({(pos_raw > 0).mean()*100:.1f}%)")
    print(f"  ✓ Flat days: {(pos_raw == 0).sum()} ({(pos_raw == 0).mean()*100:.1f}%)")
    print(f"  ✓ Mean |position|: {pos_raw.abs().mean():.3f}")

    # ========== 5. BUILD LAYER A ==========
    print("\n[5/6] Building Layer A execution contract...")

    daily_df, metrics = build_core(df_price, cfg)

    print(f"  ✓ Annual return: {metrics['annual_return']*100:+.2f}%")
    print(f"  ✓ Annual vol: {metrics['annual_vol']*100:.2f}%")
    print(f"  ✓ Sharpe ratio: {metrics['sharpe']:+.2f}")
    print(f"  ✓ Max drawdown: {metrics['max_drawdown']*100:.2f}%")
    print(f"  ✓ Observations: {metrics['obs']}")

    # ========== 6. WRITE OUTPUTS ==========
    print("\n[6/6] Writing outputs...")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Daily series
    daily_csv = outdir / "daily_series.csv"
    daily_df.to_csv(daily_csv, index=False)
    print(f"  ✓ {daily_csv}")

    # Summary metrics
    metrics_json = outdir / "summary_metrics.json"
    with open(metrics_json, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"  ✓ {metrics_json}")

    # ========== SUMMARY ==========
    print("\n" + "=" * 70)
    print("BUILD COMPLETE - HOOKCORE V4.1")
    print("=" * 70)
    print(f"\nPerformance Summary:")
    print(f"  Sharpe Ratio:    {metrics['sharpe']:+6.2f}")
    print(f"  Annual Return:   {metrics['annual_return']*100:+6.2f}%")
    print(f"  Annual Vol:      {metrics['annual_vol']*100:6.2f}%")
    print(f"  Max Drawdown:    {metrics['max_drawdown']*100:6.2f}%")

    # Calculate turnover
    turnover = daily_df["trade"].abs().sum() * 252 / len(daily_df)
    print(f"  Annual Turnover: {turnover:6.2f}x")

    # Activity
    activity_pct = (pos_raw > 0).mean() * 100
    print(f"  Activity:        {activity_pct:6.1f}%")

    # Compare to targets
    print(f"\n📊 vs V4.1 Targets:")
    target_sharpe = cfg["expected_improvements"]["v4_1_target_sharpe"]
    target_activity = cfg["expected_improvements"]["v4_1_target_activity"]
    target_turnover = cfg["expected_improvements"]["v4_1_target_turnover"]

    sharpe_status = "✅" if metrics["sharpe"] >= target_sharpe * 0.9 else "⚠️"
    activity_status = "✅" if 8 <= activity_pct <= 18 else "⚠️"
    turnover_status = "✅" if turnover <= target_turnover * 1.2 else "⚠️"

    print(
        f"  Sharpe: {metrics['sharpe']:.2f} vs {target_sharpe:.2f} target {sharpe_status}"
    )
    print(
        f"  Activity: {activity_pct:.1f}% vs {target_activity:.1f}% target {activity_status}"
    )
    print(
        f"  Turnover: {turnover:.1f}x vs {target_turnover:.1f}x target {turnover_status}"
    )

    # Compare to V4.0 baseline
    print(f"\n📈 vs V4.0 Baseline:")
    v4_sharpe = cfg["expected_improvements"]["v4_0_sharpe"]
    v4_activity = cfg["expected_improvements"]["v4_0_activity"]

    sharpe_improvement = metrics["sharpe"] - v4_sharpe
    activity_reduction = activity_pct - v4_activity

    print(
        f"  Sharpe: {metrics['sharpe']:.2f} vs {v4_sharpe:.2f} (v4.0) [{sharpe_improvement:+.2f}]"
    )
    print(
        f"  Activity: {activity_pct:.1f}% vs {v4_activity:.1f}% (v4.0) [{activity_reduction:+.1f}pp]"
    )

    print(f"\nOutputs written to: {outdir}")
    print("\nNext: Compare to v4.0 baseline")
    print(f"  python tools/compare_versions.py HookCore_v4 HookCore_v4_1")
    print()


if __name__ == "__main__":
    main()
