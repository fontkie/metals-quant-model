# src/build_composite.py
import os
import yaml
import numpy as np
import pandas as pd

from utils.policy import load_execution_policy, policy_banner, warn_if_mismatch

# --- Policy header ---
POLICY = load_execution_policy()
policy_banner(POLICY, "Composite")
warn_if_mismatch(POLICY)


# ---------- helpers ----------
def ann_vol(x: pd.Series) -> float:
    x = pd.to_numeric(x, errors="coerce")
    return float(np.sqrt(252.0) * np.nanstd(x))


def realised_vol(x: pd.Series, lookback: int) -> float:
    x = pd.to_numeric(x, errors="coerce")
    if lookback and lookback < len(x):
        x = x.tail(lookback)
    return float(np.sqrt(252.0) * np.nanstd(x))


def load_sleeve_positions(input_dir: str, sleeves: list) -> list:
    """
    Load each sleeve's position from outputs/Copper/<sleeve>/daily_series.csv
    Accepts date columns: dt or date
    Accepts position columns: position_Tplus1, position, pos, position_vt
    """
    dfs = []
    meta = []
    for s in sleeves:
        path = os.path.join(input_dir, s.lower(), "daily_series.csv")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing sleeve file: {path}")

        df = pd.read_csv(path)
        lower = {c.lower(): c for c in df.columns}

        date_col = lower.get("date") or lower.get("dt")
        if date_col is None:
            raise KeyError(f"No 'dt' or 'date' in {path}. Columns: {list(df.columns)}")

        pos_key = None
        for cand in ["position_tplus1", "position", "pos", "position_vt"]:
            if cand in lower:
                pos_key = lower[cand]
                break
        if pos_key is None:
            raise KeyError(
                f"No position col in {path}. Need one of position_Tplus1/position/pos/position_vt"
            )

        out = df[[date_col, pos_key]].copy()
        out.columns = ["dt", f"{s}_pos"]
        out["dt"] = pd.to_datetime(out["dt"], errors="coerce")
        out.sort_values("dt", inplace=True)
        dfs.append(out)
        meta.append((s, path, pos_key))
    return dfs, meta


def find_price_series(input_dir: str, sleeves: list) -> pd.DataFrame:
    """Find any sleeve daily_series.csv that has both date/dt and price."""
    for s in sleeves:
        p = os.path.join(input_dir, s.lower(), "daily_series.csv")
        if os.path.exists(p):
            df = pd.read_csv(p)
            lower = {c.lower(): c for c in df.columns}
            date_col = lower.get("date") or lower.get("dt")
            price_col = lower.get("price")
            if date_col and price_col:
                out = df[[date_col, price_col]].copy()
                out.columns = ["dt", "price"]
                out["dt"] = pd.to_datetime(out["dt"], errors="coerce")
                out.sort_values("dt", inplace=True)
                return out
    raise FileNotFoundError(
        f"Could not find price series with ['dt' or 'date', 'price'] under {input_dir}/<sleeve>/daily_series.csv"
    )


def erc_weights(cov: np.ndarray, tol: float = 1e-10, iters: int = 1000) -> np.ndarray:
    """
    Equal Risk Contribution weights via multiplicative updates.
    cov: covariance matrix of sleeve returns (NxN)
    """
    n = cov.shape[0]
    w = np.ones(n) / n
    for _ in range(iters):
        m = cov @ w  # marginal risk
        port_var = float(w @ m)
        if port_var <= 0 or not np.isfinite(port_var):
            break
        target = port_var / n
        rc = w * m  # risk contributions
        # avoid zeros
        rc = np.where(rc <= 0, 1e-12, rc)
        w_new = w * (target / rc)  # multiplicative update
        w_new = np.clip(w_new, 1e-10, None)
        w_new = w_new / w_new.sum()
        if np.linalg.norm(w_new - w, 1) < tol:
            w = w_new
            break
        w = w_new
    return w / w.sum()


