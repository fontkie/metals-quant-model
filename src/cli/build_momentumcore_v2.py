# src/cli/build_momentumcore_v2.py
"""
MomentumCore v2 Build Script - COMPLETE 4-LAYER ARCHITECTURE
------------------------------------------------------------
12-month Time Series Momentum (TSMOM) for copper markets.

**ARCHITECTURE (FULLY IMPLEMENTED):**
Layer 1: Signal Generation (pure strategy logic)
Layer 2: Vol Targeting (closed-loop EWMA targeting)
Layer 3: Portfolio Blending (single sleeve - future: regime weights)
Layer 4: Execution & Costs (clean implementation - costs once on net position)

Implementation:
- Layer 1: generate_momentum_signal() - pure signal
- Layer 2: apply_vol_targeting() - EWMA-based targeting
- Layer 3: Single sleeve for now (future: regime-based blending)
- Layer 4: execute_single_sleeve() - costs and PnL

Expected Performance:
  - Sharpe: ~0.40-0.45 (unconditional)
  - Realized Vol: ~10% (via closed-loop targeting)
  - Max DD: ~-28% (true risk profile)
  - 12-month momentum signal
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
from src.signals.momentumcore_v2 import generate_momentum_signal
from src.core.vol_targeting import apply_vol_targeting, get_vol_diagnostics, classify_strategy_type
from src.core.execution import execute_single_sleeve


def make_json_serializable(obj):
    """
    Convert numpy types to native Python types for JSON serialization.
    Handles nested dictionaries and lists recursively.
    """
    if isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, (np.bool_, np.integer)):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (bool, int, float, str, type(None))):
        return obj
    else:
        return str(obj)


def main():
    ap = argparse.ArgumentParser(
        description="Build MomentumCore v2 (Copper) - 4-Layer Architecture"
    )
    ap.add_argument("--csv", required=True, help="Path to canonical CSV")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--config", required=True, help="Path to YAML config")
    args = ap.parse_args()

    # ========== 1. LOAD CANONICAL CSV ==========
    print(f"[MomentumCore v2] Loading canonical CSV: {args.csv}")
    df = pd.read_csv(args.csv, parse_dates=["date"])

    # Validate schema
    assert (
        "date" in df.columns and "price" in df.columns
    ), "Canonical CSV must have lowercase 'date' and 'price' columns"

    print(
        f"[MomentumCore v2] Loaded {len(df)} rows from {df['date'].min()} to {df['date'].max()}"
    )

    # ========== 2. LOAD YAML CONFIG ==========
    print(f"[MomentumCore v2] Loading config: {args.config}")
    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f)

    # Validate required blocks
    assert "policy" in cfg, "Config must have 'policy' block"
    assert "signal" in cfg, "Config must have 'signal' block"

    # ========== 3. LAYER 1: GENERATE SIGNAL (Pure Strategy Logic) ==========
    print(f"\n{'='*70}")
    print("LAYER 1: Signal Generation (Pure Strategy Logic)")
    print(f"{'='*70}")
    
    signal_cfg = cfg.get("signal", {}).get("momentum", {})

    df["pos_raw"] = generate_momentum_signal(
        df,
        lookback_days=signal_cfg.get("lookback_days", 252),
    )

    # Diagnostic: Check raw signal
    pos_raw_stats = {
        "mean": df["pos_raw"].mean(),
        "mean_abs": df["pos_raw"].abs().mean(),
        "std": df["pos_raw"].std(),
        "min": df["pos_raw"].min(),
        "max": df["pos_raw"].max(),
        "pct_nonzero": (df["pos_raw"].abs() > 0.01).mean() * 100,
    }

    print(f"Raw Signal Stats (before vol targeting):")
    print(f"  Mean:          {pos_raw_stats['mean']:+.4f}")
    print(f"  Mean |pos|:    {pos_raw_stats['mean_abs']:.4f}")
    print(f"  Range:         [{pos_raw_stats['min']:+.4f}, {pos_raw_stats['max']:+.4f}]")
    print(f"  % Active:      {pos_raw_stats['pct_nonzero']:.1f}%")

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
        print(f"  [OK] Within +/-1% of target!")
    elif abs(realized_vol - target_vol) < 0.02:
        print(f"  [OK] Within +/-2% of target (acceptable)")
    else:
        print(f"  [WARNING] Outside +/-2% of target")

    # ========== 5. LAYER 3: PORTFOLIO BLENDING (Single Sleeve) ==========
    print(f"\n{'='*70}")
    print("LAYER 3: Portfolio Blending (Single Sleeve)")
    print(f"{'='*70}")
    print("Using 100% allocation (future: regime-based blending)")
    
    # For now, just pass through the vol-targeted position
    df["pos_final"] = df["pos_vol_targeted"]

    # ========== 6. LAYER 4: EXECUTION & COSTS ==========
    print(f"\n{'='*70}")
    print("LAYER 4: Execution & Costs")
    print(f"{'='*70}")
    print("Applying transaction costs and calculating PnL...")
    
    # Get cost from config
    cost_bps = cfg["policy"]["costs"].get("one_way_bps_default", 3.0)
    
    # Execute with costs - CORRECT PARAMETERS (Series, not DataFrame)
    result, metrics, turnover_metrics, validation = execute_single_sleeve(
        positions=df["pos_final"],
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
    
    # Merge with original df for complete output
    result = df[["date", "price", "ret"]].merge(result, left_index=True, right_index=True, how="left")

    # ========== 7. SAVE OUTPUTS ==========
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Daily series
    daily_path = outdir / "daily_series.csv"
    result.to_csv(daily_path, index=False)
    print(f"\n[MomentumCore v2] Saved daily series: {daily_path}")

    # Summary metrics
    all_metrics = {
        **metrics,
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
        # Convert numpy types to JSON-serializable types
        json.dump(make_json_serializable(all_metrics), f, indent=2)
    print(f"[MomentumCore v2] Saved metrics: {metrics_path}")

    # Vol targeting diagnostics
    vol_diag_path = outdir / "vol_diagnostics.csv"
    vol_diag.to_csv(vol_diag_path)
    print(f"[MomentumCore v2] Saved vol diagnostics: {vol_diag_path}")

    # Save comprehensive diagnostics
    diagnostics = {
        "signal_stats": {k: float(v) for k, v in pos_raw_stats.items()},
        "targeted_position_stats": {k: float(v) for k, v in pos_targeted_stats.items()},
        "realized_vol": float(realized_vol),
        "target_vol": float(target_vol),
        "vol_delta": float(realized_vol - target_vol),
        "strategy_type": str(strategy_type),
        "metrics": metrics,
        "turnover_metrics": turnover_metrics,
        "execution_validation": validation,
    }
    diag_path = outdir / "diagnostics.json"
    with open(diag_path, "w") as f:
        # Convert numpy types to JSON-serializable types
        json.dump(make_json_serializable(diagnostics), f, indent=2)
    print(f"[MomentumCore v2] Saved diagnostics: {diag_path}")

    # ========== 8. PRINT SUMMARY ==========
    print(f"\n{'='*70}")
    print("MomentumCore v2 Build Complete - Clean 4-Layer Architecture")
    print(f"{'='*70}")
    
    print(f"\nPerformance Metrics:")
    print(f"  Annual Return:  {metrics['annual_return']*100:+.2f}%")
    print(f"  Annual Vol:     {metrics['annual_vol']*100:.2f}%")
    print(f"  Sharpe Ratio:   {metrics['sharpe']:+.2f}")
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
    print(f"  Sharpe:         ~0.40-0.45 (unconditional)")
    print(f"  Vol:            ~10% (closed-loop targeting)")
    print(f"  Max DD:         ~-28% (true risk)")
    print(f"  Signal:         12-month TSMOM")

    # Validation
    print(f"\n{'='*70}")
    vol_ok = abs(metrics["annual_vol"] - target_vol) < 0.02
    sharpe_ok = 0.35 <= metrics["sharpe"] <= 0.50
    all_checks_pass = all(validation.values())
    
    if vol_ok and sharpe_ok and all_checks_pass:
        print("✅ SUCCESS: All systems operational!")
        print(f"   Vol: {metrics['annual_vol']*100:.1f}% (target: {target_vol*100:.0f}%)")
        print(f"   Sharpe: {metrics['sharpe']:.2f} (expected: 0.40-0.45)")
        print(f"   All validation checks passed")
    else:
        if not vol_ok:
            print(f"⚠️ Vol targeting issue:")
            print(f"   Realized: {metrics['annual_vol']*100:.1f}%")
            print(f"   Target: {target_vol*100:.0f}%")
            print(f"   Check vol_diagnostics.csv for details")
        if not sharpe_ok:
            print(f"⚠️ Sharpe outside expected range:")
            print(f"   Got: {metrics['sharpe']:.2f}")
            print(f"   Expected: 0.40-0.45")
        if not all_checks_pass:
            print(f"⚠️ Some execution validation checks failed:")
            for check, passed in validation.items():
                if not passed:
                    print(f"   ❌ {check}")
    
    print(f"{'='*70}")
    print(f"\nArchitecture Status:")
    print(f"  ✅ Layer 1: Signal Generation (pure logic)")
    print(f"  ✅ Layer 2: Vol Targeting (closed-loop EWMA)")
    print(f"  ⭐️  Layer 3: Portfolio Blending (single sleeve for now)")
    print(f"  ✅ Layer 4: Execution & Costs (clean implementation)")
    print(f"{'='*70}")
    print(f"\nOutputs written to: {outdir}")
    print(f"{'='*70}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())