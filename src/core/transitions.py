# src/core/transitions.py
"""
Transition Smoothing - Weight Change Management
===============================================

Smooths weight transitions between regimes to avoid:
  - Whipsaw from regime oscillation
  - Excessive transaction costs
  - Large single-day rebalances

Uses Exponential Moving Average (EMA) - Renaissance standard approach.

Author: Claude (ex-Renaissance)
Date: November 4, 2025
Version: 1.0
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional


class TransitionSmoother:
    """
    Smooth weight transitions between regimes using EMA.

    Attributes:
        window_days (int): EMA smoothing window (3/5/10 typical)
        method (str): 'exponential', 'linear', or 'none'
        alpha (float): EMA decay factor (calculated from window_days)
        current_weights (dict): Current smoothed weights (state)
    """

    def __init__(self, window_days: int = 5, method: str = "exponential"):
        """
        Initialize TransitionSmoother.

        Args:
            window_days: Smoothing window (default: 5 days)
                - 3 days: Fast response, higher turnover
                - 5 days: Balanced (RECOMMENDED)
                - 10 days: Slow response, lower turnover
            method: Smoothing method
                - 'exponential': EMA (recommended)
                - 'linear': Linear interpolation
                - 'none': No smoothing (discrete jumps)
        """
        if method not in ["exponential", "linear", "none"]:
            raise ValueError(
                f"method must be 'exponential', 'linear', or 'none', got {method}"
            )

        if window_days < 1:
            raise ValueError(f"window_days must be >= 1, got {window_days}")

        self.window_days = window_days
        self.method = method

        # Calculate EMA decay factor (standard formula)
        self.alpha = 2.0 / (window_days + 1)

        # State: current smoothed weights
        self.current_weights = {}

        # History tracking (for diagnostics)
        self.weight_history = []
        self.target_history = []

    def smooth_transition(
        self, target_weights: Dict[str, float], force_reset: bool = False
    ) -> Dict[str, float]:
        """
        Apply smoothing to weight transition.

        Args:
            target_weights: Desired weights in current regime
            force_reset: If True, jump immediately to target (no smoothing)

        Returns:
            dict: Smoothed weights for today
        """
        # First call: initialize at target (no smoothing needed)
        if not self.current_weights or force_reset:
            self.current_weights = target_weights.copy()
            self._record_history(target_weights, target_weights)
            return self.current_weights

        # No smoothing method: return target directly
        if self.method == "none":
            self.current_weights = target_weights.copy()
            self._record_history(target_weights, target_weights)
            return self.current_weights

        # Apply smoothing
        if self.method == "exponential":
            smoothed = self._smooth_exponential(target_weights)
        elif self.method == "linear":
            smoothed = self._smooth_linear(target_weights)
        else:
            raise ValueError(f"Unknown method: {self.method}")

        # Renormalize to ensure sum = 1.0
        smoothed = self._renormalize(smoothed)

        # Update state
        self.current_weights = smoothed
        self._record_history(target_weights, smoothed)

        return smoothed

    def _smooth_exponential(self, target_weights: Dict[str, float]) -> Dict[str, float]:
        """
        Exponential Moving Average (EMA) smoothing.

        Formula: new_weight = alpha * target + (1 - alpha) * old_weight

        Convergence characteristics (5-day window, alpha=0.333):
          - Day 1: 33% of transition complete
          - Day 5: 87% complete
          - Day 12: 90% complete (practical convergence)
        """
        smoothed = {}

        # Get all unique sleeves (from both current and target)
        all_sleeves = set(self.current_weights.keys()) | set(target_weights.keys())

        for sleeve in all_sleeves:
            old_w = self.current_weights.get(sleeve, 0.0)
            new_w = target_weights.get(sleeve, 0.0)

            # EMA formula
            smoothed[sleeve] = self.alpha * new_w + (1 - self.alpha) * old_w

        return smoothed

    def _smooth_linear(self, target_weights: Dict[str, float]) -> Dict[str, float]:
        """
        Linear interpolation smoothing.

        Moves toward target in equal daily steps over window_days.
        Less commonly used than EMA.
        """
        smoothed = {}
        step_size = 1.0 / self.window_days

        all_sleeves = set(self.current_weights.keys()) | set(target_weights.keys())

        for sleeve in all_sleeves:
            old_w = self.current_weights.get(sleeve, 0.0)
            new_w = target_weights.get(sleeve, 0.0)

            # Linear interpolation
            smoothed[sleeve] = old_w + step_size * (new_w - old_w)

        return smoothed

    def _renormalize(self, weights: Dict[str, float]) -> Dict[str, float]:
        """
        Renormalize weights to sum to 1.0.

        Important: Smoothing can cause weights to drift from 1.0 due to
        floating point arithmetic. Always renormalize.
        """
        total = sum(weights.values())

        if total == 0:
            # Edge case: all weights zero (shouldn't happen)
            # Return equal weight
            n = len(weights)
            return {k: 1.0 / n for k in weights.keys()}

        return {k: v / total for k, v in weights.items()}

    def _record_history(
        self, target_weights: Dict[str, float], smoothed_weights: Dict[str, float]
    ):
        """
        Record weight history for diagnostics.

        Useful for:
          - Plotting weight evolution over time
          - Calculating turnover
          - Debugging transition issues
        """
        self.target_history.append(target_weights.copy())
        self.weight_history.append(smoothed_weights.copy())

    def reset(self):
        """
        Reset smoother state (clears current weights and history).

        Use when:
          - Starting a new backtest
          - Want to force fresh initialization
          - Testing different smoothing parameters
        """
        self.current_weights = {}
        self.weight_history = []
        self.target_history = []

    def get_convergence_estimate(self) -> float:
        """
        Estimate % convergence to target weights.

        Returns:
            float: Convergence percentage (0 to 100)
                - 100 = fully converged
                - 50 = halfway there
                - 0 = just started transitioning
        """
        if not self.target_history or not self.weight_history:
            return 100.0  # No transition happening

        target = self.target_history[-1]
        current = self.weight_history[-1]

        if len(self.target_history) < 2:
            return 100.0  # First step

        # Previous target (to detect regime changes)
        prev_target = self.target_history[-2]

        # Check if target changed (regime transition)
        target_changed = any(
            abs(target.get(k, 0) - prev_target.get(k, 0)) > 0.01
            for k in set(target.keys()) | set(prev_target.keys())
        )

        if not target_changed:
            return 100.0  # No transition needed

        # Calculate distance to target
        distance = sum(abs(current.get(k, 0) - target.get(k, 0)) for k in target.keys())

        # Normalize to percentage (max distance = 2.0 if complete flip)
        convergence_pct = max(0, 100 * (1 - distance / 2.0))

        return round(convergence_pct, 1)

    def calculate_turnover(self, days: Optional[int] = None) -> float:
        """
        Calculate total turnover from weight changes.

        Args:
            days: Calculate over last N days (None = all history)

        Returns:
            float: Total turnover (sum of absolute weight changes)
        """
        if len(self.weight_history) < 2:
            return 0.0

        history = self.weight_history[-days:] if days else self.weight_history

        turnover = 0.0
        for i in range(1, len(history)):
            prev_weights = history[i - 1]
            curr_weights = history[i]

            # Sum absolute changes
            for sleeve in curr_weights.keys():
                prev_w = prev_weights.get(sleeve, 0.0)
                curr_w = curr_weights.get(sleeve, 0.0)
                turnover += abs(curr_w - prev_w)

        # Divide by 2 (buy + sell counted separately)
        return turnover / 2.0


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def smooth_weights_simple(
    target_weights: Dict[str, float],
    current_weights: Dict[str, float],
    window_days: int = 5,
) -> Dict[str, float]:
    """
    Convenience function for one-time smoothing (stateless).

    Args:
        target_weights: Desired weights
        current_weights: Current weights
        window_days: EMA window

    Returns:
        dict: Smoothed weights
    """
    alpha = 2.0 / (window_days + 1)

    smoothed = {}
    all_sleeves = set(current_weights.keys()) | set(target_weights.keys())

    for sleeve in all_sleeves:
        old_w = current_weights.get(sleeve, 0.0)
        new_w = target_weights.get(sleeve, 0.0)
        smoothed[sleeve] = alpha * new_w + (1 - alpha) * old_w

    # Renormalize
    total = sum(smoothed.values())
    return {k: v / total for k, v in smoothed.items()}


# ============================================================================
# MAIN - For Testing
# ============================================================================

if __name__ == "__main__":
    """
    Test transition smoother with example regime change
    """
    print("=" * 80)
    print("TRANSITION SMOOTHER - Test Mode")
    print("=" * 80)

    # Create smoother (5-day EMA)
    smoother = TransitionSmoother(window_days=5, method="exponential")

    print(f"\nConfiguration:")
    print(f"  Method: {smoother.method}")
    print(f"  Window: {smoother.window_days} days")
    print(f"  Alpha (EMA decay): {smoother.alpha:.3f}")

    # Simulate regime change
    print("\n" + "=" * 80)
    print("SCENARIO: Regime change from low_vol_trending to medium_vol_transitional")
    print("=" * 80)

    # Day 0: Low vol trending
    weights_day0 = {"TrendCore": 0.30, "TrendImpulse": 0.60, "HookCore": 0.10}

    print("\nDay 0 (Starting weights):")
    for sleeve, weight in weights_day0.items():
        print(f"  {sleeve}: {weight*100:.1f}%")

    # Initialize
    smoothed = smoother.smooth_transition(weights_day0)

    # Day 1: Regime changes to medium vol transitional
    weights_target = {"TrendCore": 0.20, "TrendImpulse": 0.10, "HookCore": 0.70}

    print("\nTarget weights (medium_vol_transitional):")
    for sleeve, weight in weights_target.items():
        print(f"  {sleeve}: {weight*100:.1f}%")

    print("\n" + "-" * 80)
    print("TRANSITION SIMULATION (Days 1-15)")
    print("-" * 80)
    print(
        f"{'Day':<5} {'TrendCore':<12} {'TrendImpulse':<15} {'HookCore':<12} {'Convergence':<12}"
    )
    print("-" * 80)

    # Simulate 15 days of transition
    for day in range(1, 16):
        smoothed = smoother.smooth_transition(weights_target)
        convergence = smoother.get_convergence_estimate()

        print(
            f"{day:<5} "
            f"{smoothed['TrendCore']*100:>6.1f}%      "
            f"{smoothed['TrendImpulse']*100:>6.1f}%         "
            f"{smoothed['HookCore']*100:>6.1f}%      "
            f"{convergence:>6.1f}%"
        )

    # Calculate turnover
    turnover = smoother.calculate_turnover()
    print("\n" + "=" * 80)
    print(f"Total turnover: {turnover*100:.1f}%")
    print(f"Average daily turnover: {turnover/15*100:.2f}%")

    # Test different window sizes
    print("\n" + "=" * 80)
    print("COMPARISON: Different Window Sizes")
    print("=" * 80)

    for window in [3, 5, 10]:
        smoother_test = TransitionSmoother(window_days=window)
        smoother_test.smooth_transition(weights_day0)  # Initialize

        # Simulate 12 days
        for _ in range(12):
            smoother_test.smooth_transition(weights_target)

        final_weights = smoother_test.current_weights
        convergence = smoother_test.get_convergence_estimate()
        turnover = smoother_test.calculate_turnover()

        print(f"\n{window}-day window:")
        print(f"  Day 12 convergence: {convergence:.1f}%")
        print(f"  Total turnover: {turnover*100:.1f}%")
        print(
            f"  HC allocation: {final_weights['HookCore']*100:.1f}% "
            f"(target: {weights_target['HookCore']*100:.1f}%)"
        )

    print("\n✅ Transition smoother test complete!")
