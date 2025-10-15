# src/build_trend.py
import argparse
import math
import os
from typing import Optional, Union

import numpy as np
import pandas as pd


# =========================
# Defaults / Global Params
# =========================
TARGET_VOL_ANNUAL = 0.10  # 10% sleeve vol
ROLL_DAYS = 21  # vol lookback (trading days)
LEVERAGE_CAP = 3.0  # max absolute leverage
TURNOVER_COST_BPS = 1.5  # per unit turnover (bps)
APPLY_T_PLUS_1 = True  # apply orders the next trading day

# Production signal defaults
PROD_LOOKBACKS = [20, 60, 120]
DEFAULT_MODE = "MOM"  # "SMA", "MOM", or "BOTH"
DEFAULT_CADENCE = "MON_WED"  # "DAILY", "MON_WED", "WEEKLY_WED", "FORTNIGHTLY_WED"
DEFAULT_QUIET_Q = 0.0  # OFF by default (enable with >0, e.g. 0.5–0.7)

POPULAR_MA = [5, 10, 50, 100, 200]  # diagnostics only; not used in composite

# IS/OOS split per repo convention
IS_START = pd.Timestamp("2008-01-01")
IS_END = pd.Timestamp("2017-12-31")
OOS_START = pd.Timestamp("2018-01-01")


# =========================
# Loaders
# =========================
def _standardise_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]
    return out


def _load_from_tabular(
    path: str,
    price_col: str = "price",
    date_col: str = "date",
    sheet: Optional[Union[str, int]] = None,
) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(path)
    elif ext in (".xlsx", ".xls"):
        try:
            df = pd.read_excel(path, sheet_name=sheet)
        except ImportError as e:
            raise ImportError(
                "Reading Excel requires 'openpyxl' (for .xlsx) or 'xlrd' (legacy .xls). "
                "Install with: pip install openpyxl"
            ) from e
    else:
        raise ValueError(f"Unsupported file extension '{ext}'. Use .csv or .xlsx/.xls")

    df = _standardise_columns(df)
    if date_col.lower() not in df.columns:
        raise ValueError(
            f"Could not find date column '{date_col}' in {list(df.columns)}"
        )
    if price_col.lower() not in df.columns:
        raise ValueError(
            f"Could not find price column '{price_col}' in {list(df.columns)}"
        )

    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df[date_col.lower()], errors="coerce"),
            "price": pd.to_numeric(df[price_col.lower()], errors="coerce"),
        }
    ).dropna(subset=["date", "price"])

    out = out.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    if (out["price"] <= 0).any():
        raise ValueError(
            "Non-positive prices detected; please validate the input series."
        )
    return out


def _load_from_sqlite(db_path: str, table: str, symbol: str) -> pd.DataFrame:
    import sqlite3

    q = f"""
    SELECT date, price
    FROM {table}
    WHERE symbol = ?
    ORDER BY date ASC
    """
    with sqlite3.connect(db_path) as con:
        df = pd.read_sql_query(q, con, params=[symbol])

    df = _standardise_columns(df)
    if "date" not in df.columns or "price" not in df.columns:
        raise ValueError("SQLite table must have columns: date, price")

    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df["date"], errors="coerce"),
            "price": pd.to_numeric(df["price"], errors="coerce"),
        }
    ).dropna(subset=["date", "price"])

    return out.sort_values("date").reset_index(drop=True)


# =========================
# Signal + Portfolio Logic
# =========================
def _realized_vol_daily(ret_log: pd.Series, win: int) -> pd.Series:
    return ret_log.rolling(win).std()


def _realized_vol_annual(ret_log: pd.Series, win: int) -> pd.Series:
    return _realized_vol_daily(ret_log, win) * math.sqrt(252.0)


def _sma(sig: pd.Series, n: int) -> pd.Series:
    return sig.rolling(n, min_periods=n).mean()


def _mom_log(px: pd.Series, n: int) -> pd.Series:
    return np.log(px / px.shift(n))


def _majority_vote(df_signs: pd.DataFrame) -> pd.Series:
    s = df_signs.sum(axis=1)
    return pd.Series(np.where(s > 0, 1, np.where(s < 0, -1, 0)), index=df_signs.index)


