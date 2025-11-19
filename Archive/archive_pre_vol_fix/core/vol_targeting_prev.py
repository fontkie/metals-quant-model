"""
Volume Targeting Module - Layer 2 of 4-Layer Architecture

Institutional-grade volatility targeting for systematic strategies.
Supports both always-on strategies (continuous positioning) and sparse strategies
(regime-dependent, with long flat periods).

CRITICAL UPDATE (Nov 2025):
Enhanced classification logic now considers BOTH % active AND max flat streak.
This fixes TrendImpulse V5 misclassification (90% active, 8-day gaps).

Methodology:
- EWMA vol estimation (λ=0.94, RiskMetrics 1996 standard)
- Conservative floors/caps to prevent extreme leverage
- Two modes: strategy-level vol (always-on) vs underlying vol × exposure (sparse)
- Fully backward-looking (no forward bias)

Author: Systematic Trading Team
Date: November 2025
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple


def calculate_max_flat_streak(positions: pd.Series) -> int:
    """
    Calculate the maximum consecutive days the strategy was flat (position = 0).
    
    This is critical for proper classification:
    - Short gaps (1-8 days) → Mostly-on with gaps → Use always_on method
    - Long gaps (15+ days) → True sparse → Use sparse method
    
    Args:
        positions: Strategy positions series
        
    Returns:
        Maximum number of consecutive flat days
    """
    is_flat = (positions.abs() < 0.01) | positions.isna()
    
    # Find changes in flat state
    flat_changes = is_flat.astype(int).diff().fillna(0)
    flat_starts = flat_changes[flat_changes == 1].index
    flat_ends = flat_changes[flat_changes == -1].index
    
    max_streak = 0
    for start_idx in range(len(flat_starts)):
        start = flat_starts[start_idx]
        # Find next end after this start
        matching_ends = flat_ends[flat_ends > start]
        if len(matching_ends) > 0:
            end = matching_ends[0]
            streak = (positions.index.get_loc(end) - 
                     positions.index.get_loc(start))
            max_streak = max(max_streak, streak)
    
    return max_streak


def classify_strategy_type(
    positions: pd.Series, 
    threshold_pct_active: float = 95.0,
    mostly_on_threshold: float = 85.0,
    max_flat_threshold: int = 15,
) -> str:
    """
    Automatically classify strategy as 'always_on' or 'sparse'.
    
    ENHANCED LOGIC (Nov 2025):
    ──────────────────────────────────────────────────────────────────
    Previous (Binary):
        if pct_active > 95% → always_on
        else → sparse
    
    Problem: 
        TrendImpulse V5 is 89.8% active with 1-8 day gaps
        → Classified as "sparse" (wrong)
        → Used underlying vol method (wrong)
        → Vol targeting failed (+52% overshoot)
    
    New (Nuanced):
        if pct_active > 95% → always_on
        elif pct_active > 85% AND max_flat < 15 days → always_on (with gaps)
        else → sparse (true sparse)
    ──────────────────────────────────────────────────────────────────
    
    Classification Examples:
    ──────────────────────────────────────────────────────────────────
    Strategy          % Active   Max Flat   Classification   Method
    ──────────────────────────────────────────────────────────────────
    TrendMedium V2      99%      <2 days    always_on       Strategy returns
    MomentumCore V2     96.2%    <2 days    always_on       Strategy returns
    TrendImpulse V5     89.8%    8 days     always_on*      Strategy returns
    True Sparse         70%      25 days    sparse          Underlying × exposure
    
    * Previously misclassified as sparse, now correctly classified as always_on
    
    Args:
        positions: Strategy positions
        threshold_pct_active: Threshold for pure always_on (default 95%)
        mostly_on_threshold: Threshold for mostly-on with gaps (default 85%)
        max_flat_threshold: Max flat days to still be always_on (default 15)
        
    Returns:
        'always_on' or 'sparse'
    """
    active_days = (positions.abs() > 0.01).sum()
    total_days = len(positions)
    pct_active = (active_days / total_days) * 100
    
    # Calculate max flat streak
    max_flat = calculate_max_flat_streak(positions)
    
    # Enhanced classification logic
    if pct_active > threshold_pct_active:
        strategy_type = 'always_on'
        reason = f"{pct_active:.1f}% active (>{threshold_pct_active}%)"
        
    elif pct_active > mostly_on_threshold and max_flat < max_flat_threshold:
        strategy_type = 'always_on'  # Mostly-on with brief gaps
        reason = (f"{pct_active:.1f}% active (>{mostly_on_threshold}%) "
                 f"with max {max_flat}d flat (<{max_flat_threshold}d) "
                 f"→ treating as always_on")
        
    else:
        strategy_type = 'sparse'  # True sparse
        reason = (f"{pct_active:.1f}% active (<{mostly_on_threshold}%) "
                 f"or max {max_flat}d flat (>{max_flat_threshold}d)")
    
    print(f"Strategy classification: {reason} → {strategy_type}")
    
    return strategy_type


def target_volatility(
    strategy_returns: pd.Series,
    underlying_returns: pd.Series,
    positions: pd.Series,
    target_vol: float = 0.10,
    strategy_type: str = 'always_on',
    lambda_decay: float = 0.94,
    vol_floor: float = 0.02,
    vol_cap: float = 0.40,
    max_leverage: float = 3.0,
    min_history: int = 63,
) -> Tuple[pd.Series, pd.Series]:
    """
    Apply closed-loop volatility targeting to strategy.
    
    Args:
        strategy_returns: Daily strategy returns (positions.shift(1) * underlying_returns)
        underlying_returns: Daily underlying asset returns (copper)
        positions: Daily strategy positions (-1 to +1)
        target_vol: Target annualized volatility (default 10%)
        strategy_type: 'always_on' or 'sparse'
            - 'always_on': Continuous positioning (TrendMedium, MomentumCore)
              Uses EWMA of strategy returns directly
            - 'sparse': Regime-dependent with flat periods (TrendImpulse)
              Uses EWMA of underlying × typical exposure
        lambda_decay: EWMA decay factor (0.94 = ~25 day half-life, RiskMetrics standard)
        vol_floor: Minimum vol estimate (prevents extreme leverage in false calm)
        vol_cap: Maximum vol estimate (prevents under-leverage in extreme vol)
        max_leverage: Hard cap on leverage scalar
        min_history: Minimum days before applying leverage
        
    Returns:
        leverage: Scalar to multiply strategy positions (0 to max_leverage)
        realized_vol: Estimated annualized volatility (for monitoring)
        
    Scrutiny Questions & Answers:
        Q: "Why EWMA with λ=0.94?"
        A: Industry standard from RiskMetrics (1996). Widely used for daily vol
           estimation, ~25-day half-life balances responsiveness with stability.
           
        Q: "Why two modes (always_on vs sparse)?"
        A: Sparse strategies (TrendImpulse with 20-day flat periods) would show
           artificially low vol during dormant periods, causing over-leveraging
           when they activate. We use underlying vol × typical exposure instead.
           
        Q: "Why 2% vol floor?"
        A: Prevents extreme leverage (>5x) during false calm periods.
           Conservative given copper's regime-switching volatility.
           
        Q: "Why 3x max leverage?"
        A: Standard for systematic futures strategies. Prevents portfolio
           concentration and margin issues. Higher leverage increases
           implementation risk without proportional returns.
           
        Q: "What if vol estimates are wrong?"
        A: Floor/cap bounds contain worst-case scenarios. Max leverage cap
           prevents blowups. This is risk management, not prediction.
    """
    # Input validation
    assert strategy_type in ['always_on', 'sparse'], \
        f"strategy_type must be 'always_on' or 'sparse', got {strategy_type}"
    assert 0 < lambda_decay < 1, f"lambda_decay must be in (0,1), got {lambda_decay}"
    assert vol_floor > 0, f"vol_floor must be positive, got {vol_floor}"
    assert vol_cap > vol_floor, f"vol_cap must exceed vol_floor"
    assert max_leverage > 0, f"max_leverage must be positive"
    
    # Align all series
    strategy_returns = strategy_returns.copy()
    underlying_returns = underlying_returns.copy()
    positions = positions.copy()
    
    # Calculate EWMA variance based on strategy type
    if strategy_type == 'always_on':
        # Use strategy returns directly (captures strategy behavior)
        ewma_var = (
            strategy_returns.pow(2)
            .ewm(alpha=1-lambda_decay, min_periods=min_history)
            .mean()
        )
        
    elif strategy_type == 'sparse':
        # Use underlying vol × typical exposure (prevents false low vol)
        underlying_var = (
            underlying_returns.pow(2)
            .ewm(alpha=1-lambda_decay, min_periods=min_history)
            .mean()
        )
        
        # Calculate typical exposure when strategy is active
        active_mask = positions.abs() > 0.05  # Non-trivial positions
        if active_mask.sum() > 0:
            # Rolling median of absolute position when active
            typical_exposure = (
                positions[active_mask].abs()
                .expanding(min_periods=min_history)
                .median()
                .reindex(positions.index, method='ffill')
                .fillna(0.5)  # Default to 50% exposure if no history
            )
        else:
            typical_exposure = pd.Series(0.5, index=positions.index)
        
        # Effective variance = underlying variance × (typical exposure)²
        ewma_var = underlying_var * typical_exposure.pow(2)
    
    # Convert variance to annualized volatility
    realized_vol = np.sqrt(ewma_var * 252)
    
    # Apply conservative bounds
    effective_vol = realized_vol.clip(lower=vol_floor, upper=vol_cap)
    
    # Calculate leverage scalar
    leverage = (target_vol / effective_vol).clip(upper=max_leverage)
    
    # Don't apply leverage until sufficient history
    leverage.iloc[:min_history] = 0
    
    # Fill NaN values with 0 (no leverage)
    leverage = leverage.fillna(0)
    realized_vol = realized_vol.fillna(0)
    
    return leverage, realized_vol


def apply_vol_targeting(
    positions: pd.Series,
    underlying_returns: pd.Series,
    target_vol: float = 0.10,
    strategy_type: str = 'always_on',
    **kwargs
) -> pd.Series:
    """
    Convenience function: Apply vol targeting to positions directly.
    
    Args:
        positions: Raw strategy positions
        underlying_returns: Underlying asset returns
        target_vol: Target volatility
        strategy_type: 'always_on' or 'sparse'
        **kwargs: Additional arguments for target_volatility()
        
    Returns:
        positions_scaled: Vol-targeted positions (positions × leverage)
    """
    # Calculate strategy returns
    strategy_returns = positions.shift(1) * underlying_returns
    
    # Get leverage scalar
    leverage, _ = target_volatility(
        strategy_returns=strategy_returns,
        underlying_returns=underlying_returns,
        positions=positions,
        target_vol=target_vol,
        strategy_type=strategy_type,
        **kwargs
    )
    
    # Apply leverage to positions
    positions_scaled = positions * leverage
    
    return positions_scaled


def get_vol_diagnostics(
    positions: pd.Series,
    underlying_returns: pd.Series,
    target_vol: float = 0.10,
    strategy_type: str = 'always_on',
    **kwargs
) -> pd.DataFrame:
    """
    Generate diagnostic report for vol targeting performance.
    
    Returns DataFrame with:
        - leverage: Applied leverage scalar
        - realized_vol: Estimated volatility
        - distance_to_target: Difference from target vol
        - strategy_returns: Actual strategy returns
    """
    # Calculate strategy returns
    strategy_returns = positions.shift(1) * underlying_returns
    
    # Get leverage and realized vol
    leverage, realized_vol = target_volatility(
        strategy_returns=strategy_returns,
        underlying_returns=underlying_returns,
        positions=positions,
        target_vol=target_vol,
        strategy_type=strategy_type,
        **kwargs
    )
    
    # Calculate vol-targeted returns
    targeted_returns = strategy_returns * leverage
    
    # Calculate realized vol of targeted returns (what we actually achieved)
    targeted_vol = (
        targeted_returns.pow(2)
        .ewm(alpha=1-kwargs.get('lambda_decay', 0.94), min_periods=kwargs.get('min_history', 63))
        .mean()
        .pipe(lambda x: np.sqrt(x * 252))
    )
    
    # Build diagnostics
    diagnostics = pd.DataFrame({
        'leverage': leverage,
        'pre_target_vol': realized_vol,
        'post_target_vol': targeted_vol,
        'distance_to_target': targeted_vol - target_vol,
        'strategy_returns': strategy_returns,
        'targeted_returns': targeted_returns,
    })
    
    return diagnostics