# ---------- main ----------
def main():
    # ---- Load config
    with open("Docs/Copper/combined/composite_config.yaml", "r") as f:
        cfg = yaml.safe_load(f)["composite"]

    sleeves = cfg["sleeves"]
    input_dir = cfg.get("input_dir", "outputs/Copper")
    out_csv = cfg.get("out_csv", "outputs/Copper/composite_v0.3.csv")
    out_summary = cfg.get("out_summary", "outputs/Copper/composite_v0.3_summary.txt")
    out_diag_txt = cfg.get(
        "out_diag_txt", "outputs/Copper/composite_v0.3_diagnostics.txt"
    )
    out_corr_csv = cfg.get(
        "out_corr_csv", "outputs/Copper/composite_v0.3_sleeve_corr.csv"
    )

    per_sleeve_target_vol = float(cfg.get("per_sleeve_target_vol", 0.10))
    cap = float(cfg.get("cap", 1.0))
    cost_bps = float(cfg.get("cost_bps", 1.5)) / 10000.0
    use_erc = bool(cfg.get("use_erc_weights", True))

    use_comp_vt = bool(cfg.get("use_composite_vol_target", True))
    comp_target = float(cfg.get("composite_vol_target", 0.10))
    comp_lev_cap = float(cfg.get("composite_lev_cap", 2.5))
    comp_lookback = int(cfg.get("composite_vol_lookback", 60))

    # ---- Load sleeve positions
    pos_dfs, meta = load_sleeve_positions(input_dir, sleeves)
    data = pos_dfs[0]
    for df in pos_dfs[1:]:
        data = data.merge(df, on="dt", how="inner")

    # ---- Add price & compute single instrument return
    px = find_price_series(input_dir, sleeves)
    data = data.merge(px, on="dt", how="inner")
    data["instr_ret"] = data["price"].pct_change().fillna(0.0)

    # ---- Risk-normalise sleeves vs instrument return
    pre_vols = {}
    scales = {}
    for s in sleeves:
        raw_ret = pd.to_numeric(data[f"{s}_pos"], errors="coerce") * pd.to_numeric(
            data["instr_ret"], errors="coerce"
        )
        v = ann_vol(raw_ret)
        pre_vols[s] = v
        scale = (per_sleeve_target_vol / v) if (v and v > 0 and np.isfinite(v)) else 0.0
        scales[s] = scale
        data[f"{s}_pos_scaled"] = (
            pd.to_numeric(data[f"{s}_pos"], errors="coerce") * scale
        )

    # ---- Sleeve realised returns (post scaling)
    r_cols = []
    for s in sleeves:
        col = f"{s}_ret_scaled"
        data[col] = pd.to_numeric(
            data[f"{s}_pos_scaled"], errors="coerce"
        ) * pd.to_numeric(data["instr_ret"], errors="coerce")
        r_cols.append(col)

    # ---- Blending: ERC weights (or equal weight)
    if use_erc and len(sleeves) > 1:
        R = data[r_cols].fillna(0.0).to_numpy()
        # sample covariance of sleeve returns
        cov = np.cov(R.T, ddof=1) if R.shape[0] > 1 else np.eye(len(sleeves))
        w = erc_weights(cov)
    else:
        w = np.ones(len(sleeves)) / len(sleeves)

    # ---- Composite position & optional vol target
    scaled_pos_cols = [f"{s}_pos_scaled" for s in sleeves]
    data["composite_pos_unlev"] = (data[scaled_pos_cols] @ w).clip(-cap, cap)

    if use_comp_vt:
        pnl_unlev = pd.to_numeric(
            data["composite_pos_unlev"], errors="coerce"
        ) * pd.to_numeric(data["instr_ret"], errors="coerce")
        # rolling realised vol (simple stdev over lookback)
        rv = pnl_unlev.rolling(comp_lookback).std() * np.sqrt(252.0)
        lev = (comp_target / rv).replace([np.inf, -np.inf], np.nan)
        lev = lev.clip(0.0, comp_lev_cap).fillna(1.0)
        data["composite_pos"] = (data["composite_pos_unlev"] * lev).clip(-cap, cap)
    else:
        data["composite_pos"] = data["composite_pos_unlev"]

    # ---- PnL, costs, equity (costs on what we actually trade)
    data["pnl_gross"] = pd.to_numeric(
        data["composite_pos"], errors="coerce"
    ) * pd.to_numeric(data["instr_ret"], errors="coerce")
    data["turnover"] = data["composite_pos"].diff().abs().fillna(0.0)
    data["cost"] = data["turnover"] * cost_bps
    data["pnl_net"] = data["pnl_gross"] - data["cost"]
    data["equity"] = (1.0 + data["pnl_net"].fillna(0.0)).cumprod()

    # ---- Summary stats
    pnl = pd.to_numeric(data["pnl_net"], errors="coerce")
    sharpe = (
        (np.nanmean(pnl) / np.nanstd(pnl) * np.sqrt(252.0))
        if np.nanstd(pnl) > 0
        else np.nan
    )
    a_ret = float(np.nanmean(pnl) * 252.0)
    a_vol = ann_vol(pnl)
    dd = float((1.0 - data["equity"] / data["equity"].cummax()).max())

    # ---- Diagnostics: per-sleeve vols (pre & post), correlations, weights
    post_vols = {}
    for s in sleeves:
        post_vols[s] = ann_vol(data[f"{s}_ret_scaled"])

    corr_df = data[r_cols].corr()
    weights_series = pd.Series(w, index=sleeves, name="erc_weight")

    diag_lines = []
    diag_lines.append("Composite v0.3 diagnostics")
    diag_lines.append(f"Sleeves: {', '.join(sleeves)}")
    diag_lines.append(f"Inputs dir: {input_dir}")
    diag_lines.append("\nPer-sleeve realised vol vs copper (pre-scale):")
    for s in sleeves:
        diag_lines.append(f"  {s:12s}: {pre_vols[s]:6.2%}")
    diag_lines.append("\nPer-sleeve realised vol vs copper (post-scale to ~target):")
    for s in sleeves:
        diag_lines.append(f"  {s:12s}: {post_vols[s]:6.2%}")
    diag_lines.append("\nERC weights:")
    for s in sleeves:
        diag_lines.append(f"  {s:12s}: {weights_series[s]:6.2%}")
    diag_lines.append("\nScales applied (target_vol / pre_vol):")
    for s in sleeves:
        diag_lines.append(f"  {s:12s}: {scales[s]:.4f}")
    diag_txt = "\n".join(diag_lines)

    summary = f"""
Composite v0.3 Summary
======================
Sleeves: {', '.join(sleeves)}
Inputs dir: {input_dir}

Blending: {'ERC (equal risk contribution)' if use_erc and len(sleeves)>1 else 'Equal-weight'}
Per-sleeve target vol: {per_sleeve_target_vol:.0%} vs copper
Composite vol target: {'ON ' + str(comp_target) if use_comp_vt else 'OFF'}
Leverage cap: {comp_lev_cap:.2f}, Lookback: {comp_lookback}d

Annualised Return: {a_ret:.2%}
Annualised Vol:    {a_vol:.2%}
Sharpe:            {sharpe if np.isfinite(sharpe) else float('nan'):.2f}
Max Drawdown:      {dd:.2%}
Costs:             {cfg.get('cost_bps', 1.5)} bps on composite turnover
ERC weights:       {', '.join([f'{s}:{weights_series[s]:.2%}' for s in sleeves])}
"""

    print(summary)

    # ---- Save outputs
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    data.to_csv(out_csv, index=False)
    with open(out_summary, "w") as f:
        f.write(summary)
    with open(out_diag_txt, "w") as f:
        f.write(diag_txt)
    corr_df.to_csv(out_corr_csv, index=True)


if __name__ == "__main__":
    main()