def _cadence_flag(dates: pd.Series, cadence: str) -> pd.Series:
    wd = dates.dt.weekday  # Mon=0 ... Fri=4
    if cadence == "DAILY":
        return pd.Series(1, index=dates.index)
    if cadence == "MON_WED":
        return ((wd == 0) | (wd == 2)).astype(int)
    if cadence == "WEEKLY_WED":
        return (wd == 2).astype(int)
    if cadence == "FORTNIGHTLY_WED":
        week = dates.dt.isocalendar().week.astype(int)
        return ((wd == 2) & (week % 2 == 0)).astype(int)
    raise ValueError("Unknown cadence")


def build_trend(
    df_prices: pd.DataFrame,
    prod_lookbacks=PROD_LOOKBACKS,
    mode: str = DEFAULT_MODE,  # "SMA" | "MOM" | "BOTH"
    cadence: str = DEFAULT_CADENCE,  # "DAILY" | "MON_WED" | "WEEKLY_WED" | "FORTNIGHTLY_WED"
    quiet_q: float = DEFAULT_QUIET_Q,  # OFF if 0.0; else threshold multiplier
) -> pd.DataFrame:

    df = df_prices.copy().sort_values("date").reset_index(drop=True)
    df["ret_log"] = np.log(df["price"] / df["price"].shift(1))

    # Feature construction
    for n in prod_lookbacks:
        df[f"sma_{n}"] = _sma(df["price"], n)
        df[f"mom_{n}"] = _mom_log(df["price"], n)

    # Signs per family
    sma_signs = []
    mom_signs = []
    for n in prod_lookbacks:
        sma_sig = np.sign((df["price"] / df[f"sma_{n}"]) - 1.0)
        mom_sig = np.sign(df[f"mom_{n}"])
        df[f"sma_sig_{n}"] = (
            pd.Series(sma_sig).replace([np.inf, -np.inf], np.nan).fillna(0).astype(int)
        )
        df[f"mom_sig_{n}"] = (
            pd.Series(mom_sig).replace([np.inf, -np.inf], np.nan).fillna(0).astype(int)
        )
        sma_signs.append(df[f"sma_sig_{n}"])
        mom_signs.append(df[f"mom_sig_{n}"])

    # Family votes
    df["raw_signal_sma"] = _majority_vote(pd.concat(sma_signs, axis=1)).astype(int)
    df["raw_signal_mom"] = _majority_vote(pd.concat(mom_signs, axis=1)).astype(int)

    mode_u = mode.upper()
    if mode_u == "SMA":
        raw = df["raw_signal_sma"]
    elif mode_u == "MOM":
        raw = df["raw_signal_mom"]
    else:
        raw = _majority_vote(df[["raw_signal_sma", "raw_signal_mom"]])

    # Optional quiet-market filter (OFF when quiet_q == 0.0)
    # Require |mom_N| > quiet_q * daily_vol for a horizon to "count"; otherwise zero out its vote.
    if quiet_q and quiet_q > 0.0:
        daily_vol = _realized_vol_daily(df["ret_log"], ROLL_DAYS)
        votes = []
        for n in prod_lookbacks:
            strong = (df[f"mom_{n}"].abs() > quiet_q * daily_vol).astype(int)
            vote = df[f"mom_sig_{n}"] * strong  # use MOM family for strength gating
            votes.append(vote)
        gated = _majority_vote(pd.concat(votes, axis=1))
        raw = pd.Series(
            np.where(gated != 0, np.sign(gated), 0), index=raw.index
        ).astype(int)

    df["raw_signal"] = raw

    # Vol targeting
    df["roll_vol21"] = _realized_vol_annual(df["ret_log"], ROLL_DAYS)
    with np.errstate(divide="ignore", invalid="ignore"):
        lev = TARGET_VOL_ANNUAL / df["roll_vol21"]
    lev = pd.Series(lev, index=df.index).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    df["leverage"] = lev.clip(-LEVERAGE_CAP, LEVERAGE_CAP)
    df["desired_pos"] = df["raw_signal"] * df["leverage"].clip(
        -LEVERAGE_CAP, LEVERAGE_CAP
    )

    # Execution schedule + T+1
    df["rebalance_flag"] = _cadence_flag(df["date"], cadence)
    df["_apply_pos"] = np.nan
    df["position"] = 0.0

    last_pos = 0.0
    for i in range(len(df)):
        # Apply any pending T+1 first
        if APPLY_T_PLUS_1 and pd.notna(df.at[i, "_apply_pos"]):
            last_pos = float(df.at[i, "_apply_pos"])
            df.at[i, "_apply_pos"] = np.nan

        # If today is a rebalance day, schedule new desired_pos
        if df.at[i, "rebalance_flag"] == 1:
            new_pos = float(df.at[i, "desired_pos"])
            if APPLY_T_PLUS_1:
                if i + 1 < len(df):
                    df.at[i + 1, "_apply_pos"] = new_pos
            else:
                last_pos = new_pos

        df.at[i, "position"] = last_pos

    # Costs & PnL
    df["turnover"] = df["position"].diff().abs().fillna(0.0)
    df["cost"] = (TURNOVER_COST_BPS * 1e-4) * df["turnover"]
    df["pnl_gross"] = df["position"].shift(1).fillna(0.0) * df["ret_log"].fillna(0.0)
    df["pnl"] = df["pnl_gross"] - df["cost"]
    df["cum_pnl"] = df["pnl"].cumsum()

    # Trim warmup
    warmup = max(max(PROD_LOOKBACKS), ROLL_DAYS) + 2
    out = df.iloc[warmup:].reset_index(drop=True).drop(columns=["_apply_pos"])
    return out


