import argparse, os, yaml, time, shutil
import numpy as np
import pandas as pd
from datetime import timedelta


# ================= IO helpers =================
def safe_write_csv(df: pd.DataFrame, path: str):
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


# ================= Small utils =================
def deep_merge(a: dict, b: dict) -> dict:
    """Recursive dict merge (b overrides a)."""
    out = dict(a or {})
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def composite_score(
    sharpe, max_dd_pct, turnover_pa, tail_ratio, ws=1.0, wdd=0.30, wto=0.10, wtail=0.0
):
    # max_dd_pct is negative (e.g., -15). Penalise its magnitude.
    dd_penalty = wdd * (abs(max_dd_pct) / 100.0)
    to_penalty = wto * turnover_pa
    tail_bonus = wtail * max(0.0, tail_ratio - 1.0)
    return ws * (sharpe - dd_penalty - to_penalty + tail_bonus)


def expand_grid(grid_spec: dict) -> list[dict]:
    """Cartesian product for params where values are lists."""
    keys = []
    values = []
    for k, v in (grid_spec or {}).items():
        if isinstance(v, list):
            keys.append(k)
            values.append(v)
    if not keys:
        return [{}]
    out = []

    def rec(i, cur):
        if i == len(keys):
            out.append(cur.copy())
            return
        k = keys[i]
        for val in values[i]:
            cur[k] = val
            rec(i + 1, cur)

    rec(0, {})
    return out


# ================= Data loading =================
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
    df = px.sort_values("date").drop_duplicates("date").set_index("date").asfreq("B")
    df["price"] = df["price"].ffill()

    # Optional stocks (kept off by default)
    s = ds.get("stocks", {})
    s_path = s.get("path")
    if s_path:
        st = pd.read_excel(s_path, sheet_name=s.get("sheet", 0), engine="openpyxl")
        st.columns = [str(c).strip() for c in st.columns]
        st = st[[s.get("date_col", "Date"), s.get("stocks_col", "stocks")]]
        st = st.rename(
            columns={
                s.get("date_col", "Date"): "date",
                s.get("stocks_col", "stocks"): "stocks",
            }
        )
        st["date"] = pd.to_datetime(st["date"])
        st = (
            st.sort_values("date").drop_duplicates("date").set_index("date").asfreq("B")
        )
        st["stocks"] = st["stocks"].ffill()
        df = df.merge(st, left_index=True, right_index=True, how="left")
    return df.dropna(subset=["price"])


# ================= Folds =================
def build_folds(df: pd.DataFrame, folds_cfg: dict) -> list[dict]:
    start = pd.to_datetime(folds_cfg.get("start", df.index.min()))
    end = pd.to_datetime(folds_cfg.get("end", df.index.max()))
    train_years = int(folds_cfg.get("train_years", 5))
    test_years = int(folds_cfg.get("test_years", 1))
    df = df.loc[start:end]
    q_ends = df.resample("Q-DEC").last().index  # quarter ends
    folds = []
    for anchor in q_ends:
        test_start = anchor + pd.offsets.Day(1)
        test_end = test_start + pd.DateOffset(years=test_years) - pd.offsets.Day(1)
        train_end = test_start - pd.offsets.Day(1)
        train_start = train_end + pd.offsets.Day(1) - pd.DateOffset(years=train_years)
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


# ================= Metrics =================
def ann_factor():
    return np.sqrt(252.0)


def sharpe(returns: pd.Series) -> float:
    r = returns.dropna()
    if r.empty:
        return 0.0
    sd = r.std(ddof=0)
    return 0.0 if sd == 0 else float((r.mean() / sd) * ann_factor())


def max_drawdown(equity: pd.Series) -> float:
    cummax = np.maximum.accumulate(equity)
    dd = equity / cummax - 1.0
    return float(dd.min() * 100.0)  # pct


def tail_ratio(returns: pd.Series) -> float:
    r = returns.dropna()
    if len(r) < 10:
        return 0.0
    left = np.percentile(r, 5)
    right = np.percentile(r, 95)
    if left == 0:
        return np.inf if right > 0 else 0.0
    return float(abs(right / left))


def hit_rate(returns: pd.Series) -> float:
    r = returns.dropna()
    return 0.0 if len(r) == 0 else float((r > 0).mean())


# ================= Signals (HookCore) =================
def _z_of_hday_return(px: pd.Series, h: int) -> pd.Series:
    r_h = np.log(px / px.shift(h))
    sd_h = r_h.rolling(252, min_periods=60).std(ddof=0)
    return r_h / (sd_h.replace(0, np.nan))


