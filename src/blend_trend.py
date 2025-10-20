# src/blend_trend.py
import argparse, os, math
import pandas as pd

from utils.policy import load_execution_policy, policy_banner, warn_if_mismatch

TARGET_VOL = 0.10


def ann_vol(x):
    return float(x.std() * (252**0.5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", required=True, help="Path to core 20/60/120 CSV")
    ap.add_argument("--slow", required=True, help="Path to slow 10/50/200 CSV")
    ap.add_argument("--w_core", type=float, default=0.7)
    ap.add_argument("--w_slow", type=float, default=0.3)
    ap.add_argument("--out", default="outputs/copper/trend/blend/daily_series.csv")
    args = ap.parse_args()

    core = pd.read_csv(args.core, parse_dates=["date"])
    slow = pd.read_csv(args.slow, parse_dates=["date"])

    # --- Policy header check ---
    policy = load_execution_policy(
        args.__dict__.get("schema_path", "Config/schema.yaml")
    )
    print(policy_banner(policy, sleeve_name="TrendCore-Cu-v1-Tclose"))
    # Our script uses: exec Mon/Wed, T-close sizing, vol_info=T, cap=2.5, costs=1.5 bps
    warnings = warn_if_mismatch(
        policy,
        exec_weekdays=(0, 2),
        fill_timing="close_T",
        vol_info="T",
        leverage_cap=args.lev_cap,
        one_way_bps=args.bps,
    )
    for w in warnings:
        print(w)

    # Align on date
    df = core.merge(
        slow[["date", "pnl", "cum_pnl"]].rename(
            columns={"pnl": "pnl_slow", "cum_pnl": "cum_slow"}
        ),
        on="date",
        how="inner",
    )
    df.rename(columns={"pnl": "pnl_core", "cum_pnl": "cum_core"}, inplace=True)

    # Risk-equalize (match annual vol of components, then weight)
    v_core = ann_vol(df["pnl_core"])
    v_slow = ann_vol(df["pnl_slow"])
    if v_core == 0 or v_slow == 0:
        raise SystemExit("Zero vol in one component; check inputs.")
    core_norm = df["pnl_core"] * (1.0 / v_core)
    slow_norm = df["pnl_slow"] * (1.0 / v_slow)

    blend_unit = args.w_core * core_norm + args.w_slow * slow_norm

    # Scale the blend to 10% target vol
    v_unit = ann_vol(blend_unit)
    scale = (TARGET_VOL / v_unit) if v_unit > 0 else 0.0
    df["pnl"] = blend_unit * scale
    df["cum_pnl"] = df["pnl"].cumsum()

    # Minimal extras for consistency (no positions in a pure blend)
    df["position"] = 0.0
    df["turnover"] = 0.0

    # Write outputs
    out_dir = os.path.dirname(args.out)
    os.makedirs(out_dir, exist_ok=True)
    df_out = df[["date", "pnl", "cum_pnl", "position", "turnover"]].copy()
    df_out.to_csv(args.out, index=False)

    # Summary metrics
    def ann_stats(p):
        ann_pnl = float(p.mean() * 252)
        ann_vol = float(p.std() * (252**0.5))
        sr = ann_pnl / (ann_vol + 1e-12)
        return ann_pnl, ann_vol, sr

    all_stats = ann_stats(df_out["pnl"])
    metrics = pd.DataFrame(
        [
            {
                "Sleeve": "TrendCore 70/30 blend (2060120/1050200)",
                "Sharpe_ALL": all_stats[2],
                "Vol_ALL": all_stats[1],
            }
        ]
    )
    metrics.to_csv(os.path.join(out_dir, "summary_metrics.csv"), index=False)
    print(f"Wrote {args.out} and summary_metrics.csv")


if __name__ == "__main__":
    main()
