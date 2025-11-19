import argparse
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import yaml

TRADING_DAYS = 252


# ============= helpers =============
def ann_vol(x: pd.Series) -> float:
    return float(x.std(ddof=0) * np.sqrt(TRADING_DAYS))


def sharpe(x: pd.Series) -> float:
    v = ann_vol(x)
    return float(x.mean() * TRADING_DAYS / v) if v > 0 else np.nan


def max_drawdown(eq: pd.Series) -> float:
    peak = eq.cummax()
    dd = eq / peak - 1.0
    return float(dd.min())


def hit_rate(x: pd.Series) -> float:
    n = (x > 0).sum()
    d = x.notna().sum()
    return float(n / d) if d else np.nan


def turnover_series(pos: pd.Series) -> pd.Series:
    return pos.diff().abs().fillna(0.0)


def read_yaml(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def read_table_auto(
    path: str, date_col_candidates=("dt", "date", "Date", "datetime", "DT")
) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing file: {p}")
    if p.suffix.lower() in (".csv", ".txt"):
        df = pd.read_csv(p)
    elif p.suffix.lower() in (".xlsx", ".xls"):
        try:
            import openpyxl  # noqa: F401
        except Exception:
            pass
        df = pd.read_excel(p)
    else:
        raise ValueError(f"Unsupported file extension for {p.name}")
    date_col = None
    for c in date_col_candidates:
        if c in df.columns:
            date_col = c
            break
    if date_col is None:
        raise ValueError(
            f"Could not find a date column in {p}. Columns: {list(df.columns)}"
        )
    df["dt"] = pd.to_datetime(df[date_col])
    return df.sort_values("dt").reset_index(drop=True)


def read_price_from_excel(
    xlsx_path: str, sheet: str | None, date_col_idx: int, px_col_idx: int
) -> pd.DataFrame:
    """
    Read price from Excel by zero-based column indices.
    date_col_idx: 0 for column A, 3 for column D, etc.
    """
    try:
        import openpyxl  # ensure engine for .xlsx
    except Exception:
        pass
    sheet_name = 0 if sheet is None else sheet
    df = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=0)
    if isinstance(df, dict):
        df = next(iter(df.values()))
    df = df.iloc[:, [date_col_idx, px_col_idx]].copy()
    df.columns = ["dt", "copper_3m"]
    df["dt"] = pd.to_datetime(df["dt"])
    df = df.sort_values("dt").dropna(subset=["dt"]).reset_index(drop=True)
    return df


