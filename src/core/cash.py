# src/core/cash.py
"""
Cash Allocation - Defensive Regime Management
=============================================

Manages cash allocation for defensive regimes (e.g., high_vol_transitional).

Methods:
  - Scale Down: Reduce all positions proportionally (simple, recommended)
  - Explicit Cash: Treat cash as an asset allocation
  - Hybrid: Scale down + tighten stops (advanced)

Author: Claude (ex-Renaissance)
Date: November 4, 2025
Version: 1.0
"""

import pandas as pd
from typing import Dict, Tuple, Optional


class CashAllocationManager:
    """
    Manage cash allocation for defensive regimes.

    Attributes:
        method (str): 'scale_down', 'explicit', or 'hybrid'
    """

    def __init__(self, method: str = "scale_down"):
        """
        Initialize CashAllocationManager.

        Args:
            method: Cash allocation method
                - 'scale_down': Reduce all positions proportionally (RECOMMENDED)
                - 'explicit': Cash as explicit asset allocation
                - 'hybrid': Scale down + tighten stops (advanced)
        """
        if method not in ["scale_down", "explicit", "hybrid"]:
            raise ValueError(
                f"method must be 'scale_down', 'explicit', or 'hybrid', got {method}"
            )

        self.method = method

    def apply_cash_policy(
        self,
        weights: Dict[str, float],
        regime: str,
        risk_overlay: Optional[Dict] = None,
    ) -> Tuple[Dict[str, float], Optional[float]]:
        """
        Apply cash allocation policy based on regime.

        Args:
            weights: Target weights from regime map
            regime: Current regime (e.g., 'high_vol_transitional')
            risk_overlay: Risk parameters from portfolio.yaml
                - exposure_scalar: e.g., 0.50 for 50% cash
                - stop_multiplier: e.g., 0.75 for tighter stops

        Returns:
            Tuple of (adjusted_weights, stop_multiplier)
            - adjusted_weights: Weights with cash allocation applied
            - stop_multiplier: Stop loss multiplier (None if not used)
        """
        # Default: no risk overlay
        if risk_overlay is None:
            risk_overlay = {}

        exposure_scalar = risk_overlay.get("exposure_scalar", 1.0)
        stop_multiplier = risk_overlay.get("stop_multiplier", None)

        # Apply method
        if self.method == "scale_down":
            adjusted = self._apply_scale_down(weights, exposure_scalar)
            return adjusted, stop_multiplier

        elif self.method == "explicit":
            adjusted = self._apply_explicit_cash(weights, risk_overlay)
            return adjusted, stop_multiplier

        elif self.method == "hybrid":
            adjusted = self._apply_scale_down(weights, exposure_scalar)
            return adjusted, stop_multiplier

        else:
            # Should never reach here
            return weights, None

    def _apply_scale_down(
        self, weights: Dict[str, float], exposure_scalar: float
    ) -> Dict[str, float]:
        """
        Scale down all positions proportionally (METHOD A).

        Example:
            Normal: TC=50%, TI=30%, HC=20%
            With 50% cash: TC=25%, TI=15%, HC=10%, Cash=50%

        Preserves relative sleeve weights.
        """
        adjusted = {}

        # Scale down all sleeves
        for sleeve, weight in weights.items():
            if sleeve == "Cash":
                continue  # Handle cash separately
            adjusted[sleeve] = weight * exposure_scalar

        # Add implicit cash
        total_exposure = sum(adjusted.values())
        adjusted["Cash"] = 1.0 - total_exposure

        return adjusted

    def _apply_explicit_cash(
        self, weights: Dict[str, float], risk_overlay: Dict
    ) -> Dict[str, float]:
        """
        Use explicit cash allocation (METHOD B).

        Weights dict already contains 'Cash' key from portfolio.yaml.
        Just return as-is.
        """
        # If weights already have Cash, return as-is
        if "Cash" in weights:
            return weights

        # Otherwise, apply scale_down logic
        exposure_scalar = risk_overlay.get("exposure_scalar", 1.0)
        return self._apply_scale_down(weights, exposure_scalar)

    def check_cash_allocation(
        self, weights: Dict[str, float], regime: str, expected_cash_min: float = 0.45
    ) -> Tuple[bool, str]:
        """
        Validate cash allocation in defensive regimes.

        Args:
            weights: Current weights
            regime: Current regime
            expected_cash_min: Minimum expected cash % in death zone

        Returns:
            Tuple of (is_valid, message)
        """
        cash_pct = weights.get("Cash", 0.0)

        # Check if death zone
        if "high_vol_transitional" in regime:
            if cash_pct < expected_cash_min:
                return False, (
                    f"WARNING: Cash allocation {cash_pct*100:.1f}% "
                    f"below minimum {expected_cash_min*100:.1f}% in death zone"
                )
            else:
                return True, (
                    f"✓ Cash allocation {cash_pct*100:.1f}% "
                    f"appropriate for death zone"
                )
        else:
            # Normal regime: cash should be minimal
            if cash_pct > 0.10:
                return False, (
                    f"WARNING: Unexpected cash {cash_pct*100:.1f}% "
                    f"in non-defensive regime"
                )
            else:
                return True, f"✓ Fully invested ({cash_pct*100:.1f}% cash)"

    def calculate_effective_exposure(self, weights: Dict[str, float]) -> float:
        """
        Calculate total non-cash exposure.

        Args:
            weights: Current weights

        Returns:
            float: Total exposure (0 to 1.0)
        """
        total_exposure = sum(
            weight for sleeve, weight in weights.items() if sleeve != "Cash"
        )
        return total_exposure


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def apply_cash_simple(
    weights: Dict[str, float], regime: str, death_zone_cash_pct: float = 0.50
) -> Dict[str, float]:
    """
    Convenience function for simple cash allocation (stateless).

    Args:
        weights: Current weights
        regime: Current regime
        death_zone_cash_pct: Cash % in death zone (default: 50%)

    Returns:
        dict: Weights with cash applied
    """
    if "high_vol_transitional" in regime:
        # Death zone: go defensive
        exposure_scalar = 1.0 - death_zone_cash_pct

        adjusted = {}
        for sleeve, weight in weights.items():
            if sleeve != "Cash":
                adjusted[sleeve] = weight * exposure_scalar

        adjusted["Cash"] = death_zone_cash_pct

        return adjusted
    else:
        # Normal regime: no cash
        if "Cash" not in weights:
            weights["Cash"] = 0.0
        return weights


