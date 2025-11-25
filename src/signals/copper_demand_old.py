"""
Copper Demand Overlay - ADAPTED VERSION
Works with BaselineEqualWeight portfolio format.

Supports both YoY and QoQ momentum calculations for comparison.

Author: Kieran
Date: November 20, 2025
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict, Optional


def load_demand_data(filepath: str) -> pd.DataFrame:
    """
    Load and prepare Bloomberg Chinese demand proxy data.
    
    Args:
        filepath: Path to demand proxy file
        
    Returns:
        DataFrame with 'date' and 'demand_index' columns
    """
    if filepath.endswith('.csv'):
        demand = pd.read_csv(filepath, header=0)
    elif filepath.endswith('.xlsx') or filepath.endswith('.xls'):
        demand = pd.read_excel(filepath, header=0)
    else:
        raise ValueError(f"Unsupported file format: {filepath}")
    
    demand.columns = ['date', 'demand_index']
    demand['date'] = pd.to_datetime(demand['date'])
    demand = demand.sort_values('date').reset_index(drop=True)
    
    # Fix last date if it comes as month start (Bloomberg quirk)
    if demand['date'].iloc[-1].day == 1:
        demand.loc[demand.index[-1], 'date'] = (
            demand['date'].iloc[-1] + pd.offsets.MonthEnd(0)
        )
    
    return demand


def classify_regime_yoy(yoy_change: float) -> Optional[str]:
    """
    Classify regime based on YoY change (12-month).
    
    Regime Rules:
    - DECLINING: YoY < -2
    - RISING: YoY > 3
    - NEUTRAL: -2 ≤ YoY ≤ 3
    
    Args:
        yoy_change: Year-over-year change in demand index
        
    Returns:
        'RISING', 'NEUTRAL', 'DECLINING', or None
    """
    if pd.isna(yoy_change):
        return None
    
    if yoy_change < -2:
        return 'DECLINING'
    elif yoy_change > 3:
        return 'RISING'
    else:
        return 'NEUTRAL'


def classify_regime_qoq(qoq_change: float) -> Optional[str]:
    """
    Classify regime based on QoQ change (3-month).
    
    Regime Rules (adapted from YoY):
    - DECLINING: QoQ < -2
    - RISING: QoQ > 3
    - NEUTRAL: -2 ≤ QoQ ≤ 3
    
    Args:
        qoq_change: Quarter-over-quarter change in demand index
        
    Returns:
        'RISING', 'NEUTRAL', 'DECLINING', or None
    """
    if pd.isna(qoq_change):
        return None
    
    if qoq_change < -2:
        return 'DECLINING'
    elif qoq_change > 3:
        return 'RISING'
    else:
        return 'NEUTRAL'


def map_demand_regimes_to_daily(
    daily_data: pd.DataFrame,
    demand_data: pd.DataFrame,
    lag_months: int = 2,
    method: str = 'yoy'
) -> pd.DataFrame:
    """
    Map monthly demand regimes to daily trading data.
    
    Args:
        daily_data: DataFrame with 'date' column
        demand_data: DataFrame with 'date', 'demand_index' columns
        lag_months: Publication lag (0, 1, or 2)
        method: 'yoy' (12-month) or 'qoq' (3-month)
        
    Returns:
        daily_data with 'regime' and momentum change columns added
    """
    result = daily_data.copy()
    result['regime'] = None
    result['momentum_change'] = np.nan
    
    # Calculate momentum changes
    demand = demand_data.copy()
    
    if method == 'yoy':
        demand['momentum_change'] = demand['demand_index'] - demand['demand_index'].shift(12)
        demand['regime'] = demand['momentum_change'].apply(classify_regime_yoy)
    elif method == 'qoq':
        demand['momentum_change'] = demand['demand_index'] - demand['demand_index'].shift(3)
        demand['regime'] = demand['momentum_change'].apply(classify_regime_qoq)
    else:
        raise ValueError(f"Unknown method: {method}. Use 'yoy' or 'qoq'")
    
    # Filter to valid regimes
    demand_valid = demand[demand['regime'].notna()].copy().reset_index(drop=True)
    
    # Calculate when each month's data becomes available for trading
    demand_valid['available_date'] = demand_valid['date'].apply(
        lambda x: x + pd.offsets.MonthEnd(lag_months)
    )
    
    # Map each month's regime to daily trading period
    for idx in range(len(demand_valid)):
        regime = demand_valid.loc[idx, 'regime']
        momentum = demand_valid.loc[idx, 'momentum_change']
        
        # Start trading day after data becomes available
        start_date = demand_valid.loc[idx, 'available_date'] + pd.Timedelta(days=1)
        
        # Adjust if start_date falls on weekend
        while start_date.dayofweek >= 5:
            start_date += pd.Timedelta(days=1)
        
        # End date is when next month's data becomes available
        if idx < len(demand_valid) - 1:
            next_available = demand_valid.loc[idx+1, 'available_date']
            end_date = next_available
            
            while end_date.dayofweek >= 5:
                end_date -= pd.Timedelta(days=1)
        else:
            end_date = (
                demand_valid.loc[idx, 'available_date'] + pd.offsets.MonthEnd(1)
            )
            while end_date.dayofweek >= 5:
                end_date -= pd.Timedelta(days=1)
        
        # Assign regime to all trading days in this period
        mask = (result['date'] >= start_date) & (result['date'] <= end_date)
        result.loc[mask, 'regime'] = regime
        result.loc[mask, 'momentum_change'] = momentum
    
    return result


def apply_regime_scaling(
    position: float,
    regime: Optional[str],
    scale_factor: float = 1.3
) -> float:
    """
    Apply regime-based scaling to portfolio position.
    
    Args:
        position: Current portfolio position
        regime: 'RISING', 'NEUTRAL', or 'DECLINING'
        scale_factor: Base scaling factor
        
    Returns:
        scaled_position
    """
    if regime is None or pd.isna(regime) or regime == 'NEUTRAL':
        return position
    
    if regime == 'RISING':
        if position > 0:
            return position * scale_factor
        else:
            return position / scale_factor
    
    elif regime == 'DECLINING':
        if position > 0:
            return position / scale_factor
        else:
            return position * scale_factor
    
    return position


def apply_overlay(
    baseline_data: pd.DataFrame,
    demand_data: pd.DataFrame,
    lag_months: int = 2,
    scale_factor: float = 1.3,
    transaction_cost_bps: float = 3.0,
    method: str = 'yoy'
) -> Tuple[pd.DataFrame, Dict]:
    """
    Apply Chinese demand overlay to baseline portfolio.
    
    ADAPTED for BaselineEqualWeight format which has:
    - portfolio_pos (not 'pos')
    - pnl_gross (not 'pnl_net')
    - No 'cost' column
    
    Args:
        baseline_data: DataFrame with baseline strategy
        demand_data: DataFrame with Chinese demand index
        lag_months: Publication lag (default=2)
        scale_factor: Regime scaling factor (default=1.3)
        transaction_cost_bps: Transaction costs in bps (default=3.0)
        method: 'yoy' or 'qoq' for momentum calculation
        
    Returns:
        Tuple of (overlay_df, metrics)
    """
    # Standardize column names for the overlay
    overlay = baseline_data.copy()
    overlay['pos'] = overlay['portfolio_pos']  # Rename for internal use
    overlay['pnl_baseline'] = overlay['pnl_gross']  # Use gross as baseline
    
    # Map regimes to daily data
    overlay = map_demand_regimes_to_daily(overlay, demand_data, lag_months, method)
    
    # Calculate scaled positions
    overlay['pos_scaled'] = overlay.apply(
        lambda row: apply_regime_scaling(row['pos'], row['regime'], scale_factor),
        axis=1
    )
    
    # Calculate overlay costs (only from regime transitions)
    overlay['regime_change'] = (
        overlay['regime'] != overlay['regime'].shift(1)
    ).astype(float)
    overlay['pos_diff_from_baseline'] = (
        overlay['pos_scaled'] - overlay['pos']
    ).abs()
    overlay['cost_overlay'] = (
        overlay['regime_change'] * 
        overlay['pos_diff_from_baseline'] * 
        (transaction_cost_bps / 10000)
    )
    
    # Calculate overlay PnL
    overlay['pos_for_ret_scaled'] = overlay['pos_scaled'].shift(1).fillna(0)
    overlay['pnl_gross_overlay'] = overlay['ret'] * overlay['pos_for_ret_scaled']
    overlay['pnl_net_overlay'] = (
        overlay['pnl_gross_overlay'] - 
        overlay['cost_overlay']
    )
    
    # Calculate metrics for valid regime periods only
    # Filter to rows with BOTH regime AND valid pnl data
    valid = overlay[(overlay['regime'].notna()) & (overlay['pnl_gross'].notna())].copy()
    
    if len(valid) == 0:
        raise ValueError("No valid regime periods found")
    
    # CRITICAL: Baseline metrics should use the SAME baseline data for all lag tests
    # The baseline portfolio is the same regardless of overlay lag
    # We just need to calculate it on the period where we have regime data
    baseline_returns = valid['pnl_gross'].values  # Use original column name
    
    # Store the date range for transparency
    test_period_start = valid['date'].min()
    test_period_end = valid['date'].max()
    baseline_sharpe = (
        np.mean(baseline_returns) / np.std(baseline_returns) * np.sqrt(252)
    )
    baseline_total = np.sum(baseline_returns) * 100
    
    # Overlay metrics - filter out NaN values
    overlay_returns = valid['pnl_net_overlay'].dropna().values
    overlay_sharpe = (
        np.mean(overlay_returns) / np.std(overlay_returns) * np.sqrt(252)
    )
    overlay_total = np.sum(overlay_returns) * 100
    
    # Drawdowns
    baseline_cum = np.cumsum(baseline_returns)
    baseline_dd = np.min(baseline_cum - np.maximum.accumulate(baseline_cum)) * 100
    
    # Use dropna for overlay to avoid NaN in cumsum
    overlay_returns_clean = valid['pnl_net_overlay'].dropna().values
    overlay_cum = np.cumsum(overlay_returns_clean)
    overlay_dd = np.min(overlay_cum - np.maximum.accumulate(overlay_cum)) * 100
    
    # Regime distribution
    regime_counts = valid['regime'].value_counts()
    
    # Compile metrics
    metrics = {
        'method': method.upper(),
        'baseline': {
            'sharpe': baseline_sharpe,
            'total_return_pct': baseline_total,
            'max_drawdown_pct': baseline_dd,
            'days': len(valid)
        },
        'overlay': {
            'sharpe': overlay_sharpe,
            'total_return_pct': overlay_total,
            'max_drawdown_pct': overlay_dd,
            'days': len(valid)
        },
        'improvement': {
            'sharpe_diff': overlay_sharpe - baseline_sharpe,
            'sharpe_pct': ((overlay_sharpe / baseline_sharpe) - 1) * 100 if baseline_sharpe != 0 else 0,
            'return_diff_pct': overlay_total - baseline_total,
            'dd_diff_pct': overlay_dd - baseline_dd
        },
        'regime_distribution': {
            'DECLINING': int(regime_counts.get('DECLINING', 0)),
            'NEUTRAL': int(regime_counts.get('NEUTRAL', 0)),
            'RISING': int(regime_counts.get('RISING', 0))
        },
        'parameters': {
            'lag_months': lag_months,
            'scale_factor': scale_factor,
            'transaction_cost_bps': transaction_cost_bps
        }
    }
    
    return overlay, metrics


def format_metrics_summary(metrics: Dict) -> str:
    """Format metrics into readable summary string."""
    lines = [
        "="*80,
        f"COPPER DEMAND OVERLAY - {metrics['method']} METHOD",
        "="*80,
        "",
        "Baseline Performance:",
        f"  Sharpe Ratio:    {metrics['baseline']['sharpe']:.3f}",
        f"  Total Return:    {metrics['baseline']['total_return_pct']:.2f}%",
        f"  Max Drawdown:    {metrics['baseline']['max_drawdown_pct']:.2f}%",
        f"  Trading Days:    {metrics['baseline']['days']:,}",
        "",
        "Overlay Performance:",
        f"  Sharpe Ratio:    {metrics['overlay']['sharpe']:.3f}",
        f"  Total Return:    {metrics['overlay']['total_return_pct']:.2f}%",
        f"  Max Drawdown:    {metrics['overlay']['max_drawdown_pct']:.2f}%",
        "",
        "Improvement:",
        f"  Sharpe:          +{metrics['improvement']['sharpe_diff']:.3f} "
        f"({metrics['improvement']['sharpe_pct']:+.1f}%)",
        f"  Return:          +{metrics['improvement']['return_diff_pct']:.2f}%",
        f"  Max Drawdown:    {metrics['improvement']['dd_diff_pct']:+.2f}%",
        "",
        "Regime Distribution:",
        f"  DECLINING:       {metrics['regime_distribution']['DECLINING']:,} days "
        f"({metrics['regime_distribution']['DECLINING']/metrics['baseline']['days']*100:.1f}%)",
        f"  NEUTRAL:         {metrics['regime_distribution']['NEUTRAL']:,} days "
        f"({metrics['regime_distribution']['NEUTRAL']/metrics['baseline']['days']*100:.1f}%)",
        f"  RISING:          {metrics['regime_distribution']['RISING']:,} days "
        f"({metrics['regime_distribution']['RISING']/metrics['baseline']['days']*100:.1f}%)",
        "",
        "Parameters:",
        f"  Momentum Method: {metrics['method']}",
        f"  Publication Lag: {metrics['parameters']['lag_months']} months",
        f"  Scale Factor:    {metrics['parameters']['scale_factor']:.1f}x",
        f"  Transaction Cost: {metrics['parameters']['transaction_cost_bps']:.1f} bps",
        "="*80
    ]
    
    return "\n".join(lines)