# =========================
# Metrics / Outputs
# =========================
def _ann_stats(p: pd.Series) -> tuple[float, float, float]:
    ann_pnl = float(p.mean() * 252)
    ann_vol = float(p.std() * math.sqrt(252))
    sr = float(ann_pnl / (ann_vol + 1e-12))
    return ann_pnl, ann_vol, sr


def _max_dd(eq: pd.Series) -> float:
    roll_max = eq.cummax()
    dd = eq - roll_max
    return float(dd.min())


def _write_outputs(dfr: pd.DataFrame, out_path: str, sleeve_name: str) -> None:
    # 1) Daily series
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    dfr.to_csv(out_path, index=False)

    # 2) Equity curves (ALL/IS/OOS)
    is_slice = dfr[dfr["date"].between(IS_START, IS_END)]
    oos_slice = dfr[dfr["date"] >= OOS_START]

    eq_all = dfr[["date", "cum_pnl"]].copy()
    eq_all["segment"] = "ALL"
    eq_is = is_slice[["date", "cum_pnl"]].copy()
    eq_is["segment"] = "IS"
    eq_oos = oos_slice[["date", "cum_pnl"]].copy()
    eq_oos["segment"] = "OOS"
    eq_curves = pd.concat([eq_all, eq_is, eq_oos], axis=0, ignore_index=True)

    eq_path = os.path.join(os.path.dirname(out_path), "equity_curves.csv")
    eq_curves.to_csv(eq_path, index=False)

    # 3) Summary metrics
    all_stats = _ann_stats(dfr["pnl"])
    is_stats = _ann_stats(is_slice["pnl"]) if len(is_slice) else (float("nan"),) * 3
    oos_stats = _ann_stats(oos_slice["pnl"]) if len(oos_slice) else (float("nan"),) * 3

    metrics = pd.DataFrame(
        [
            {
                "Sleeve": sleeve_name,
                "Sharpe_ALL": all_stats[2],
                "Vol_ALL": all_stats[1],
                "MaxDD_ALL": _max_dd(dfr["cum_pnl"]),
                "Sharpe_IS": is_stats[2],
                "Vol_IS": is_stats[1],
                "MaxDD_IS": (
                    _max_dd(is_slice["cum_pnl"] - is_slice["cum_pnl"].iloc[0])
                    if len(is_slice)
                    else float("nan")
                ),
                "Sharpe_OOS": oos_stats[2],
                "Vol_OOS": oos_stats[1],
                "MaxDD_OOS": (
                    _max_dd(oos_slice["cum_pnl"] - oos_slice["cum_pnl"].iloc[0])
                    if len(oos_slice)
                    else float("nan")
                ),
                "AvgDailyTurnover": float(dfr["turnover"].mean()),
                "%DaysInPosition": float((dfr["position"].abs() > 1e-9).mean()) * 100.0,
            }
        ]
    )

    m_path = os.path.join(os.path.dirname(out_path), "summary_metrics.csv")
    metrics.to_csv(m_path, index=False)

    print(f"Wrote:\n - {out_path}\n - {eq_path}\n - {m_path}")