def signal_pricing_hook(px: pd.Series, params: dict) -> pd.Series:
    """Discrete ±1/0 signal sampled on Mon/Wed (origin Fri/Tue)."""
    w35 = float(params.get("w35", 0.5))
    thr = float(params.get("threshold", 0.75))

    z3 = _z_of_hday_return(px, 3)
    z5 = _z_of_hday_return(px, 5)
    z_eq = w35 * z3 + (1.0 - w35) * z5

    raw = pd.Series(0.0, index=z_eq.index, dtype=float)
    raw[z_eq >= thr] = -1.0
    raw[z_eq <= -thr] = 1.0

    # Build Mon/Wed execution days and map to Fri/Tue origin
    idx = raw.index
    is_mon = idx.weekday == 0
    is_wed = idx.weekday == 2
    origin = pd.Series(pd.NaT, index=idx, dtype="datetime64[ns]")
    origin.loc[is_mon] = (idx[is_mon] - pd.Timedelta(days=3)).values  # Fri
    origin.loc[is_wed] = (idx[is_wed] - pd.Timedelta(days=1)).values  # Tue
    exec_days = origin.dropna().index
    origin_days = pd.DatetimeIndex(origin.dropna().values)

    # Map origin signals to execution days; ffill between execs
    mapped = pd.Series(raw.reindex(origin_days).values, index=exec_days)
    exec_sig = pd.Series(np.nan, index=idx, dtype=float)
    exec_sig.loc[exec_days] = mapped.values
    exec_sig = exec_sig.ffill().fillna(0.0)  # hold between rebalances
    return exec_sig


# ================= Execution, sizing, costs =================
def realized_vol_annual(ret: pd.Series, lookback: int) -> pd.Series:
    # simple returns -> annualised realised vol
    return ret.rolling(lookback).std(ddof=0) * np.sqrt(252.0)


def build_exec_mask(index: pd.DatetimeIndex) -> pd.Series:
    return pd.Series((index.weekday == 0) | (index.weekday == 2), index=index)


def vol_target_positions(
    exec_signal: pd.Series, px: pd.Series, exec_cfg: dict
) -> pd.Series:
    """
    Vol-target with units aligned:
      - compute annualised realised vol of simple returns,
      - compute target scale on EXECUTION DAYS only,
      - forward-fill scale until next exec day.
    Position only changes on exec days (so costs apply only there).
    """
    look = int(exec_cfg.get("vol_lookback_days", 21))
    vt_ann = float(exec_cfg.get("vol_target_annual", 0.10))
    cap = float(exec_cfg.get("vol_cap", 2.5))
    clip = float(exec_cfg.get("position_clip", cap))

    simple_ret = px.pct_change().fillna(0.0)
    vol_ann = realized_vol_annual(simple_ret, lookback=look).replace(0.0, np.nan)

    idx = exec_signal.index
    exec_mask = build_exec_mask(idx)
    exec_dates = idx[exec_mask.values]

    # Scale only on exec dates, then hold
    scale_exec = pd.Series(np.nan, index=idx, dtype=float)
    scale_on_exec = (vt_ann / (vol_ann.reindex(exec_dates) + 1e-12)).clip(upper=cap)
    scale_exec.loc[exec_dates] = scale_on_exec.values
    scale_exec = scale_exec.ffill().fillna(method="bfill").fillna(0.0)
    scale_exec = scale_exec.clip(-cap, cap)

    pos = exec_signal * scale_exec
    return pos.clip(-clip, clip)


def apply_tplus1_and_costs(pos_sized: pd.Series, px: pd.Series, cost_cfg: dict):
    """T+1 fills; costs only when position changes (i.e., exec days)."""
    simple_ret = px.pct_change().fillna(0.0)
    pos_t1 = pos_sized.shift(1).fillna(0.0)  # T+1
    turn = (
        pos_sized.diff().abs().fillna(0.0)
    )  # non-zero only at exec days (by construction)
    turn_bps = float(cost_cfg.get("turn_bps", 1.5))
    pnl = pos_t1 * simple_ret - (turn_bps / 10000.0) * turn
    return pnl, turn


# ================= Train/Eval per slice =================
def train_eval_on_slice(params, data_train, data_test, exec_cfg, cost_cfg):
    sig_tr = signal_pricing_hook(data_train["price"], params)
    sig_te = signal_pricing_hook(data_test["price"], params)

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
        "turnover": float(turn_tr.sum() * (252.0 / max(1, len(turn_tr)))),  # per-annum
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


