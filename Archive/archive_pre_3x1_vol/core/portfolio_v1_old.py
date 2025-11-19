# src/core/portfolio.py
"""
Adaptive Portfolio - Multi-Sleeve Dynamic Blending
==================================================

Orchestrates adaptive regime blending:
  1. Detect market regime (vol × trend)
  2. Look up target weights from config
  3. Smooth transitions (EMA)
  4. Apply cash policy (defensive regimes)
  5. Blend sleeve returns → portfolio PnL

Author: Claude (ex-Renaissance)
Date: November 4, 2025
Version: 1.0
"""

import pandas as pd
import numpy as np
import yaml
from pathlib import Path
from typing import Dict, Tuple, Optional, List

# Import our core modules
from .regime import RegimeDetector
from .transitions import TransitionSmoother
from .cash import CashAllocationManager


class AdaptivePortfolio:
    """
    Adaptive portfolio manager - regime-aware multi-sleeve blending.

    Attributes:
        sleeves (dict): Loaded sleeve DataFrames {name: df}
        config (dict): Full configuration from portfolio.yaml
        regime_detector (RegimeDetector): Regime classification engine
        transition_smoother (TransitionSmoother): Weight smoothing engine
        cash_manager (CashAllocationManager): Cash allocation engine
    """

    def __init__(self, sleeves_dict: Dict[str, pd.DataFrame], config: Dict):
        """
        Initialize AdaptivePortfolio.

        Args:
            sleeves_dict: Dict of {sleeve_name: dataframe}
                Each dataframe must have columns: date, pos, pnl_net, ret
            config: Configuration dict from portfolio.yaml
        """
        self.sleeves = sleeves_dict
        self.config = config

        # Initialize sub-components
        self._initialize_components()

        # Validate inputs
        self._validate_sleeves()

    def _initialize_components(self):
        """Initialize regime detector, smoother, cash manager."""
        # Regime detector
        regime_cfg = self.config.get("regime_detection", {})
        vol_cfg = regime_cfg.get("volatility", {})

        self.regime_detector = RegimeDetector(
            mode=vol_cfg.get("mode", "research"),
            vol_window=vol_cfg.get("vol_window_days", 63),
            percentile_window=vol_cfg.get("percentile_lookback_days", 252),
            low_vol_threshold=vol_cfg.get("low_vol_percentile", 0.33),
            high_vol_threshold=vol_cfg.get("high_vol_percentile", 0.67),
        )

        # Transition smoother
        smooth_cfg = self.config.get("transition_smoothing", {})

        if smooth_cfg.get("enabled", True):
            self.transition_smoother = TransitionSmoother(
                window_days=smooth_cfg.get("window_days", 5),
                method=smooth_cfg.get("method", "exponential"),
            )
        else:
            # No smoothing
            self.transition_smoother = TransitionSmoother(window_days=1, method="none")

        # Cash manager
        cash_method = self.config.get("cash_allocation_method", "scale_down")
        self.cash_manager = CashAllocationManager(method=cash_method)

    def _validate_sleeves(self):
        """Validate sleeve dataframes have required columns."""
        required_cols = ["date", "pos", "pnl_net"]

        for sleeve_name, df in self.sleeves.items():
            missing = [col for col in required_cols if col not in df.columns]
            if missing:
                raise ValueError(f"Sleeve '{sleeve_name}' missing columns: {missing}")

            # Ensure date is datetime
            if not pd.api.types.is_datetime64_any_dtype(df["date"]):
                df["date"] = pd.to_datetime(df["date"])

            # Sort by date
            df.sort_values("date", inplace=True)

    def get_price_series(self) -> pd.Series:
        """
        Extract price series from any sleeve (they should all have same dates).

        Returns:
            pd.Series: Price series for regime detection
        """
        # Use first sleeve's price
        first_sleeve = list(self.sleeves.values())[0]

        # If 'price' column exists, use it
        if "price" in first_sleeve.columns:
            return first_sleeve.set_index("date")["price"]

        # Otherwise, reconstruct from returns
        if "ret" in first_sleeve.columns:
            returns = first_sleeve.set_index("date")["ret"]
            # Assume starting price = 100
            price = (1 + returns).cumprod() * 100
            return price

        raise ValueError("Cannot extract price series from sleeves")

    def backtest_adaptive_strategy(self) -> Tuple[pd.DataFrame, Dict, pd.DataFrame]:
        """
        Run full adaptive portfolio backtest.

        Returns:
            Tuple of (daily_series, metrics, regime_log)
            - daily_series: Portfolio daily PnL and positions
            - metrics: Portfolio-level performance metrics
            - regime_log: Regime transitions and weights over time
        """
        print("\n" + "=" * 80)
        print("ADAPTIVE PORTFOLIO BACKTEST")
        print("=" * 80)

        # Step 1: Detect regimes
        print("\nStep 1: Detecting market regimes...")
        price_series = self.get_price_series()
        regime_df = self.regime_detector.detect_combined_regime(price_series)

        regime_dist = self.regime_detector.get_regime_distribution(
            regime_df["vol_regime"]
        )
        print(f"  Vol regime distribution:")
        for regime, row in regime_dist.iterrows():
            print(f"    {regime}: {row['pct_of_time']:.1f}% of time")

        # Step 2: Get aligned dates (intersection of all sleeves)
        print("\nStep 2: Aligning sleeve dates...")
        common_dates = self._get_common_dates()
        print(f"  {len(common_dates)} common trading days")

        # Step 3: Build portfolio daily series
        print("\nStep 3: Building adaptive portfolio...")
        daily_series, regime_log = self._build_daily_series(regime_df, common_dates)

        # Step 4: Calculate metrics
        print("\nStep 4: Calculating performance metrics...")
        metrics = self.calculate_portfolio_metrics(daily_series)

        print("\n" + "=" * 80)
        print("PORTFOLIO PERFORMANCE")
        print("=" * 80)
        print(f"Sharpe Ratio:    {metrics['sharpe']:.3f}")
        print(f"Annual Return:   {metrics['annual_return']*100:.2f}%")
        print(f"Annual Vol:      {metrics['annual_vol']*100:.2f}%")
        print(f"Max Drawdown:    {metrics['max_drawdown']*100:.2f}%")
        print(f"Observations:    {metrics['obs']:,}")

        return daily_series, metrics, regime_log

    def _get_common_dates(self) -> pd.DatetimeIndex:
        """Get common dates across all sleeves."""
        date_sets = []
        for sleeve_name, df in self.sleeves.items():
            date_sets.append(set(df["date"]))

        # Intersection
        common = set.intersection(*date_sets)
        return pd.DatetimeIndex(sorted(common))

    def _build_daily_series(
        self, regime_df: pd.DataFrame, common_dates: pd.DatetimeIndex
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Build daily portfolio series with adaptive weights.

        Returns:
            Tuple of (daily_series, regime_log)
        """
        records = []
        regime_records = []

        # Reset smoother (fresh start)
        self.transition_smoother.reset()

        for date in common_dates:
            # Get regime for this date
            if date not in regime_df.index:
                continue

        for date in common_dates:
            # Get regime for this date
            if date not in regime_df.index:
                continue

            regime = regime_df.loc[date, "combined_regime"]

            # Handle NaN regime (skip or use default)
            if pd.isna(regime) or regime == "nan":
                continue  # Skip this date

            vol_regime = regime_df.loc[date, "vol_regime"]
            trend_regime = regime_df.loc[date, "trend_regime"]
            vol_percentile = regime_df.loc[date, "vol_percentile"]

            # Get target weights from regime map
            target_weights = self._get_regime_weights(regime)

            # Apply transition smoothing
            smoothed_weights = self.transition_smoother.smooth_transition(
                target_weights
            )

            # Apply cash policy (if death zone)
            final_weights, stop_mult = self.cash_manager.apply_cash_policy(
                smoothed_weights,
                regime,
                risk_overlay=target_weights.get("risk_overlay"),
            )

            # Calculate portfolio return (weighted average of sleeve returns)
            portfolio_ret = self._calculate_portfolio_return(date, final_weights)

            # Calculate portfolio position (weighted average of sleeve positions)
            portfolio_pos = self._calculate_portfolio_position(date, final_weights)

            # Record
            records.append(
                {
                    "date": date,
                    "ret": portfolio_ret,
                    "pos": portfolio_pos,
                    "regime": regime,
                    "vol_regime": vol_regime,
                    "trend_regime": trend_regime,
                    "vol_percentile": vol_percentile,
                }
            )

            # Record regime log (for analysis)
            regime_record = {
                "date": date,
                "regime": regime,
                "vol_regime": vol_regime,
                "trend_regime": trend_regime,
                "vol_percentile": vol_percentile,
            }

            # Add sleeve weights
            for sleeve, weight in final_weights.items():
                regime_record[f"{sleeve}_weight"] = weight

            regime_records.append(regime_record)

        # Build DataFrames
        daily_df = pd.DataFrame(records)
        regime_log = pd.DataFrame(regime_records)

        # Calculate cumulative PnL
        daily_df["pnl_net"] = daily_df["ret"]
        daily_df["cum_pnl"] = (1 + daily_df["ret"]).cumprod()

        return daily_df, regime_log

    def _get_regime_weights(self, regime: str) -> Dict[str, float]:
        """
        Look up target weights for given regime.

        Args:
            regime: e.g., 'low_vol_trending'

        Returns:
            dict: Target weights for each sleeve
        """
        regime_weights_cfg = self.config.get("regime_weights", {})

        # Get weights for this specific regime
        if regime in regime_weights_cfg:
            weights = regime_weights_cfg[regime].copy()

            # Extract risk overlay if present
            risk_overlay = weights.pop("risk_overlay", None)

            # Remove non-weight keys (rationale, expected_sharpe, etc.)
            weights = {
                k: v for k, v in weights.items() if k in self.sleeves or k == "Cash"
            }

            # Add risk overlay back for cash manager
            if risk_overlay:
                weights["risk_overlay"] = risk_overlay

            return weights

        # Fallback: use default weights from sleeve config
        print(f"WARNING: No weights defined for regime '{regime}', using defaults")
        sleeves_cfg = self.config.get("sleeves", {})

        weights = {}
        for sleeve_name, sleeve_cfg in sleeves_cfg.items():
            if sleeve_cfg.get("enabled", True):
                weights[sleeve_name] = sleeve_cfg.get("default_weight", 0.0)

        # Normalize
        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}

    def _calculate_portfolio_return(
        self, date: pd.Timestamp, weights: Dict[str, float]
    ) -> float:
        """
        Calculate portfolio return as weighted average of sleeve returns.

        Args:
            date: Trading date
            weights: Sleeve weights (including Cash if any)

        Returns:
            float: Portfolio return
        """
        portfolio_ret = 0.0

        for sleeve_name, weight in weights.items():
            if sleeve_name == "Cash":
                # Cash earns 0% (ignore for now, can add risk-free rate later)
                continue

            if sleeve_name not in self.sleeves:
                continue

            # Get sleeve return for this date
            sleeve_df = self.sleeves[sleeve_name]
            sleeve_row = sleeve_df[sleeve_df["date"] == date]

            if len(sleeve_row) == 0:
                continue

            if "ret" in sleeve_row.columns:
                sleeve_ret = sleeve_row["ret"].iloc[0]
            elif "pnl_net" in sleeve_row.columns:
                # Use pnl_net as proxy for return
                sleeve_ret = sleeve_row["pnl_net"].iloc[0]
            else:
                sleeve_ret = 0.0

            # Weight contribution
            portfolio_ret += weight * sleeve_ret

        return portfolio_ret

    def _calculate_portfolio_position(
        self, date: pd.Timestamp, weights: Dict[str, float]
    ) -> float:
        """
        Calculate portfolio position as weighted average of sleeve positions.

        Args:
            date: Trading date
            weights: Sleeve weights

        Returns:
            float: Portfolio position
        """
        portfolio_pos = 0.0

        for sleeve_name, weight in weights.items():
            if sleeve_name == "Cash":
                continue

            if sleeve_name not in self.sleeves:
                continue

            sleeve_df = self.sleeves[sleeve_name]
            sleeve_row = sleeve_df[sleeve_df["date"] == date]

            if len(sleeve_row) == 0:
                continue

            sleeve_pos = sleeve_row["pos"].iloc[0]
            portfolio_pos += weight * sleeve_pos

        return portfolio_pos

    def calculate_portfolio_metrics(self, daily_series: pd.DataFrame) -> Dict:
        """
        Calculate portfolio-level performance metrics.

        Args:
            daily_series: Portfolio daily series

        Returns:
            dict: Performance metrics
        """
        returns = daily_series["ret"]

        # Annual return (compounded)
        total_return = (1 + returns).prod() - 1
        years = len(returns) / 252
        annual_return = (1 + total_return) ** (1 / years) - 1

        # Annual volatility
        annual_vol = returns.std() * np.sqrt(252)

        # Sharpe ratio
        sharpe = annual_return / annual_vol if annual_vol > 0 else 0.0

        # Max drawdown
        cum_ret = (1 + returns).cumprod()
        running_max = cum_ret.expanding().max()
        drawdown = (cum_ret - running_max) / running_max
        max_drawdown = drawdown.min()

        return {
            "sharpe": sharpe,
            "annual_return": annual_return,
            "annual_vol": annual_vol,
            "max_drawdown": max_drawdown,
            "obs": len(returns),
            "total_return": total_return,
        }

    def compare_static_vs_adaptive(self, static_weights: Dict[str, float]) -> Dict:
        """
        Compare adaptive portfolio to static blend.

        Args:
            static_weights: Fixed weights for static comparison
                e.g., {'TrendCore': 0.50, 'TrendImpulse': 0.30, 'HookCore': 0.20}

        Returns:
            dict: Comparison metrics
        """
        print("\n" + "=" * 80)
        print("STATIC VS ADAPTIVE COMPARISON")
        print("=" * 80)

        # Build static portfolio
        print("\nBuilding static portfolio...")
        common_dates = self._get_common_dates()

        static_records = []
        for date in common_dates:
            static_ret = self._calculate_portfolio_return(date, static_weights)
            static_records.append({"date": date, "ret": static_ret})

        static_df = pd.DataFrame(static_records)
        static_metrics = self.calculate_portfolio_metrics(static_df)

        print(f"Static Sharpe:   {static_metrics['sharpe']:.3f}")

        # Get adaptive metrics (run full backtest)
        adaptive_df, adaptive_metrics, _ = self.backtest_adaptive_strategy()

        # Calculate improvement
        sharpe_improvement = adaptive_metrics["sharpe"] - static_metrics["sharpe"]
        improvement_pct = (sharpe_improvement / static_metrics["sharpe"]) * 100

        print("\n" + "=" * 80)
        print(f"Adaptive Sharpe: {adaptive_metrics['sharpe']:.3f}")
        print(f"Improvement:     +{sharpe_improvement:.3f} ({improvement_pct:.1f}%)")
        print("=" * 80)

        return {
            "static_sharpe": static_metrics["sharpe"],
            "adaptive_sharpe": adaptive_metrics["sharpe"],
            "improvement": sharpe_improvement,
            "improvement_pct": improvement_pct,
            "static_metrics": static_metrics,
            "adaptive_metrics": adaptive_metrics,
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def load_portfolio_config(config_path: str) -> Dict:
    """
    Load portfolio.yaml configuration.

    Args:
        config_path: Path to portfolio.yaml

    Returns:
        dict: Configuration
    """
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config


def load_sleeves_from_config(config: Dict) -> Dict[str, pd.DataFrame]:
    """
    Load all enabled sleeves from configuration.

    Args:
        config: Configuration dict from portfolio.yaml

    Returns:
        dict: {sleeve_name: dataframe}
    """
    sleeves = {}
    sleeves_cfg = config.get("sleeves", {})

    for sleeve_name, sleeve_cfg in sleeves_cfg.items():
        # Check if enabled
        if not sleeve_cfg.get("enabled", True):
            print(f"  Skipping {sleeve_name} (disabled)")
            continue

        # Load CSV
        csv_path = sleeve_cfg.get("path")
        if not csv_path:
            print(f"  WARNING: No path for {sleeve_name}")
            continue

        # Try to load
        try:
            df = pd.read_csv(csv_path)
            df["date"] = pd.to_datetime(df["date"])
            sleeves[sleeve_name] = df
            print(f"  ✓ Loaded {sleeve_name}: {len(df)} days")
        except Exception as e:
            print(f"  ✗ Failed to load {sleeve_name}: {e}")

    return sleeves


# ============================================================================
# MAIN - For Testing
# ============================================================================

if __name__ == "__main__":
    """
    Test adaptive portfolio with mock data
    """
    print("=" * 80)
    print("ADAPTIVE PORTFOLIO - Test Mode")
    print("=" * 80)

    # Create mock sleeve data
    dates = pd.date_range("2020-01-01", "2024-12-31", freq="B")
    n = len(dates)

    # Mock sleeves with different characteristics
    np.random.seed(42)

    sleeve_tc = pd.DataFrame(
        {
            "date": dates,
            "pos": np.random.choice([-1, 0, 1], n),
            "ret": np.random.normal(0.0002, 0.01, n),  # Sharpe ~0.6
            "pnl_net": np.random.normal(0.0002, 0.01, n),
        }
    )

    sleeve_ti = pd.DataFrame(
        {
            "date": dates,
            "pos": np.random.choice([-1, 0, 1], n),
            "ret": np.random.normal(0.0001, 0.015, n),  # Sharpe ~0.4
            "pnl_net": np.random.normal(0.0001, 0.015, n),
        }
    )

    sleeves_dict = {"TrendCore": sleeve_tc, "TrendImpulse": sleeve_ti}

    # Create minimal config
    config = {
        "regime_detection": {
            "volatility": {
                "mode": "research",
                "vol_window_days": 63,
                "percentile_lookback_days": 252,
            }
        },
        "transition_smoothing": {"enabled": True, "window_days": 5},
        "regime_weights": {
            "low_vol_trending": {"TrendCore": 0.30, "TrendImpulse": 0.70},
            "low_vol_transitional": {"TrendCore": 0.50, "TrendImpulse": 0.50},
            "low_vol_ranging": {"TrendCore": 0.50, "TrendImpulse": 0.50},
            "medium_vol_trending": {"TrendCore": 0.60, "TrendImpulse": 0.40},
            "medium_vol_transitional": {"TrendCore": 0.50, "TrendImpulse": 0.50},
            "medium_vol_ranging": {"TrendCore": 0.50, "TrendImpulse": 0.50},
            "high_vol_trending": {"TrendCore": 0.60, "TrendImpulse": 0.40},
            "high_vol_transitional": {
                "TrendCore": 0.20,
                "TrendImpulse": 0.05,
                "Cash": 0.75,
                "risk_overlay": {"exposure_scalar": 0.25},
            },
            "high_vol_ranging": {"TrendCore": 0.50, "TrendImpulse": 0.50},
        },
    }

    # Create portfolio
    print("\nInitializing adaptive portfolio...")
    portfolio = AdaptivePortfolio(sleeves_dict, config)

    # Run backtest
    daily_series, metrics, regime_log = portfolio.backtest_adaptive_strategy()

    # Save sample outputs
    print("\nSample regime log (last 10 days):")
    print(
        regime_log.tail(10)[
            ["date", "regime", "TrendCore_weight", "TrendImpulse_weight"]
        ]
    )

    print("\n✅ Adaptive portfolio test complete!")