# =========================
# CLI
# =========================
def main() -> None:
    p = argparse.ArgumentParser(
        description="Build TrendCore sleeve (momentum) for copper 3M."
    )
    # Primary file input (csv/xlsx)
    p.add_argument(
        "--file",
        type=str,
        default=None,
        help="Path to CSV/XLSX with a date column and a price series",
    )
    p.add_argument(
        "--sheet", type=str, default=None, help="Excel sheet name (optional)"
    )
    p.add_argument(
        "--price_col",
        type=str,
        default="price",
        help="Column name for price (e.g. copper_lme_3mo)",
    )
    p.add_argument(
        "--date_col",
        type=str,
        default="date",
        help="Column name for the date (default: 'date')",
    )
    # Back-compat
    p.add_argument(
        "--csv", type=str, default=None, help="[Deprecated] Use --file instead"
    )
    # SQLite alternative
    p.add_argument("--sql", type=str, default=None, help="Path to SQLite DB")
    p.add_argument(
        "--table",
        type=str,
        default="prices",
        help="SQLite table name (default: prices)",
    )
    p.add_argument(
        "--symbol", type=str, default="COPPER", help="Symbol to query from SQLite"
    )
    # Signal + execution options
    p.add_argument(
        "--mode",
        type=str,
        default=DEFAULT_MODE,
        choices=["SMA", "MOM", "BOTH"],
        help="Signal family (default MOM)",
    )
    p.add_argument(
        "--cadence",
        type=str,
        default=DEFAULT_CADENCE,
        choices=["DAILY", "MON_WED", "WEEKLY_WED", "FORTNIGHTLY_WED"],
        help="Rebalance cadence",
    )
    p.add_argument(
        "--quiet_q",
        type=float,
        default=DEFAULT_QUIET_Q,
        help="Quiet-market filter multiplier (0=OFF; try 0.5–0.7 to enable)",
    )
    # Outputs
    p.add_argument(
        "--out",
        type=str,
        default="outputs/copper/trend/daily_series.csv",
        help="Output CSV path for daily series",
    )
    args = p.parse_args()

    # Resolve input
    if args.file or args.csv:
        path = args.file if args.file else args.csv
        dfp = _load_from_tabular(
            path, price_col=args.price_col, date_col=args.date_col, sheet=args.sheet
        )
    elif args.sql:
        dfp = _load_from_sqlite(args.sql, args.table, args.symbol)
    else:
        raise SystemExit("Provide --file (CSV/XLSX) or (--sql, --table, --symbol).")

    # Build & write
    dfr = build_trend(
        dfp,
        prod_lookbacks=PROD_LOOKBACKS,
        mode=args.mode,
        cadence=args.cadence,
        quiet_q=args.quiet_q,
    )
    _write_outputs(
        dfr,
        args.out,
        sleeve_name=f"TrendCore {PROD_LOOKBACKS} {args.mode} (cadence={args.cadence}, quiet_q={args.quiet_q})",
    )

    # Console summary
    ann_pnl = dfr["pnl"].mean() * 252
    ann_vol = dfr["pnl"].std() * math.sqrt(252)
    sr = ann_pnl / (ann_vol + 1e-12)
    avg_turnover = dfr["turnover"].mean()
    pct_in_pos = (dfr["position"].abs() > 1e-9).mean() * 100.0

    print(
        f"[TrendCore] rows={len(dfr)}  SR={sr:0.2f}  ann_vol={ann_vol:0.2%}  avg_daily_turnover={avg_turnover:0.3f}  %in_pos={pct_in_pos:0.1f}%"
    )
    print(
        f"Wrote daily_series/equity_curves/summary_metrics under {os.path.dirname(args.out)}"
    )


if __name__ == "__main__":
    main()
