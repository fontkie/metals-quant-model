import argparse, os, yaml, time, shutil
import numpy as np
import pandas as pd
from datetime import timedelta

# --- import utils whether run as module (-m) or as a script ---
try:
    from .utils import (
        deep_merge,
        expand_grid_coarse,
        expand_grid_local,
        composite_score,
    )
except Exception:
    import sys

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from src.wfv.utils import (
        deep_merge,
        expand_grid_coarse,
        expand_grid_local,
        composite_score,
    )
# ------------------------------------------------------------------------------


# ============ IO helpers ============
def safe_write_csv(df, path):
    """Atomic write; if target locked, write a timestamped fallback."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp_{int(time.time())}"
    df.to_csv(tmp, index=False)
    try:
        os.replace(tmp, path)
    except PermissionError:
        base, ext = os.path.splitext(path)
        alt = f"{base}.{int(time.time())}{ext}"
        shutil.move(tmp, alt)
        print(f"[warn] Locked file; wrote to: {alt}")


# ============ Data loading (Excel-aware via global config) ============
def get_data_for_tier(market: str, tier: str, global_cfg: dict) -> pd.DataFrame:
    ds = global_cfg.get("data", {}).get(market, {}).get(tier, {})
    if not ds:
        raise FileNotFoundError(
            f"No data config for {market}/{tier} in config/wfv.yaml"
        )

    # Price
    p = ds.get("price", {})
    p_path = p.get("path")
    p_sheet = p.get("sheet", 0)
    p_date = p.get("date_col", "Date")
    p_px = p.get("price_col", "price")
    if not p_path:
        raise FileNotFoundError("Price path not set in config/wfv.yaml -> data")

    px = pd.read_excel(p_path, sheet_name=p_sheet, engine="openpyxl")
    px.columns = [str(c).strip() for c in px.columns]
    px = px[[p_date, p_px]].rename(columns={p_date: "date", p_px: "price"})
    px["date"] = pd.to_datetime(px["date"])
    df = px.sort_values("date").drop_duplicates("date")

    # Stocks (optional)
    s = ds.get("stocks", {})
    s_path = s.get("path")
    if s_path:
        s_sheet = s.get("sheet", 0)
        s_date = s.get("date_col", "Date")
        s_col = s.get("stocks_col", "stocks")
        st = pd.read_excel(s_path, sheet_name=s_sheet, engine="openpyxl")
        st.columns = [str(c).strip() for c in st.columns]
        st = st[[s_date, s_col]].rename(columns={s_date: "date", s_col: "stocks"})
        st["date"] = pd.to_datetime(st["date"])
        st = st.sort_values("date").drop_duplicates("date")
        df = df.merge(st, on="date", how="left")

    df = df.set_index("date").asfreq("B")
    df["price"] = df["price"].ffill()
    if "stocks" in df.columns:
        df["stocks"] = df["stocks"].ffill()
    return df.dropna(subset=["price"])


# ============ Fold builder ============
def build_folds(df: pd.DataFrame, folds_cfg: dict) -> list[dict]:
    start = pd.to_datetime(folds_cfg.get("start", df.index.min()))
    end = pd.to_datetime(folds_cfg.get("end", df.index.max()))
    df = df.loc[start:end].copy()

    train_years = int(folds_cfg["train_years"])
    test_years = int(folds_cfg["test_years"])

    # Quarter-end stepping ("Q" deprecated → use "QE-DEC")
    quarter_ends = df.resample("QE-DEC").last().index
    folds = []
    for anchor in quarter_ends:
        test_start = anchor + pd.offsets.Day(1)
        test_end = test_start + pd.DateOffset(years=test_years) - pd.offsets.Day(1)
        train_end = test_start - pd.offsets.Day(1)
        train_start = train_end - pd.DateOffset(years=train_years) + pd.offsets.Day(1)
        if train_start < df.index.min() or test_end > df.index.max():
            continue
        folds.append(
            {
                "train_start": train_start.normalize(),
                "train_end": train_end.normalize(),
                "test_start": test_start.normalize(),
                "test_end": test_end.normalize(),
            }
        )
    return folds


# ============ Metrics ============
def ann_factor():
    return np.sqrt(252.0)


def sharpe(returns):
    r = returns.dropna()
    if r.empty:
        return 0.0
    sd = r.std(ddof=0)
    return 0.0 if sd == 0 else r.mean() / sd * ann_factor()


def max_drawdown(equity):
    cummax = np.maximum.accumulate(equity)
    dd = equity / cummax - 1.0
    return float(dd.min() * 100.0)


def tail_ratio(returns):
    r = returns.dropna()
    if len(r) < 10:
        return 0.0
    left = np.percentile(r, 5)
    right = np.percentile(r, 95)
    if left == 0:
        return np.inf if right > 0 else 0.0
    return float(abs(right / left))


def hit_rate(returns):
    r = returns.dropna()
    return 0.0 if len(r) == 0 else float((r > 0).mean())


def realized_vol(returns, lookback=21):
    return returns.rolling(lookback).std(ddof=0) * np.sqrt(252.0)


# ============ Stocks filter helper ============
def apply_stocks_filter(df, fcfg, use_filter: bool):
    if not use_filter or "stocks" not in df.columns:
        return pd.Series(1.0, index=df.index)
    win = fcfg.get("pct_rank_window", [60])[0]
    thr_lo = fcfg.get("threshold_low", [0.2])[0]
    thr_hi = fcfg.get("threshold_high", [0.8])[0]
    side = fcfg.get("side", ["both"])[0]
    ranks = (
        df["stocks"]
        .rolling(win)
        .apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False)
    )
    if side == "both":
        mask = ((ranks <= thr_lo) | (ranks >= thr_hi)).astype(float)
    elif side == "long_only_when_low":
        mask = (ranks <= thr_lo).astype(float)
    elif side == "short_only_when_high":
        mask = (ranks >= thr_hi).astype(float)
    else:
        mask = pd.Series(1.0, index=df.index)
    return mask.reindex(df.index).fillna(1.0)


# ============ HookCore signal (your real logic) ============
def signal_pricing_hook(df, params):
    px = df["price"].dropna()

    def z_of_hday_return(px_series, h):
        r_h = np.log(px_series / px_series.shift(h))
        sd_h = r_h.rolling(252, min_periods=60).std(ddof=0)
        return r_h / (sd_h.replace(0, np.nan))

    z3 = z_of_hday_return(px, 3)
    z5 = z_of_hday_return(px, 5)
    w35 = float(params.get("w35", 0.5))
    z_eq = w35 * z3 + (1.0 - w35) * z5

    thr = float(params.get("threshold", 0.75))
    raw = pd.Series(0.0, index=z_eq.index)
    raw[z_eq >= thr] = -1.0
    raw[z_eq <= -thr] = 1.0

    # Friday weekly backup (optional)
    if bool(params.get("weekly_backup", False)):
        wthr = float(params.get("weekly_threshold", max(0.85, thr)))
        weekly = pd.Series(0.0, index=z_eq.index)
        weekly[z_eq >= wthr] = -1.0
        weekly[z_eq <= -wthr] = 1.0
        is_fri = raw.index.weekday == 4
        raw.loc[is_fri] = weekly.loc[is_fri]

    # Bi-weekly execution: Mon uses Fri; Wed uses Tue
    idx = raw.index
    origin = pd.Series(idx, index=idx, dtype="datetime64[ns]")
    is_mon = idx.weekday == 0
    origin[is_mon] = origin[is_mon] - pd.Timedelta(days=3)
    is_wed = idx.weekday == 2
    origin[is_wed] = origin[is_wed] - pd.Timedelta(days=1)
    origin[~(is_mon | is_wed)] = pd.NaT
    exec_sig = pd.Series(np.nan, index=idx, dtype=float)
    for d in origin.dropna().index:
        od = origin.loc[d]
        if od in raw.index:
            exec_sig.loc[d] = raw.loc[od]
    exec_sig = exec_sig.ffill().fillna(0.0)
    return exec_sig


# ============ Execution & costs ============
def vol_target_positions(pos_raw, px, exec_cfg):
    ret = np.log(px).diff().fillna(0.0)
    look = int(exec_cfg.get("vol_lookback_days", 21))
    vt = float(exec_cfg.get("vol_target_annual", 0.10))
    cap = float(exec_cfg.get("vol_cap", 2.5))
    vol = realized_vol(ret, lookback=look).replace(0.0, np.nan).bfill()
    daily_target = vt / np.sqrt(252.0)
    scale = (daily_target / (vol + 1e-12)).clip(upper=cap)
    pos_sized = pos_raw * scale
    clip = float(exec_cfg.get("position_clip", 1.0))
    return pos_sized.clip(-clip, clip)


def apply_tplus1_and_costs(pos_sized, px, cost_cfg):
    ret = np.log(px).diff().fillna(0.0)
    pos_t1 = pos_sized.shift(1).fillna(0.0)  # T+1
    turn = pos_sized.diff().abs().fillna(0.0)
    turn_bps = float(cost_cfg.get("turn_bps", 1.5))
    slip_bps = float(cost_cfg.get("slippage_bps", 0.0))
    cost_per_day = (turn_bps + slip_bps) / 10000.0 * turn
    pnl = pos_t1 * ret - cost_per_day
    return pnl, turn


# ============ Train/Eval wrapper ============
def train_eval_on_slice(
    params,
    data_train,
    data_test,
    exec_cfg,
    cost_cfg,
    stocks_mask_train=None,
    stocks_mask_test=None,
):
    sig_tr = signal_pricing_hook(data_train, params)
    sig_te = signal_pricing_hook(data_test, params)

    if stocks_mask_train is not None:
        sig_tr = sig_tr * stocks_mask_train.reindex(sig_tr.index).fillna(1.0)
    if stocks_mask_test is not None:
        sig_te = sig_te * stocks_mask_test.reindex(sig_te.index).fillna(1.0)

    pos_tr = vol_target_positions(sig_tr, data_train["price"], exec_cfg)
    pnl_tr, turn_tr = apply_tplus1_and_costs(pos_tr, data_train["price"], cost_cfg)

    pos_te = vol_target_positions(sig_te, data_test["price"], exec_cfg)
    pnl_te, turn_te = apply_tplus1_and_costs(pos_te, data_test["price"], cost_cfg)

    tr = pnl_tr.dropna()
    te = pnl_te.dropna()
    eq_tr = (1 + tr).cumprod()
    eq_te = (1 + te).cumprod()

    train_metrics = {
        "sharpe": float(sharpe(tr)),
        "max_drawdown": float(max_drawdown(eq_tr)),
        "turnover": float(turn_tr.sum() * (252.0 / max(1, len(turn_tr)))),
        "hit_rate": float(hit_rate(tr)),
        "tail_ratio": float(tail_ratio(tr)),
    }
    test_metrics = {
        "sharpe": float(sharpe(te)),
        "max_drawdown": float(max_drawdown(eq_te)),
        "turnover": float(turn_te.sum() * (252.0 / max(1, len(turn_te)))),
        "hit_rate": float(hit_rate(te)),
        "tail_ratio": float(tail_ratio(te)),
    }
    return train_metrics, test_metrics


# ============ Runner ============
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True)  # e.g., copper
    ap.add_argument("--sleeve", required=True)  # 'pricing' for HookCore
    ap.add_argument("--base", required=True)  # base sleeve YAML (hookcore_config.yaml)
    ap.add_argument("--wfv-global", required=True)  # config/wfv.yaml
    ap.add_argument("--wfv-sleeve", required=True)  # docs/.../wfv.yaml
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    # Load configs
    with open(args.wfv_global, "r", encoding="utf-8") as f:
        global_cfg = yaml.safe_load(f) or {}
    with open(args.wfv_sleeve, "r", encoding="utf-8") as f:
        sleeve_cfg = yaml.safe_load(f) or {}
    try:
        with open(args.base, "r", encoding="utf-8") as f:
            base_cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        alt = sleeve_cfg.get("binds_to_base")
        if not alt:
            raise
        with open(alt, "r", encoding="utf-8") as f:
            base_cfg = yaml.safe_load(f) or {}

    # Merge (base -> global -> sleeve)
    effective = deep_merge(base_cfg, global_cfg)
    effective = deep_merge(effective, sleeve_cfg)

    # Data and folds
    df = get_data_for_tier(args.market, effective.get("tier", "tierA"), global_cfg)
    folds = build_folds(df, effective["folds"])
    embargo_days = int(effective["folds"].get("embargo_days", 21))

    # Search setup
    search_mode = effective.get("search_mode", {"strategy": "fixed_grid"})
    sel = effective["metrics"]["selection"]
    primary = sel.get("primary", "sharpe")
    comp = sel.get("composite", {})
    coarse_bounds = {
        k: v for k, v in effective.get("grids", {}).items() if isinstance(v, list)
    }
    optimise = bool(effective.get("optimise", True))

    # Stocks filter config (optional)
    stocks_cfg = effective.get("filters", {}).get("stocks_filter", None)

    rows_params, rows_metrics = [], []
    prev_best = None

    for i, f in enumerate(folds):
        tr = df.loc[f["train_start"] : f["train_end"]].copy()
        te = df.loc[f["test_start"] : f["test_end"]].copy()

        # Embargo
        if embargo_days > 0:
            tr = tr.iloc[:-embargo_days] if len(tr) > embargo_days else tr.iloc[0:0]
            te = te.iloc[embargo_days:] if len(te) > embargo_days else te.iloc[0:0]

        # Optional stocks masks
        tr_mask = te_mask = None
        if stocks_cfg is not None:
            tr_mask = apply_stocks_filter(tr, stocks_cfg, use_filter=True)
            te_mask = apply_stocks_filter(te, stocks_cfg, use_filter=True)

        # Build parameter grid
        if not optimise:
            grid = [effective.get("use_params", {})]
            apply_candidates = [False]
            if stocks_cfg is not None and isinstance(
                stocks_cfg.get("apply", [False]), list
            ):
                apply_candidates = stocks_cfg["apply"]
        else:
            if i == 0 or search_mode.get("strategy") == "fixed_grid":
                grid = expand_grid_coarse(effective["grids"])
            else:
                grid = expand_grid_local(
                    effective.get("local_refine_template", {}),
                    prev_best,
                    coarse_bounds,
                    max_total=search_mode.get("max_total_combos", 120),
                )
            apply_candidates = [False]
            if stocks_cfg is not None:
                apply_candidates = stocks_cfg.get("apply", [False])

        # Grid search on TRAIN; evaluate TEST with same params
        scored = []
        for params in grid:
            for use_filter in apply_candidates:
                tm = tr_mask if (use_filter and tr_mask is not None) else None
                te_m = te_mask if (use_filter and te_mask is not None) else None
                tr_m, te_m = train_eval_on_slice(
                    params,
                    tr,
                    te,
                    effective["execution"],
                    effective["costs"],
                    stocks_mask_train=tm,
                    stocks_mask_test=te_m,
                )
                if primary == "sharpe":
                    score = tr_m["sharpe"]
                else:
                    score = composite_score(
                        tr_m["sharpe"],
                        tr_m["max_drawdown"],
                        tr_m["turnover"],
                        tr_m["tail_ratio"],
                        ws=comp.get("sharpe_weight", 1.0),
                        wdd=comp.get("dd_penalty_weight", 0.3),
                        wto=comp.get("turnover_penalty_weight", 0.1),
                        wtail=comp.get("tail_bonus_weight", 0.0),
                    )
                scored.append((score, tr_m, te_m, params, use_filter))

        # Pick best by score; tie-break: lower DD, lower turnover (on TRAIN)
        scored.sort(
            key=lambda x: (
                -x[0],
                x[1].get("max_drawdown", 1e9),
                x[1].get("turnover", 1e9),
            )
        )
        best_score, tr_best, te_best, best_params, best_filter = scored[0]
        prev_best = best_params

        rows_params.append(
            {
                "fold": i,
                "train_start": f["train_start"],
                "train_end": f["train_end"],
                "test_start": f["test_start"],
                "test_end": f["test_end"],
                **best_params,
                "stocks_filter_applied": best_filter,
            }
        )
        rows_metrics.append(
            {
                "fold": i,
                "phase": "train",
                "train_start": f["train_start"],
                "train_end": f["train_end"],
                **tr_best,
            }
        )
        rows_metrics.append(
            {
                "fold": i,
                "phase": "test",
                "test_start": f["test_start"],
                "test_end": f["test_end"],
                **te_best,
            }
        )

    # ---- OPTIONAL: emit daily OOS series for parity checks (fixed params only recommended) ----
    if bool(effective.get("emit_stitched_oos", False)) and len(folds) > 0:
        oos_start = folds[0]["test_start"]
        oos_end = folds[-1]["test_end"]

        # 1) Static OOS using the fixed params over the whole OOS span
        fixed_params = effective.get("use_params", {})
        full = df.loc[oos_start:oos_end].copy()
        sig_static = signal_pricing_hook(full, fixed_params)
        pos_static = vol_target_positions(
            sig_static, full["price"], effective["execution"]
        )
        pnl_static, _ = apply_tplus1_and_costs(
            pos_static, full["price"], effective["costs"]
        )
        safe_write_csv(
            pnl_static.dropna()
            .rename("pnl")
            .reset_index()
            .rename(columns={"index": "date"}),
            os.path.join(args.out, "static_oos_pnl.csv"),
        )

        # 2) WFV-stitched OOS (concatenate each fold's TEST pnl with the same fixed params)
        parts = []
        for r in rows_params:
            i = r["fold"]
            f = folds[i]
            te = df.loc[f["test_start"] : f["test_end"]].copy()
            sig_te = signal_pricing_hook(te, fixed_params)
            pos_te = vol_target_positions(sig_te, te["price"], effective["execution"])
            pnl_te, _ = apply_tplus1_and_costs(pos_te, te["price"], effective["costs"])
            parts.append(pnl_te.dropna())
        if parts:
            pnl_wfv = pd.concat(parts).sort_index()
            safe_write_csv(
                pnl_wfv.rename("pnl").reset_index().rename(columns={"index": "date"}),
                os.path.join(args.out, "wfv_stitched_oos_pnl.csv"),
            )
    # ------------------------------------------------------------------------------

    # Save outputs (keep these last)
    outdir = args.out
    safe_write_csv(pd.DataFrame(rows_params), os.path.join(outdir, "param_choices.csv"))
    safe_write_csv(pd.DataFrame(rows_metrics), os.path.join(outdir, "fold_metrics.csv"))


if __name__ == "__main__":
    main()