def inverse_vol_weights_n(ret_df: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """
    Rolling inverse-vol weights for N sleeves.
    ret_df: columns are per-sleeve returns (aligned to 'dt' outside).
    """
    roll_std = ret_df.rolling(lookback).std(ddof=0)
    inv = 1.0 / roll_std.replace(0.0, np.nan)
    w = inv.div(inv.sum(axis=1), axis=0)
    return w


def vol_target_tplus1(
    ret_raw: pd.Series, target_ann_vol: float, lookback_days: int, cap: float
) -> pd.DataFrame:
    rv_daily = ret_raw.rolling(lookback_days).std(ddof=0)
    rv_ann = rv_daily * np.sqrt(TRADING_DAYS)
    lev = (target_ann_vol / rv_ann).clip(upper=cap)
    lev_t1 = lev.shift(1)  # T+1 execution
    ret_scaled = ret_raw * lev_t1
    return pd.DataFrame({"lev": lev_t1, "ret_scaled": ret_scaled})


# ============= main =============
def main():
    ap = argparse.ArgumentParser(
        description="Build Copper composite daily series (PM view) incl. TrendCore."
    )
    ap.add_argument(
        "--config",
        required=True,
        help="Path to docs/Copper/combined/composite_config.yaml",
    )
    ap.add_argument(
        "--weight_lookback",
        type=int,
        default=63,
        help="Lookback for inverse-vol weights (default 63)",
    )
    # Price join options (can override)
    ap.add_argument(
        "--price_xlsx",
        type=str,
        default=r"C:\Code\Metals\Data\copper\pricing\pricing_values.xlsx",
    )
    ap.add_argument(
        "--price_sheet",
        type=str,
        default=None,
        help="Sheet name if needed (None = first sheet)",
    )
    ap.add_argument(
        "--price_date_col_idx", type=int, default=0, help="0-based index (A=0)"
    )
    ap.add_argument(
        "--price_px_col_idx", type=int, default=3, help="0-based index (D=3)"
    )
    ap.add_argument(
        "--no_price",
        action="store_true",
        help="Skip joining price even if Excel path exists",
    )
    args = ap.parse_args()

    # ---------- Load configs ----------
    cfg = read_yaml(args.config)
    global_cfg = (
        read_yaml("config/global.yaml") if Path("config/global.yaml").exists() else {}
    )

    ass = cfg.get("assumptions", {})
    vol_cfg = ass.get("vol_target") or ass.get("vol") or {}
    g_vol = (global_cfg.get("vol_target") if isinstance(global_cfg, dict) else {}) or {}

    target_vol = float(vol_cfg.get("ann_pct", g_vol.get("ann_pct", 10.0))) / 100.0
    lookback_vol = int(vol_cfg.get("lookback_days", g_vol.get("lookback_days", 21)))
    cap = float(vol_cfg.get("leverage_cap", g_vol.get("leverage_cap", 3.0)))
    costs_bps = float(
        ass.get("cost_bps_per_turnover", global_cfg.get("cost_bps_per_turnover", 1.5))
    )

    exec_cfg = cfg.get("execution", {})
    rebalance_days = set(
        exec_cfg.get("rebalance_days", ["Mon", "Wed"])
    )  # e.g., ["Mon","Wed"]
    t_plus = int(exec_cfg.get("t_plus", 1))

    reporting = cfg.get("reporting", {}).get("write", {})
    out_combo = Path(
        reporting.get("combo_path", "outputs/copper/composite/daily_series.csv")
    )
    out_summary = Path(
        reporting.get("summary_path", "outputs/copper/composite/summary_metrics.csv")
    )
    out_dir = out_combo.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------- Load sleeves (Hook, Stocks, Trend...) ----------
    sleeves_cfg = cfg.get("inputs", {})
    if not sleeves_cfg or not isinstance(sleeves_cfg, dict):
        raise ValueError(
            "Config must have an 'inputs' mapping with one entry per sleeve (hookcore, stockscore, trendcore, ...)."
        )

    sleeves = []
    for name, scfg in sleeves_cfg.items():
        path = scfg.get("path")
        if not path:
            raise ValueError(f"Missing path for inputs.{name}")
        raw = read_table_auto(path)

        fields = scfg.get("fields", {})
        # Hook can have weekly/biweekly streams; others likely just 'ret' and 'pos'
        use_stream = str(scfg.get("use_stream", "")).lower()
        if name.lower().startswith("hook") and use_stream in ("weekly", "biweekly"):
            ret_col = fields.get(f"ret_{use_stream}")
            pos_col = fields.get(f"pos_{use_stream}")
        else:
            ret_col = fields.get("ret")
            pos_col = fields.get("pos")

        if not ret_col or not pos_col:
            raise ValueError(
                f"{name}: map 'fields.ret' and 'fields.pos' (or ret_weekly/biweekly). Provided: {fields}"
            )

        missing = [c for c in [ret_col, pos_col] if c not in raw.columns]
        if missing:
            raise ValueError(
                f"{name}: missing columns {missing}. Found: {list(raw.columns)}"
            )

        df = raw.rename(columns={ret_col: f"ret_{name}", pos_col: f"pos_{name}"})[
            ["dt", f"ret_{name}", f"pos_{name}"]
        ]
        sleeves.append((name, df))

    # Align all sleeves on intersection of dates
    base = sleeves[0][1]
    for _, df in sleeves[1:]:
        base = base.merge(df, on="dt", how="inner", validate="one_to_one")
    base = base.sort_values("dt").reset_index(drop=True)

    # ---------- Rolling inverse-vol weights across ALL sleeve returns ----------
    ret_cols = [c for c in base.columns if c.startswith("ret_")]
    pos_cols = [c for c in base.columns if c.startswith("pos_")]
    if len(ret_cols) < 2:
        raise ValueError(
            "Need at least two sleeves (found fewer than 2 return columns)."
        )

    w_rolling = inverse_vol_weights_n(base[ret_cols], lookback=args.weight_lookback)
    w_rolling.columns = [c.replace("ret_", "w_") for c in ret_cols]  # align names

    # Rebalance only on specified weekdays; forward fill T between rebalances
    weekdays = base["dt"].dt.day_name().str[:3]  # "Mon","Tue",...
    is_rebal = weekdays.isin(rebalance_days)
    w_eff = w_rolling.copy()
    w_eff.loc[~is_rebal, :] = np.nan
    w_eff = w_eff.ffill()
    # Normalise to 1.0 row-wise (defensive)
    w_eff = w_eff.div(w_eff.sum(axis=1), axis=0)

    # ---------- Portfolio return & position (unlevered, before composite costs) ----------
    # sum_i w_i * ret_i ;   sum_i w_i * pos_i
    ret_combo_raw = (base[ret_cols].values * w_eff.values).sum(axis=1)
    pos_target = (base[pos_cols].values * w_eff.values).sum(axis=1)

    df = pd.DataFrame(
        {
            "dt": base["dt"],
            **{col: base[col] for col in ret_cols + pos_cols},
            **{col: w_eff[col] for col in w_eff.columns},
            "ret_combo_raw": ret_combo_raw,
            "pos_target": pos_target,
        }
    )

    # ---------- Executed (T+1), composite turnover & costs ----------
    df["pos_exec"] = df["pos_target"].shift(t_plus)
    df["turnover"] = turnover_series(df["pos_exec"])
    df["cost"] = (costs_bps / 10000.0) * df["turnover"]
    df["ret_after_cost"] = df["ret_combo_raw"] - df["cost"].fillna(0.0)

    # ---------- Portfolio vol target (T+1) ----------
    vt = vol_target_tplus1(df["ret_after_cost"], target_vol, lookback_vol, cap)
    df["lev"] = vt["lev"]
    df["ret_combo_net"] = vt["ret_scaled"]

    # ---------- Levered positions, equity, drawdown ----------
    df["pos_target_lev_T"] = df["pos_target"] * df["lev"]
    df["pos_exec_lev_T"] = df["pos_exec"] * df["lev"]
    df["equity_net"] = (1.0 + df["ret_combo_net"].fillna(0.0)).cumprod()
    df["drawdown"] = df["equity_net"] / df["equity_net"].cummax() - 1.0

    # ---------- Optional: join Copper 3M price ----------
    if not args.no_price and Path(args.price_xlsx).exists():
        p = read_price_from_excel(
            args.price_xlsx,
            args.price_sheet,
            args.price_date_col_idx,
            args.price_px_col_idx,
        )
        df = df.merge(p, on="dt", how="left")

    # ---------- Write outputs ----------
    out_dir = out_combo.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # Rich daily series
    daily_cols = ["dt"]
    if "copper_3m" in df.columns:
        daily_cols.append("copper_3m")
    daily_cols += sorted([c for c in df.columns if c.startswith("w_")])
    daily_cols += sorted([c for c in df.columns if c.startswith("pos_")])
    daily_cols += [
        "pos_target",
        "pos_target_lev_T",
        "pos_exec",
        "pos_exec_lev_T",
        "turnover",
        "cost",
        "lev",
        "ret_combo_raw",
        "ret_after_cost",
        "ret_combo_net",
        "equity_net",
        "drawdown",
    ]
    rich_path = out_dir / "daily_series.csv"
    df[daily_cols].to_csv(rich_path, index=False)

    # Legacy summary daily (optional)
    legacy = pd.DataFrame(
        {
            "dt": df["dt"],
            "combo_10vol": df["ret_combo_net"],
        }
    )
    legacy_path = out_dir / "daily_combo.csv"
    legacy.to_csv(legacy_path, index=False)

    # Summary
    summary = pd.DataFrame(
        [
            {
                "name": "Composite_net",
                "ann_return": df["ret_combo_net"].mean() * TRADING_DAYS,
                "ann_vol": ann_vol(df["ret_combo_net"]),
                "sharpe": sharpe(df["ret_combo_net"]),
                "max_drawdown": max_drawdown(df["equity_net"]),
                "hit_rate": hit_rate(df["ret_combo_net"]),
                "turnover_ann": float(df["turnover"].sum() / (len(df) / TRADING_DAYS)),
                "rows": len(df),
            }
        ]
    )
    out_summary.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_summary, index=False)

    print("[OK] Wrote:")
    print(f" - {rich_path}")
    print(f" - {legacy_path}")
    print(f" - {out_summary}")


if __name__ == "__main__":
    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 120)
    try:
        main()
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
