# backtest_prices.py
# -------------------
# Backtests sleeves using:
#   - prices from VIEW 'prices_std' (date, px_3m, px_cash)
#   - positions from TABLE 'signals' (trend_signal, hook_signal)
# Positions in 'signals' are already shifted (trade next day).
#
# Outputs (to outputs/<Metal>/):
#   - equity_curves_prices.csv
#   - backtest_summary_prices.csv
#   - equity_trend.png, equity_hook.png, equity_combo.png
#
# Usage (from project root):
#   python src\backtest_prices.py --db .\Copper\quant.db --prices-table prices_std --signals-table signals
#
import argparse
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ANNUAL_DAYS = 252
TARGET_VOL = 0.10  # 10% annualised
VOL_WIN = 60  # rolling window for vol estimate (days)
TCOST_PER_TURN = 0.0002  # 2 bps per 1.0 notional turnover
LEVERAGE_CAP = 10.0


def compute_default_outdir(db_path: Path, explicit_outdir: Path | None) -> Path:
    if explicit_outdir:
        out = explicit_outdir
    else:
        project_root = Path(__file__).resolve().parent.parent
        out = project_root / "outputs"
    metal = db_path.parent.name or "default"
    outdir = out / metal
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def read_prices(con, prices_table: str) -> pd.DataFrame:
    df = pd.read_sql(
        f"SELECT * FROM {prices_table} ORDER BY date", con, parse_dates=["date"]
    )
    df = df.dropna(subset=["date"]).sort_values("date")
    df["px_3m"] = pd.to_numeric(df["px_3m"], errors="coerce")
    df = df.dropna(subset=["px_3m"])
    # Clamp history
    df = df[df["date"] >= pd.Timestamp("2008-01-01")]
    df = df.drop_duplicates(subset=["date"], keep="last")
    df = df.set_index("date")
    df["ret_1d"] = df["px_3m"].pct_change()
    return df


def read_signals(con, signals_table: str) -> pd.DataFrame:
    df = pd.read_sql(f"SELECT * FROM {signals_table}", con, parse_dates=["date"])
    if "date" in df.columns:
        df = df.dropna(subset=["date"]).sort_values("date").set_index("date")
    else:
        # if signals were written with date as index column named 'index'
        if "index" in df.columns:
            df["date"] = pd.to_datetime(df["index"])
            df = df.drop(columns=["index"]).set_index("date").sort_index()
        else:
            raise KeyError(
                "signals table must contain a 'date' column or an 'index' column with dates."
            )
    # Keep the essentials only
    keep = [c for c in df.columns if c in ("trend_signal", "hook_signal")]
    if not keep:
        raise KeyError(
            "signals table is missing 'trend_signal' and 'hook_signal'. Re-run build_hookcore.py."
        )
    return df[keep]


def align(prices: pd.DataFrame, signals: pd.DataFrame) -> pd.DataFrame:
    df = prices.join(signals, how="inner")
    return df.dropna(subset=["ret_1d"])


def ex_ante_leverage(
    returns: pd.Series, win=VOL_WIN, target_vol=TARGET_VOL, cap=LEVERAGE_CAP
) -> pd.Series:
    vol = returns.rolling(win).std() * np.sqrt(ANNUAL_DAYS)
    vol = vol.shift(1)  # ex-ante (use info up to t-1)
    lev = (target_vol / vol).clip(lower=0, upper=cap)
    return lev


def sleeve_pnl(df: pd.DataFrame, sig_col: str) -> pd.DataFrame:
    # gross position = ex-ante leverage * signal (already shifted in build_signals)
    lev = ex_ante_leverage(df["ret_1d"])
    pos = (lev * df[sig_col]).fillna(0.0)
    # turnover cost
    turn = (pos - pos.shift(1)).abs().fillna(0.0)
    cost = TCOST_PER_TURN * turn
    # pnl = position_t * ret_t - cost_t
    pnl = (pos * df["ret_1d"] - cost).fillna(0.0)
    out = pd.DataFrame(
        {f"{sig_col}_pos": pos, f"{sig_col}_turnover": turn, f"{sig_col}_pnl": pnl},
        index=df.index,
    )
    return out


def equity(pnl: pd.Series) -> pd.Series:
    return (1.0 + pnl).cumprod()


def max_drawdown(eq: pd.Series) -> float:
    roll_max = eq.cummax()
    dd = eq / roll_max - 1.0
    return -dd.min() if len(dd) else np.nan


