"""
Portfolio Blender - Layer 3
----------------------------
Combine multiple strategy sleeves into portfolio.

Author: Systematic Trading Team
Date: November 2025
"""

import pandas as pd
import numpy as np
from typing import Dict


def blend_sleeves_equal_weight(sleeve_pnls: Dict[str, pd.Series]) -> pd.Series:
    """
    Blend multiple sleeves using equal weights.
    
    Args:
        sleeve_pnls: Dict of sleeve name -> PnL series
        
    Returns:
        Portfolio PnL series (equal-weighted)
    """
    
    # Convert to DataFrame for alignment
    df = pd.DataFrame(sleeve_pnls)
    
    # Equal weight = 1/N
    n_sleeves = len(sleeve_pnls)
    weights = {name: 1.0/n_sleeves for name in sleeve_pnls.keys()}
    
    # Calculate weighted sum
    portfolio_pnl = sum(df[name] * weight for name, weight in weights.items())
    
    return portfolio_pnl


def calculate_sleeve_attribution(
    sleeve_pnls: Dict[str, pd.Series], 
    portfolio_pnl: pd.Series
) -> Dict:
    """
    Calculate performance attribution for each sleeve and portfolio.
    
    Args:
        sleeve_pnls: Dict of sleeve PnLs
        portfolio_pnl: Blended portfolio PnL
        
    Returns:
        Dict of sleeve name -> metrics
    """
    
    def calc_metrics(pnl: pd.Series) -> Dict:
        """Calculate key metrics for a PnL series"""
        pnl = pnl.dropna()
        if len(pnl) == 0:
            return {
                'sharpe': 0.0,
                'annual_return': 0.0,
                'annual_vol': 0.0,
                'days': 0
            }
        
        mean_ret = pnl.mean()
        std_ret = pnl.std()
        
        sharpe = (mean_ret / std_ret) * np.sqrt(252) if std_ret > 0 else 0.0
        
        return {
            'sharpe': float(sharpe),
            'annual_return': float(mean_ret * 252),
            'annual_vol': float(std_ret * np.sqrt(252)),
            'days': int(len(pnl))
        }
    
    attribution = {}
    
    # Individual sleeves
    for name, pnl in sleeve_pnls.items():
        attribution[name] = calc_metrics(pnl)
    
    # Portfolio
    attribution['Portfolio'] = calc_metrics(portfolio_pnl)
    
    # Diversification benefit - FIXED: Only look at sleeve Sharpes, not Portfolio
    sleeve_sharpes = [
        attribution[name]['sharpe'] 
        for name in sleeve_pnls.keys()  # Only iterate over sleeve names
        if attribution[name]['sharpe'] > 0
    ]
    
    if len(sleeve_sharpes) > 0:
        best_sleeve_sharpe = max(sleeve_sharpes)
    else:
        best_sleeve_sharpe = 0.0
    
    portfolio_sharpe = attribution['Portfolio']['sharpe']
    
    if best_sleeve_sharpe > 0:
        diversification_benefit = (portfolio_sharpe / best_sleeve_sharpe - 1) * 100
    else:
        diversification_benefit = 0.0
    
    attribution['Diversification'] = {
        'best_sleeve_sharpe': float(best_sleeve_sharpe),
        'portfolio_sharpe': float(portfolio_sharpe),
        'improvement_pct': float(diversification_benefit)
    }
    
    return attribution


def calculate_correlation_matrix(sleeve_pnls: Dict[str, pd.Series]) -> pd.DataFrame:
    """
    Calculate correlation matrix of sleeve PnLs.
    
    Args:
        sleeve_pnls: Dict of sleeve PnLs
        
    Returns:
        pd.DataFrame: Correlation matrix
    """
    df = pd.DataFrame(sleeve_pnls)
    return df.corr()