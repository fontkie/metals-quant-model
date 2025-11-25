# src/core/execution.py
"""
Execution Layer - Layer 4 of 4-Layer Architecture

Purpose: Apply transaction costs ONCE and calculate final PnL
Input: Vol-targeted positions from Layer 2/3
Output: PnL series + performance metrics

CRITICAL: Costs applied ONCE on net portfolio position changes,
not separately per sleeve. This is institutional standard.

Author: Systematic Trading Team
Date: November 2025
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict


def execute_single_sleeve(
    positions: pd.Series,
    returns: pd.Series,
    cost_bps: float = 3.0,
    expected_vol: float = 0.10,
) -> Tuple[pd.DataFrame, Dict, Dict, Dict]:
    """
    Execute single sleeve strategy with transaction costs.
    
    Layer 4 Logic:
        1. Calculate trades (position changes)
        2. Apply costs on |trade|
        3. Calculate gross PnL (lagged position × return)
        4. Calculate net PnL (gross - costs)
        5. Calculate all performance metrics
        6. Validate execution correctness
    
    Args:
        positions: Vol-targeted positions from Layer 2
        returns: Underlying asset returns
        cost_bps: One-way transaction cost in basis points (default: 3.0)
        expected_vol: Expected strategy volatility for validation
        
    Returns:
        result_df: DataFrame with all execution columns
        metrics: Performance metrics dict
        turnover_metrics: Turnover statistics dict
        validation: Validation checks dict
    """
    
    # Create result DataFrame
    result = pd.DataFrame(index=returns.index)
    result["pos"] = positions
    
    # ========== STEP 1: CALCULATE TRADES ==========
    # Trade = change in position
    result["trade"] = result["pos"].diff()
    result["trade"] = result["trade"].fillna(0)
    
    # ========== STEP 2: APPLY TRANSACTION COSTS ==========
    # Cost = |trade| × cost_bps / 10000
    # One-way cost: pay when position changes
    result["cost"] = -result["trade"].abs() * (cost_bps / 10000)
    
    # ========== STEP 3: CALCULATE GROSS PNL ==========
    # T→T+1 accrual: position at T-1 earns return at T
    result["pos_for_ret"] = result["pos"].shift(1)
    result["pnl_gross"] = result["pos_for_ret"] * returns
    
    # ========== STEP 4: CALCULATE NET PNL ==========
    result["pnl_net"] = result["pnl_gross"] + result["cost"]
    
    # ========== STEP 5: CALCULATE METRICS ==========
    metrics = calculate_metrics(result, expected_vol)
    
    # ========== STEP 6: CALCULATE TURNOVER METRICS ==========
    turnover_metrics = calculate_turnover(result, cost_bps)
    
    # ========== STEP 7: VALIDATE EXECUTION ==========
    validation = validate_execution(result, returns)
    
    return result, metrics, turnover_metrics, validation


def calculate_metrics(df: pd.DataFrame, expected_vol: float = 0.10) -> Dict:
    """
    Calculate performance metrics from PnL series.
    
    Metrics calculated:
        - Annual return (geometric)
        - Annual volatility
        - Sharpe ratio
        - Maximum drawdown
        - Gross vs net comparison
    """
    
    # Remove warmup period (first 63 days)
    df_clean = df.iloc[63:].copy()
    
    # Gross metrics
    gross_cum_ret = (1 + df_clean["pnl_gross"]).cumprod() - 1
    gross_total_ret = gross_cum_ret.iloc[-1]
    gross_annual_ret = (1 + gross_total_ret) ** (252 / len(df_clean)) - 1
    gross_annual_vol = df_clean["pnl_gross"].std() * np.sqrt(252)
    gross_sharpe = gross_annual_ret / gross_annual_vol if gross_annual_vol > 0 else 0
    
    # Net metrics
    net_cum_ret = (1 + df_clean["pnl_net"]).cumprod() - 1
    net_total_ret = net_cum_ret.iloc[-1]
    net_annual_ret = (1 + net_total_ret) ** (252 / len(df_clean)) - 1
    net_annual_vol = df_clean["pnl_net"].std() * np.sqrt(252)
    net_sharpe = net_annual_ret / net_annual_vol if net_annual_vol > 0 else 0
    
    # Max drawdown (net)
    cumulative = (1 + df_clean["pnl_net"]).cumprod()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = drawdown.min()
    
    # Cost impact
    cost_drag_sharpe = gross_sharpe - net_sharpe
    cost_drag_return = gross_annual_ret - net_annual_ret
    
    # Handle date formatting (works for both datetime and integer indices)
    try:
        start_date = df_clean.index[0].strftime("%Y-%m-%d")
        end_date = df_clean.index[-1].strftime("%Y-%m-%d")
    except AttributeError:
        # Index is not datetime - use position instead
        start_date = f"row_{df_clean.index[0]}"
        end_date = f"row_{df_clean.index[-1]}"
    
    metrics = {
        # Net (primary)
        "sharpe": net_sharpe,  # Changed from "net_sharpe" to match expected key
        "annual_return": net_annual_ret,
        "annual_vol": net_annual_vol,
        "max_drawdown": max_drawdown,
        
        # Gross (for comparison)
        "gross_sharpe": gross_sharpe,
        "gross_annual_return": gross_annual_ret,
        
        # Cost impact
        "cost_drag_sharpe": cost_drag_sharpe,
        "cost_drag_return": cost_drag_return,
        
        # Validation
        "observations": len(df_clean),
        "start_date": start_date,
        "end_date": end_date,
    }
    
    return metrics


def calculate_turnover(df: pd.DataFrame, cost_bps: float) -> Dict:
    """
    Calculate turnover statistics.
    
    Turnover metrics:
        - Annual turnover (trades per year)
        - Mean trade size
        - Max trade size
        - Total costs
    """
    
    df_clean = df.iloc[63:].copy()
    
    # Turnover (sum of absolute trades)
    total_turnover = df_clean["trade"].abs().sum()
    years = len(df_clean) / 252
    annual_turnover = total_turnover / years
    
    # Trade statistics
    trades = df_clean[df_clean["trade"].abs() > 0]["trade"]
    mean_trade_size = trades.abs().mean() if len(trades) > 0 else 0
    max_trade_size = trades.abs().max() if len(trades) > 0 else 0
    
    # Cost analysis
    total_cost = df_clean["cost"].sum()
    annual_cost = total_cost / years
    
    # Cost as % of gross PnL
    gross_pnl_sum = df_clean["pnl_gross"].sum()
    cost_as_pct_gross = abs(total_cost / gross_pnl_sum) if gross_pnl_sum != 0 else 0
    
    # Implied holding period
    # If turnover = 10x, average holding = 252/10 = 25 days
    avg_holding_days = 252 / annual_turnover if annual_turnover > 0 else np.inf
    
    turnover_metrics = {
        "annual_turnover": annual_turnover,
        "mean_trade_size": mean_trade_size,
        "max_trade_size": max_trade_size,
        "trades_per_year": len(trades) / years,
        "annual_cost": annual_cost,
        "cost_as_pct_gross": cost_as_pct_gross,
        "avg_holding_days": avg_holding_days,
    }
    
    return turnover_metrics


def validate_execution(df: pd.DataFrame, returns: pd.Series) -> Dict:
    """
    Validate execution correctness.
    
    Checks:
        1. T→T+1 accrual (pos_for_ret = pos.shift(1))
        2. Trade calculation (trade = pos.diff())
        3. Gross PnL calculation
        4. Costs never positive
        5. No NaN in critical columns
    """
    
    validation = {}
    
    # Check 1: T→T+1 accrual
    pos_for_ret_check = df["pos"].shift(1)
    validation["t_plus_1_accrual"] = np.allclose(
        df["pos_for_ret"].fillna(0), 
        pos_for_ret_check.fillna(0),
        rtol=1e-10
    )
    
    # Check 2: Trade calculation
    trade_check = df["pos"].diff()
    validation["trade_calculation"] = np.allclose(
        df["trade"].fillna(0),
        trade_check.fillna(0),
        rtol=1e-10
    )
    
    # Check 3: Gross PnL calculation
    pnl_check = df["pos_for_ret"] * returns
    validation["pnl_gross_calculation"] = np.allclose(
        df["pnl_gross"].fillna(0),
        pnl_check.fillna(0),
        rtol=1e-10
    )
    
    # Check 4: Costs never positive
    validation["costs_negative_or_zero"] = (df["cost"] <= 0).all()
    
    # Check 5: No NaN in PnL (after warmup)
    df_clean = df.iloc[63:]
    validation["no_nan_in_pnl"] = not df_clean["pnl_net"].isna().any()
    
    # Check 6: Net PnL = Gross + Cost
    net_check = df["pnl_gross"] + df["cost"]
    validation["net_pnl_calculation"] = np.allclose(
        df["pnl_net"].fillna(0),
        net_check.fillna(0),
        rtol=1e-10
    )
    
    return validation


def format_validation_report(validation: Dict) -> str:
    """
    Format validation results for printing.
    """
    report = []
    report.append("\nExecution Validation:")
    report.append("=" * 60)
    
    for check, passed in validation.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        report.append(f"  {status}: {check}")
    
    all_passed = all(validation.values())
    report.append("=" * 60)
    
    if all_passed:
        report.append("✅ All validation checks passed!")
    else:
        report.append("❌ Some validation checks failed - review execution logic")
    
    return "\n".join(report)