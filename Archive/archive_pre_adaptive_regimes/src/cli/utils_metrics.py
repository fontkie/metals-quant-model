# src/utils_metrics.py
from __future__ import annotations
import numpy as np
import pandas as pd

TRADING_DAYS = 252

def ann_vol(ret: pd.Series, ddof: int = 0) -> float:
    """
    Annualized volatility for daily returns.
    ret: daily returns as pd.Series (NaNs allowed)
    """
    x = pd.Series(ret).dropna()
    return float(x.std(ddof=ddof) * np.sqrt(TRADING_DAYS))

def max_drawdown(equity: pd.Series) -> float:
    """
    Max drawdown given an equity curve (level, not returns).
    Returns a negative number (e.g., -0.228 for -22.8%).
    """
    x = pd.Series(equity).fillna(method="ffill")
    peak = x.cummax()
    dd = x / peak - 1.0
    return float(dd.min())

def worst_dd_window(ret: pd.Series) -> tuple[pd.Timestamp, pd.Timestamp, float]:
    """
    Returns (peak_date, trough_date, max_dd) from daily returns.
    """
    eq = (1 + pd.Series(ret).fillna(0.0)).cumprod()
    peak_idx = eq.cummax().idxmax()
    trough_idx = (eq / eq.cummax() - 1.0).idxmin()
    max_dd = (eq.loc[trough_idx] / eq.loc[:trough_idx].max()) - 1.0
    return (pd.to_datetime(peak_idx), pd.to_datetime(trough_idx), float(max_dd))