# ============================================================================
# MAIN - For Testing
# ============================================================================

if __name__ == "__main__":
    """
    Test cash allocation manager
    """
    print("=" * 80)
    print("CASH ALLOCATION MANAGER - Test Mode")
    print("=" * 80)

    # Create manager
    manager = CashAllocationManager(method="scale_down")

    print(f"\nConfiguration:")
    print(f"  Method: {manager.method}")

    # Test scenarios
    print("\n" + "=" * 80)
    print("SCENARIO 1: Normal Regime (low_vol_trending)")
    print("=" * 80)

    weights_normal = {"TrendCore": 0.30, "TrendImpulse": 0.60, "HookCore": 0.10}

    print("\nInput weights:")
    for sleeve, weight in weights_normal.items():
        print(f"  {sleeve}: {weight*100:.1f}%")

    # Apply (no cash expected)
    adjusted, stop_mult = manager.apply_cash_policy(
        weights_normal, regime="low_vol_trending", risk_overlay={"exposure_scalar": 1.0}
    )

    print("\nOutput weights:")
    for sleeve, weight in adjusted.items():
        print(f"  {sleeve}: {weight*100:.1f}%")

    # Validate
    is_valid, message = manager.check_cash_allocation(adjusted, "low_vol_trending")
    print(f"\nValidation: {message}")

    # ---

    print("\n" + "=" * 80)
    print("SCENARIO 2: Death Zone (high_vol_transitional)")
    print("=" * 80)

    weights_death = {
        "TrendCore": 0.20,
        "TrendImpulse": 0.05,
        "HookCore": 0.25,
        "Cash": 0.50,  # Explicit in config
    }

    print("\nInput weights (from portfolio.yaml):")
    for sleeve, weight in weights_death.items():
        print(f"  {sleeve}: {weight*100:.1f}%")

    # Apply scale down
    adjusted, stop_mult = manager.apply_cash_policy(
        weights_death,
        regime="high_vol_transitional",
        risk_overlay={"exposure_scalar": 0.50},
    )

    print("\nOutput weights (after scale_down):")
    for sleeve, weight in adjusted.items():
        print(f"  {sleeve}: {weight*100:.1f}%")

    # Validate
    is_valid, message = manager.check_cash_allocation(adjusted, "high_vol_transitional")
    print(f"\nValidation: {message}")

    exposure = manager.calculate_effective_exposure(adjusted)
    print(f"Total exposure: {exposure*100:.1f}%")

    # ---

    print("\n" + "=" * 80)
    print("SCENARIO 3: Test Different Cash Levels")
    print("=" * 80)

    for cash_pct in [0.30, 0.50, 0.70]:
        print(f"\n{int(cash_pct*100)}% Cash Policy:")

        base_weights = {"TrendCore": 0.40, "TrendImpulse": 0.10, "HookCore": 0.50}

        adjusted, _ = manager.apply_cash_policy(
            base_weights,
            regime="high_vol_transitional",
            risk_overlay={"exposure_scalar": 1.0 - cash_pct},
        )

        for sleeve, weight in sorted(adjusted.items()):
            print(f"  {sleeve}: {weight*100:.1f}%")

    print("\n" + "=" * 80)
    print("SCENARIO 4: Hybrid Method (with stop tightening)")
    print("=" * 80)

    manager_hybrid = CashAllocationManager(method="hybrid")

    adjusted, stop_mult = manager_hybrid.apply_cash_policy(
        weights_death,
        regime="high_vol_transitional",
        risk_overlay={
            "exposure_scalar": 0.50,
            "stop_multiplier": 0.75,  # 25% tighter stops
        },
    )

    print("\nAdjusted weights:")
    for sleeve, weight in adjusted.items():
        print(f"  {sleeve}: {weight*100:.1f}%")

    print(f"\nStop multiplier: {stop_mult}")
    print(f"  (Stops tightened to {stop_mult*100:.0f}% of normal)")

    print("\n✅ Cash allocation manager test complete!")
