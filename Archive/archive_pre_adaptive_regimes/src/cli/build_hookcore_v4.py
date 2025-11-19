#!/usr/bin/env python3
# src/cli/build_hookcore_v4.py
"""
Build script for HookCore v4.0

Usage:
    python build_hookcore_v4.py \
        --csv-price /mnt/project/copper_lme_3mo_canonical.csv \
        --csv-stocks /mnt/project/copper_lme_total_stocks_canonical.csv \
        --csv-iv /mnt/project/copper_lme_1mo_impliedvol_canonical.csv \
        --csv-fut-3mo /mnt/project/copper_lme_3mo_fut_canonical.csv \
        --csv-fut-12mo /mnt/project/copper_lme_12mo_fut_canonical.csv \
        --config hookcore_v4.yaml \
        --outdir /mnt/user-data/outputs/Copper/HookCore_v4
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
from hookcore_v4 import generate_hookcore_v4_signal


def load_canonical_csv(path: str, required_cols: list) -> pd.DataFrame:
    """Load and validate canonical CSV"""
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])

    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}' in {path}")

    return df.sort_values("date").reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="Build HookCore v4.0")
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
    print("HookCore v4.0 - Build Process")
    print("=" * 70)
    print("\nV4 Changes:")
    print("  • BB: 10d/2.0σ (optimal from diagnostics)")
    print("  • Hold: 3 days (mean reversion completes faster)")
    print("  • No autocorr filter (removed - was broken)")
    print("  • Looser trend/vol filters")
    print("  • Regime filter: stocks < 40th percentile")
    print("  • Fixed stocks T+1 lag handling")

    # ========== 1. LOAD PRICE DATA ==========
    print("\n[1/6] Loading price data...")
    df_price = load_canonical_csv(args.csv_price, ["date", "price"])
    df_price["ret"] = df_price["price"].pct_change()
    print(f"  ✓ Loaded {len(df_price)} price observations")
    print(f"  ✓ Date range: {df_price['date'].min()} to {df_price['date'].max()}")

    # ========== 2. LOAD REGIME DATA ==========
    print("\n[2/6] Loading regime data...")

    # Stocks (with T+1 lag awareness)
    if args.csv_stocks:
        df_stocks = load_canonical_csv(args.csv_stocks, ["date", "stocks"])
        stocks = df_stocks.set_index("date")["stocks"]
        print(f"  ✓ Loaded {len(stocks)} stocks observations")
        print(f"  ✓ Note: Stocks have T+1 publication lag (built into data)")
    else:
        stocks = None
        print("  ⚠ Stocks data not provided (regime filter disabled)")

    # Implied vol
    if args.csv_iv:
        df_iv = load_canonical_csv(args.csv_iv, ["date", "iv"])
        iv_1mo = df_iv.set_index("date")["iv"]
        print(f"  ✓ Loaded {len(iv_1mo)} IV observations")
    else:
        iv_1mo = None
        print("  ⚠ IV data not provided (safety filter partially disabled)")

    # Curve spread
    if args.csv_fut_3mo and args.csv_fut_12mo:
        df_fut_3mo = load_canonical_csv(args.csv_fut_3mo, ["date", "price"])
        df_fut_12mo = load_canonical_csv(args.csv_fut_12mo, ["date", "price"])

        df_curve = df_fut_3mo.merge(df_fut_12mo, on="date", suffixes=("_3mo", "_12mo"))
        df_curve["spread"] = df_curve["price_3mo"] - df_curve["price_12mo"]
        df_curve["spread_pct"] = (df_curve["spread"] / df_curve["price_12mo"]) * 100

        curve_spread_pct = df_curve.set_index("date")["spread_pct"]
        print(f"  ✓ Loaded {len(curve_spread_pct)} curve observations")
    else:
        curve_spread_pct = None
        print("  ⚠ Curve data not provided (safety filter partially disabled)")

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
    print(
        f"  ✓ Regime filter: {'Enabled' if signal_params['regime']['use_regime_filter'] else 'Disabled'}"
    )
    print(f"  ✓ Longs only: {signal_params['directional']['longs_only']}")

    # ========== 4. GENERATE SIGNAL ==========
    print("\n[4/6] Generating HookCore v4.0 signal...")

    pos_raw = generate_hookcore_v4_signal(
        df=df_price,
        bb_lookback=signal_params["bollinger"]["lookback_days"],
        bb_sigma=signal_params["bollinger"]["sigma_multiplier"],
        bb_shift=signal_params["bollinger"]["shift_bars"],
        stocks=stocks,
        iv_1mo=iv_1mo,
        curve_spread_pct=curve_spread_pct,
        stocks_tight_threshold=signal_params["regime"]["stocks_tight_threshold"],
        hold_days=signal_params["holding"]["hold_days_trading"],
        trend_lookback=signal_params["filters"]["trend_lookback"],
        trend_thresh=signal_params["filters"]["trend_thresh"],
        vol_lookback=signal_params["filters"]["vol_lookback"],
        vol_thresh=signal_params["filters"]["vol_thresh"],
        autocorr_lookback=signal_params["filters"]["autocorr_lookback"],
        autocorr_thresh=signal_params["filters"]["autocorr_thresh"],
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
    print("BUILD COMPLETE - HOOKCORE V4.0")
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
    print(f"\n📊 vs V4 Targets:")
    target_sharpe = cfg["expected_improvements"]["v4_0_target_sharpe"]
    target_turnover = cfg["expected_improvements"]["v4_0_target_turnover"]

    sharpe_status = "✅" if metrics["sharpe"] >= target_sharpe * 0.9 else "⚠️"
    turnover_status = "✅" if turnover <= target_turnover * 1.1 else "⚠️"

    print(
        f"  Sharpe: {metrics['sharpe']:.2f} vs {target_sharpe:.2f} target {sharpe_status}"
    )
    print(
        f"  Turnover: {turnover:.1f}x vs {target_turnover:.1f}x target {turnover_status}"
    )

    print(f"\nOutputs written to: {outdir}")
    print("\nNext: Run validation")
    print(f"  python /mnt/project/validate_outputs.py --outdir {outdir}")
    print()


if __name__ == "__main__":
    main()