# ================= Runner =================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True)  # e.g. copper
    ap.add_argument("--sleeve", required=True)  # 'pricing' (HookCore)
    ap.add_argument("--base", required=False)  # base sleeve YAML (optional)
    ap.add_argument("--wfv-global", required=True)  # config/wfv.yaml
    ap.add_argument("--wfv-sleeve", required=True)  # docs/.../wfv.yaml
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.wfv_global, "r", encoding="utf-8") as f:
        global_cfg = yaml.safe_load(f) or {}
    with open(args.wfv_sleeve, "r", encoding="utf-8") as f:
        sleeve_cfg = yaml.safe_load(f) or {}
    base_cfg = {}
    if args.base and os.path.exists(args.base):
        with open(args.base, "r", encoding="utf-8") as f:
            base_cfg = yaml.safe_load(f) or {}

    # Merge configs: base -> global -> sleeve
    effective = deep_merge(base_cfg, global_cfg)
    effective = deep_merge(effective, sleeve_cfg)

    df = get_data_for_tier(args.market, effective.get("tier", "tierA"), effective)
    folds = build_folds(df, effective["folds"])
    embargo_days = int(effective["folds"].get("embargo_days", 0))

    # Search setup
    optimise = bool(effective.get("optimise", False))
    grids = effective.get("grids", {})
    sel_cfg = effective.get("metrics", {}).get("selection", {})
    comp_cfg = sel_cfg.get("composite", {})
    primary = sel_cfg.get("primary", "composite")

    # Fixed params for parity
    fixed_params = effective.get("use_params", {"threshold": 0.75, "w35": 0.5})

    rows_params, rows_metrics = [], []
    prev_best = fixed_params

    for i, f in enumerate(folds):
        tr = df.loc[f["train_start"] : f["train_end"]].copy()
        te = df.loc[f["test_start"] : f["test_end"]].copy()

        # Embargo
        if embargo_days > 0 and len(tr) > embargo_days:
            tr = tr.iloc[:-embargo_days]
        if embargo_days > 0 and len(te) > embargo_days:
            te = te.iloc[embargo_days:]

        # Param grid
        grid = [fixed_params] if not optimise else expand_grid(grids)

        # Evaluate grid on TRAIN; pick best by selection rule
        scored = []
        for params in grid:
            tr_m, te_m = train_eval_on_slice(
                params, tr, te, effective["execution"], effective["costs"]
            )
            if primary == "sharpe":
                score = tr_m["sharpe"]
            else:
                score = composite_score(
                    tr_m["sharpe"],
                    tr_m["max_drawdown"],
                    tr_m["turnover"],
                    tr_m["tail_ratio"],
                    ws=comp_cfg.get("sharpe_weight", 1.0),
                    wdd=comp_cfg.get("dd_penalty_weight", 0.30),
                    wto=comp_cfg.get("turnover_penalty_weight", 0.10),
                    wtail=comp_cfg.get("tail_bonus_weight", 0.0),
                )
            scored.append((score, tr_m, te_m, params))

        scored.sort(
            key=lambda x: (
                -x[0],
                x[1].get("max_drawdown", 1e9),
                x[1].get("turnover", 1e9),
            )
        )
        best_score, tr_best, te_best, best_params = scored[0]
        prev_best = best_params

        rows_params.append({"fold": i, **f, **best_params})
        rows_metrics += [
            {"fold": i, "phase": "train", **f, **tr_best},
            {"fold": i, "phase": "test", **f, **te_best},
        ]

    # ---- Emit parity daily OOS (fixed params recommended) ----
    if bool(effective.get("emit_stitched_oos", True)) and len(folds) > 0:
        oos_start = folds[0]["test_start"]
        oos_end = folds[-1]["test_end"]
        full_oos = df.loc[oos_start:oos_end].copy()

        # 1) Static OOS (fixed params across entire OOS)
        sig_static = signal_pricing_hook(full_oos["price"], fixed_params)
        pos_static = vol_target_positions(
            sig_static, full_oos["price"], effective["execution"]
        )
        pnl_static, _ = apply_tplus1_and_costs(
            pos_static, full_oos["price"], effective["costs"]
        )

        safe_write_csv(
            pnl_static.dropna()
            .rename("pnl")
            .reset_index()
            .rename(columns={"index": "date"}),
            os.path.join(args.out, "static_oos_pnl.csv"),
        )

        # 2) WFV-stitched (concatenate each fold TEST pnl under fixed params)
        parts = []
        for r in rows_params:
            te = df.loc[r["test_start"] : r["test_end"]].copy()
            sig_te = signal_pricing_hook(te["price"], fixed_params)
            pos_te = vol_target_positions(sig_te, te["price"], effective["execution"])
            pnl_te, _ = apply_tplus1_and_costs(pos_te, te["price"], effective["costs"])
            parts.append(pnl_te.dropna())
        if parts:
            pnl_wfv = pd.concat(parts).sort_index()
            safe_write_csv(
                pnl_wfv.rename("pnl").reset_index().rename(columns={"index": "date"}),
                os.path.join(args.out, "wfv_stitched_oos_pnl.csv"),
            )

    # Save grids/metrics
    outdir = args.out
    safe_write_csv(pd.DataFrame(rows_params), os.path.join(outdir, "param_choices.csv"))
    safe_write_csv(pd.DataFrame(rows_metrics), os.path.join(outdir, "fold_metrics.csv"))


if __name__ == "__main__":
    main()
