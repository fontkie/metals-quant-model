# src/cli/build_trendimpulse_v5.py
"""
TrendImpulse v5 Build Script - COMPLETE 4-LAYER ARCHITECTURE
------------------------------------------------------------
Quality momentum with regime specialization for copper markets.

**ARCHITECTURE (FULLY IMPLEMENTED):**
Layer 1: Signal Generation (pure strategy logic)
Layer 2: Vol Targeting (closed-loop EWMA targeting)
Layer 3: Portfolio Blending (single sleeve - future: regime weights)
Layer 4: Execution & Costs (clean implementation - costs once on net position)

Implementation:
- Layer 1: generate_trendimpulse_signal() - pure signal with regime scaling
- Layer 2: apply_vol_targeting() - EWMA-based targeting
- Layer 3: Single sleeve for now (future: regime-based blending)
- Layer 4: execute_single_sleeve() - costs and PnL

Expected Performance:
  - Gross Sharpe: ~0.48 (unconditional)
  - Net Sharpe: ~0.42 @ 3bps (institutional costs)
  - Realized Vol: ~10% (via closed-loop targeting)
  - Turnover: ~630x (high but profitable)
  - Activity: ~90% (mostly in market)
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml
import numpy as np

# Import all layers
sys.path.append(str(Path(__file__).parent.parent.parent))
from src.signals.trendimpulse_v5 import generate_trendimpulse_signal
from src.core.vol_targeting import apply_vol_targeting, get_vol_diagnostics, classify_strategy_type
from src.core.execution import execute_single_sleeve


def main():
    ap = argparse.ArgumentParser(
        description="Build TrendImpulse v5 (Copper) - 4-Layer Architecture"
    )
    ap.add_argument("--csv", required=True, help="Path to canonical CSV")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--config", required=True, help="Path to YAML config")
    args = ap.parse_args()

    # ========== 1. LOAD CANONICAL CSV ==========
    print(f"[TrendImpulse v5] Loading canonical CSV: {args.csv}")
    df = pd.read_csv(args.csv, parse_dates=["date"])

    # Validate schema
    assert (
        "date" in df.columns and "price" in df.columns
    ), "Canonical CSV must have lowercase 'date' and 'price' columns"

    print(
        f"[TrendImpulse v5] Loaded {len(df)} rows from {df['date'].min()} to {df['date'].max()}"
    )

    # ========== 2. LOAD YAML CONFIG ==========
    print(f"[TrendImpulse v5] Loading config: {args.config}")
    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f)

    # Validate required blocks
    assert "policy" in cfg, "Config must have 'policy' block"
    assert "signal" in cfg, "Config must have 'signal' block"

    # ========== 3. LAYER 1: GENERATE SIGNAL (Pure Strategy Logic) ==========
    print(f"\n{'='*70}")
    print("LAYER 1: Signal Generation (Pure Strategy Logic)")
    print(f"{'='*70}")
    
    signal_cfg = cfg.get("signal", {})

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

    # Diagnostic: Check raw signal
    pos_raw_stats = {
        "mean": df["pos_raw"].mean(),
        "mean_abs": df["pos_raw"].abs().mean(),
        "std": df["pos_raw"].std(),
        "min": df["pos_raw"].min(),
        "max": df["pos_raw"].max(),
        "pct_nonzero": (df["pos_raw"].abs() > 0.01).mean() * 100,
        "pct_long": (df["pos_raw"] > 0.01).mean() * 100,
        "pct_short": (df["pos_raw"] < -0.01).mean() * 100,
    }

    print(f"Raw Signal Stats (before vol targeting):")
    print(f"  Mean:          {pos_raw_stats['mean']:+.4f}")
    print(f"  Mean |pos|:    {pos_raw_stats['mean_abs']:.4f}")
    print(f"  Range:         [{pos_raw_stats['min']:+.4f}, {pos_raw_stats['max']:+.4f}]")
    print(f"  % Active:      {pos_raw_stats['pct_nonzero']:.1f}%")
    print(f"  % Long:        {pos_raw_stats['pct_long']:.1f}%")
    print(f"  % Short:       {pos_raw_stats['pct_short']:.1f}%")

    # ========== 4. LAYER 2: VOL TARGETING ==========
    print(f"\n{'='*70}")
    print("LAYER 2: Volatility Targeting (Closed-Loop)")
    print(f"{'='*70}")
    
    # Calculate returns for vol targeting
    df["ret"] = df["price"].pct_change()
    
    # Classify strategy type (always-on vs sparse)
    strategy_type = classify_strategy_type(df["pos_raw"])
    print(f"Strategy Type: {strategy_type}")
    
    # Get vol targeting config
    target_vol = cfg["policy"]["sizing"].get("ann_target", 0.10)
    print(f"Target Vol: {target_vol:.1%}")
    
    # Apply vol targeting
    df["pos_vol_targeted"] = apply_vol_targeting(
        positions=df["pos_raw"],
        underlying_returns=df["ret"],
        target_vol=target_vol,
        strategy_type=strategy_type,
    )
    
    # Diagnostic: Check vol-targeted positions
    pos_targeted_stats = {
        "mean": df["pos_vol_targeted"].mean(),
        "mean_abs": df["pos_vol_targeted"].abs().mean(),
        "std": df["pos_vol_targeted"].std(),
        "min": df["pos_vol_targeted"].min(),
        "max": df["pos_vol_targeted"].max(),
    }
    
    print(f"\nVol-Targeted Positions:")
    print(f"  Mean:          {pos_targeted_stats['mean']:+.4f}")
    print(f"  Mean |pos|:    {pos_targeted_stats['mean_abs']:.4f}")
    print(f"  Range:         [{pos_targeted_stats['min']:+.4f}, {pos_targeted_stats['max']:+.4f}]")
    
    # Get diagnostics
    vol_diag = get_vol_diagnostics(
        positions=df["pos_raw"],
        underlying_returns=df["ret"],
        target_vol=target_vol,
        strategy_type=strategy_type,
    )
    
    # Calculate realized vol
    strategy_returns = df["pos_vol_targeted"].shift(1) * df["ret"]
    realized_vol = strategy_returns.iloc[63:].std() * np.sqrt(252)
    
    print(f"\nRealized Volatility:")
    print(f"  Post-warmup (63d+): {realized_vol:.2%}")
    print(f"  Target: {target_vol:.1%}")
    print(f"  Delta: {(realized_vol - target_vol):.2%}")
    
    if abs(realized_vol - target_vol) < 0.01:
        print(f"  ✅ Within ±1% of target!")
    elif abs(realized_vol - target_vol) < 0.02:
        print(f"  ✓ Within ±2% of target (acceptable)")
    else:
        print(f"  ⚠️ Outside ±2% of target")

    # ========== 5. LAYER 4: EXECUTION & COSTS ==========
    print(f"\n{'='*70}")
    print("LAYER 4: Execution & Costs")
    print(f"{'='*70}")
    print("Applying transaction costs and calculating PnL...")
    
    # Get cost from config
    cost_bps = cfg["policy"]["costs"].get("one_way_bps_default", 3.0)
    
    # Execute with costs
    result, metrics, turnover_metrics, validation = execute_single_sleeve(
        positions=df["pos_vol_targeted"],
        returns=df["ret"],
        cost_bps=cost_bps,
        expected_vol=target_vol,
    )
    
    # Validation checks
    print(f"\nExecution Validation:")
    for check, passed in validation.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {check}: {passed}")
    
    # Turnover metrics
    print(f"\nTurnover Metrics:")
    print(f"  Annual Turnover:    {turnover_metrics['annual_turnover']:.2f}x")
    print(f"  Avg Holding Period: {turnover_metrics['avg_holding_days']:.0f} days")
    print(f"  Annual Cost:        {turnover_metrics['annual_cost']:.4f}")
    print(f"  Cost % of Gross:    {turnover_metrics['cost_as_pct_gross']:.2%}")
    
    # Calculate gross Sharpe (without costs)
    gross_returns = result["pnl_gross"]
    gross_sharpe = gross_returns.mean() / gross_returns.std() * np.sqrt(252)
    
    print(f"\nGross vs Net Performance:")
    print(f"  Gross Sharpe: {gross_sharpe:+.2f}")
    print(f"  Net Sharpe:   {metrics['sharpe']:+.2f}")
    print(f"  Cost Impact:  {(gross_sharpe - metrics['sharpe']):.2f} Sharpe points")
    
    # Merge with original df for complete output
    result = df[["date", "price", "ret"]].merge(result, left_index=True, right_index=True, how="left")

    # ========== 6. SAVE OUTPUTS ==========
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Daily series
    daily_path = outdir / "daily_series.csv"
    result.to_csv(daily_path, index=False)
    print(f"\n[TrendImpulse v5] Saved daily series: {daily_path}")

    # Summary metrics
    all_metrics = {
        **metrics,
        "gross_sharpe": float(gross_sharpe),
        "turnover": turnover_metrics,
        "vol_targeting": {
            "realized_vol": realized_vol,
            "target_vol": target_vol,
            "vol_delta": realized_vol - target_vol,
            "strategy_type": strategy_type,
        }
    }
    
    metrics_path = outdir / "summary_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(all_metrics, f, indent=2)
    print(f"[TrendImpulse v5] Saved metrics: {metrics_path}")

    # Vol targeting diagnostics
    vol_diag_path = outdir / "vol_diagnostics.csv"
    vol_diag.to_csv(vol_diag_path)
    print(f"[TrendImpulse v5] Saved vol diagnostics: {vol_diag_path}")

    # Save comprehensive diagnostics
    diagnostics = {
        "signal_stats": {k: float(v) for k, v in pos_raw_stats.items()},
        "targeted_position_stats": {k: float(v) for k, v in pos_targeted_stats.items()},
        "realized_vol": float(realized_vol),
        "target_vol": float(target_vol),
        "vol_delta": float(realized_vol - target_vol),
        "strategy_type": str(strategy_type),
        "gross_sharpe": float(gross_sharpe),
        "metrics": metrics,
        "turnover_metrics": turnover_metrics,
        "execution_validation": validation,
    }
    diag_path = outdir / "diagnostics.json"
    with open(diag_path, "w") as f:
        json.dump(diagnostics, f, indent=2)
    print(f"[TrendImpulse v5] Saved diagnostics: {diag_path}")

    # ========== 7. PRINT SUMMARY ==========
    print(f"\n{'='*70}")
    print("TrendImpulse v5 Build Complete - Clean 4-Layer Architecture")
    print(f"{'='*70}")
    
    print(f"\nPerformance Metrics:")
    print(f"  Gross Sharpe:   {gross_sharpe:+.2f}")
    print(f"  Net Sharpe:     {metrics['sharpe']:+.2f}")
    print(f"  Annual Return:  {metrics['annual_return']*100:+.2f}%")
    print(f"  Annual Vol:     {metrics['annual_vol']*100:.2f}%")
    print(f"  Max Drawdown:   {metrics['max_drawdown']*100:.2f}%")
    
    print(f"\nVol Targeting Validation:")
    print(f"  Target Vol:     {target_vol*100:.1f}%")
    print(f"  Realized Vol:   {realized_vol*100:.2f}%")
    print(f"  Delta:          {(realized_vol - target_vol)*100:+.2f}%")
    
    print(f"\nTurnover & Costs:")
    print(f"  Annual Turnover: {turnover_metrics['annual_turnover']:.2f}x")
    print(f"  Avg Holding:     {turnover_metrics['avg_holding_days']:.0f} days")
    print(f"  Cost Impact:     {turnover_metrics['cost_as_pct_gross']:.2%} of gross")
    
    print(f"\nExpected Performance:")
    print(f"  Gross Sharpe:   ~0.48 (unconditional)")
    print(f"  Net Sharpe:     ~0.42 @ 3bps")
    print(f"  Vol:            ~10% (closed-loop targeting)")
    print(f"  Turnover:       ~630x (high but profitable)")
    print(f"  Activity:       ~90% (mostly in market)")

    # Validation
    print(f"\n{'='*70}")
    vol_ok = abs(metrics["annual_vol"] - target_vol) < 0.02
    gross_sharpe_ok = 0.43 <= gross_sharpe <= 0.53
    net_sharpe_ok = 0.37 <= metrics["sharpe"] <= 0.47
    all_checks_pass = all(validation.values())
    
    if vol_ok and gross_sharpe_ok and net_sharpe_ok and all_checks_pass:
        print("✅ SUCCESS: All systems operational!")
        print(f"   Vol: {metrics['annual_vol']*100:.1f}% (target: {target_vol*100:.0f}%)")
        print(f"   Gross Sharpe: {gross_sharpe:.2f} (expected: ~0.48)")
        print(f"   Net Sharpe: {metrics['sharpe']:.2f} (expected: ~0.42)")
        print(f"   All validation checks passed")
    else:
        if not vol_ok:
            print(f"⚠️ Vol targeting issue:")
            print(f"   Realized: {metrics['annual_vol']*100:.1f}%")
            print(f"   Target: {target_vol*100:.0f}%")
            print(f"   Check vol_diagnostics.csv for details")
        if not gross_sharpe_ok:
            print(f"⚠️ Gross Sharpe outside expected range:")
            print(f"   Got: {gross_sharpe:.2f}")
            print(f"   Expected: ~0.48")
        if not net_sharpe_ok:
            print(f"⚠️ Net Sharpe outside expected range:")
            print(f"   Got: {metrics['sharpe']:.2f}")
            print(f"   Expected: ~0.42")
        if not all_checks_pass:
            print(f"⚠️ Some execution validation checks failed:")
            for check, passed in validation.items():
                if not passed:
                    print(f"   ❌ {check}")
    
    print(f"{'='*70}")
    print(f"\nArchitecture Status:")
    print(f"  ✅ Layer 1: Signal Generation (pure logic + regime scaling)")
    print(f"  ✅ Layer 2: Vol Targeting (closed-loop EWMA)")
    print(f"  ⭐ Layer 3: Portfolio Blending (single sleeve for now)")
    print(f"  ✅ Layer 4: Execution & Costs (clean implementation)")
    print(f"{'='*70}")
    print(f"\nOutputs written to: {outdir}")
    print(f"{'='*70}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())