#!/usr/bin/env python3
"""
Build Adaptive Portfolio - CLI Wrapper
======================================

Orchestrates adaptive portfolio construction:
  1. Load portfolio.yaml configuration
  2. Load sleeve CSVs
  3. Run adaptive backtest
  4. Generate outputs
  5. Compare to static blend (optional)

Usage:
    python build_adaptive_portfolio.py \\
        --config Config/Copper/portfolio.yaml \\
        --outdir outputs/Copper/AdaptivePortfolio \\
        --compare-static

Author: Claude (ex-Renaissance)
Date: November 4, 2025
Version: 1.0
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.portfolio import (
    AdaptivePortfolio,
    load_portfolio_config,
    load_sleeves_from_config,
)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Build adaptive portfolio with regime-dependent blending"
    )

    parser.add_argument(
        "--config", required=True, help="Path to portfolio.yaml configuration file"
    )

    parser.add_argument("--outdir", required=True, help="Output directory for results")

    parser.add_argument(
        "--compare-static",
        action="store_true",
        help="Compare to static blend benchmark",
    )

    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Print header
    print("\n" + "=" * 80)
    print("ADAPTIVE PORTFOLIO BUILDER")
    print("=" * 80)
    print(f"Config: {args.config}")
    print(f"Output: {args.outdir}")

    try:
        # Step 1: Load configuration
        print("\n📋 Loading configuration...")
        config = load_portfolio_config(args.config)

        commodity = config.get("io", {}).get("commodity", "Unknown")
        portfolio_name = config.get("io", {}).get("portfolio_name", "Unknown")

        print(f"  Commodity: {commodity}")
        print(f"  Portfolio: {portfolio_name}")

        # Step 2: Load sleeves
        print("\n📂 Loading sleeves...")
        sleeves = load_sleeves_from_config(config)

        if len(sleeves) == 0:
            print("  ❌ No sleeves loaded!")
            return 1

        print(f"  ✓ Loaded {len(sleeves)} sleeve(s)")

        # Step 3: Initialize portfolio
        print("\n🔧 Initializing adaptive portfolio...")
        portfolio = AdaptivePortfolio(sleeves, config)

        # Step 4: Run backtest
        print("\n🚀 Running backtest...")
        daily_series, metrics, regime_log = portfolio.backtest_adaptive_strategy()

        # Step 5: Create output directory
        print(f"\n💾 Saving outputs to {args.outdir}...")
        output_dir = Path(args.outdir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save daily series
        daily_series.to_csv(output_dir / "daily_series.csv", index=False)
        print(f"  ✓ Saved daily_series.csv")

        # Save regime log
        regime_log.to_csv(output_dir / "regime_log.csv", index=False)
        print(f"  ✓ Saved regime_log.csv")

        # Save metrics
        with open(output_dir / "summary_metrics.json", "w") as f:
            # Convert numpy types to Python types for JSON
            metrics_json = {
                k: float(v) if hasattr(v, "item") else v for k, v in metrics.items()
            }
            json.dump(metrics_json, f, indent=2)
        print(f"  ✓ Saved summary_metrics.json")

        # Step 6: Compare to static (if requested)
        if args.compare_static:
            print("\n📊 Comparing to static blend...")

            # Get default weights
            static_weights = {}
            for sleeve_name, sleeve_cfg in config.get("sleeves", {}).items():
                if sleeve_cfg.get("enabled", True):
                    static_weights[sleeve_name] = sleeve_cfg.get("default_weight", 0.0)

            # Normalize
            total = sum(static_weights.values())
            static_weights = {k: v / total for k, v in static_weights.items()}

            print(f"  Static weights: {static_weights}")

            # Compare
            comparison = portfolio.compare_static_vs_adaptive(static_weights)

            # Save comparison
            with open(output_dir / "comparison_report.json", "w") as f:
                comparison_json = {
                    k: float(v) if hasattr(v, "item") else v
                    for k, v in comparison.items()
                    if k not in ["static_metrics", "adaptive_metrics"]
                }
                json.dump(comparison_json, f, indent=2)
            print(f"  ✓ Saved comparison_report.json")

        # Print final summary
        print("\n" + "=" * 80)
        print("BUILD COMPLETE")
        print("=" * 80)
        print(f"✅ Portfolio Sharpe: {metrics['sharpe']:.3f}")
        print(f"✅ Annual Return:   {metrics['annual_return']*100:.2f}%")
        print(f"✅ Annual Vol:      {metrics['annual_vol']*100:.2f}%")
        print(f"✅ Max Drawdown:    {metrics['max_drawdown']*100:.2f}%")
        print(f"✅ Observations:    {metrics['obs']:,}")

        if args.compare_static:
            improvement_pct = comparison["improvement_pct"]
            print(f"✅ Improvement:     +{improvement_pct:.1f}% vs static")

        print("\nOutputs saved to:")
        print(f"  {output_dir.absolute()}/")
        print("=" * 80)

        return 0

    except Exception as e:
        print(f"\n❌ ERROR: {e}")

        if args.verbose:
            import traceback

            traceback.print_exc()

        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