def metrics(pnl: pd.Series, turn: pd.Series, label: str, window: str) -> dict:
    pnl = pnl.dropna()
    n = len(pnl)
    if n == 0:
        return {
            "sleeve": label,
            "window": window,
            "ann_return": np.nan,
            "ann_vol": np.nan,
            "sharpe": np.nan,
            "sortino": np.nan,
            "max_dd": np.nan,
            "hit_rate": np.nan,
            "win_loss": np.nan,
            "avg_turnover": np.nan,
            "days": 0,
        }
    eq = equity(pnl)
    cagr = eq.iloc[-1] ** (ANNUAL_DAYS / n) - 1.0
    vol = pnl.std() * np.sqrt(ANNUAL_DAYS)
    sharpe = (
        (pnl.mean() / pnl.std() * np.sqrt(ANNUAL_DAYS)) if pnl.std() > 0 else np.nan
    )
    downside = pnl[pnl < 0]
    dstd = downside.std() * np.sqrt(ANNUAL_DAYS) if len(downside) > 0 else np.nan
    sortino = (
        (pnl.mean() * np.sqrt(ANNUAL_DAYS) / dstd) if dstd and dstd > 0 else np.nan
    )
    mdd = max_drawdown(eq)
    hit = (pnl > 0).mean()
    avg_win = pnl[pnl > 0].mean()
    avg_loss = -pnl[pnl < 0].mean() if (pnl < 0).any() else np.nan
    wl = (avg_win / avg_loss) if avg_loss and avg_loss > 0 else np.nan
    avg_turn = turn.mean()
    return {
        "sleeve": label,
        "window": window,
        "ann_return": cagr,
        "ann_vol": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_dd": mdd,
        "hit_rate": hit,
        "win_loss": wl,
        "avg_turnover": avg_turn,
        "days": n,
    }


def slice_idx(df: pd.DataFrame, start: str, end: str) -> pd.Index:
    return df.index[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))]


def plot_equity(eq: pd.Series, out_path: Path, title: str):
    plt.figure()
    eq.plot()
    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel("Equity (start=1.0)")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--db", required=True, help="Path to quant.db (e.g. .\\Copper\\quant.db)"
    )
    ap.add_argument("--prices-table", default="prices_std")
    ap.add_argument("--signals-table", default="signals")
    ap.add_argument(
        "--outdir",
        default=None,
        help="Optional base outputs dir (default: outputs/<Metal>)",
    )
    args = ap.parse_args()

    db_path = Path(args.db).resolve()
    outdir = compute_default_outdir(
        db_path, Path(args.outdir).resolve() if args.outdir else None
    )

    with sqlite3.connect(db_path) as con:
        prices = read_prices(con, args.prices_table)
        signals = read_signals(con, args.signals_table)

    df = align(prices, signals)

    # build sleeve pnls
    t = sleeve_pnl(df, "trend_signal")
    h = sleeve_pnl(df, "hook_signal")

    pnl_trend = t["trend_signal_pnl"]
    pnl_hook = h["hook_signal_pnl"]
    turn_trend = t["trend_signal_turnover"]
    turn_hook = h["hook_signal_turnover"]

    # simple 50/50 combo
    pnl_combo = 0.5 * pnl_trend + 0.5 * pnl_hook

    # equity curves
    eq_trend = equity(pnl_trend)
    eq_hook = equity(pnl_hook)
    eq_combo = equity(pnl_combo)

    # save equity CSV
    eq_df = pd.DataFrame(
        {"eq_trend": eq_trend, "eq_hook": eq_hook, "eq_combo": eq_combo}
    )
    eq_csv = outdir / "equity_curves_prices.csv"
    eq_df.to_csv(eq_csv, index=True)
    print(f"[OK] Saved equity curves → {eq_csv}")

    # charts
    plot_equity(eq_trend, outdir / "equity_trend.png", "Trend Equity")
    plot_equity(eq_hook, outdir / "equity_hook.png", "Hook Equity")
    plot_equity(eq_combo, outdir / "equity_combo.png", "Combo Equity")
    print(f"[OK] Saved charts → {outdir}")

    # metrics across windows
    windows = {
        "All": (df.index.min().date().isoformat(), df.index.max().date().isoformat()),
        "IS_2008_2016": ("2008-01-01", "2016-12-31"),
        "OOS1_2017_2021": ("2017-01-01", "2021-12-31"),
        "OOS2_2022_present": ("2022-01-01", df.index.max().date().isoformat()),
    }

    rows = []
    for wname, (ws, we) in windows.items():
        mask = (df.index >= ws) & (df.index <= we)
        rows.append(metrics(pnl_trend[mask], turn_trend[mask], "trend", wname))
        rows.append(metrics(pnl_hook[mask], turn_hook[mask], "hook", wname))
        rows.append(
            metrics(
                pnl_combo[mask],
                (0.5 * turn_trend + 0.5 * turn_hook)[mask],
                "combo50",
                wname,
            )
        )

    summ = pd.DataFrame(rows)
    summ_path = outdir / "backtest_summary_prices.csv"
    summ.to_csv(summ_path, index=False)
    print(f"[OK] Saved summary → {summ_path}")


if __name__ == "__main__":
    main()
