# src/core/regime.py
"""
Regime Detection - Market State Classification
===============================================

Classifies market state into 9 regime buckets:
- Volatility dimension: LOW / MEDIUM / HIGH (33rd/67th percentile)
- Trend dimension: TRENDING / TRANSITIONAL / RANGING (to be implemented)

Combined: e.g., 'low_vol_trending', 'high_vol_transitional', etc.

Two modes:
  - RESEARCH: Rolling percentile window (minor lookahead bias, fast)
  - PRODUCTION: Expanding window (no lookahead, production-safe)

Author: Claude (ex-Renaissance)
Date: November 4, 2025
Version: 1.0
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional


class RegimeDetector:
    """
    Detect market regime based on volatility and trend characteristics.

    Attributes:
        mode (str): 'research' or 'production'
        vol_window (int): Days for realized vol calculation (default: 63)
        percentile_window (int): Days for percentile ranking (default: 252)
        low_vol_threshold (float): Percentile for low vol cutoff (default: 0.33)
        high_vol_threshold (float): Percentile for high vol cutoff (default: 0.67)
    """

    def __init__(
        self,
        mode: str = "research",
        vol_window: int = 63,
        percentile_window: int = 252,
        low_vol_threshold: float = 0.33,
        high_vol_threshold: float = 0.67,
        min_history_days: int = 252,
    ):
        """
        Initialize RegimeDetector.

        Args:
            mode: 'research' (rolling window) or 'production' (expanding window)
            vol_window: Days for realized vol calculation (industry standard: 63)
            percentile_window: Days for percentile ranking (research mode only)
            low_vol_threshold: Bottom percentile for LOW vol (default: 0.33)
            high_vol_threshold: Top percentile for HIGH vol (default: 0.67)
            min_history_days: Minimum history before classifying (production mode)
        """
        if mode not in ["research", "production"]:
            raise ValueError(f"mode must be 'research' or 'production', got {mode}")

        self.mode = mode
        self.vol_window = vol_window
        self.percentile_window = percentile_window
        self.low_vol_threshold = low_vol_threshold
        self.high_vol_threshold = high_vol_threshold
        self.min_history_days = min_history_days

        # Cache for production mode thresholds (avoids recomputing)
        self._production_thresholds_cache = {}

    def calculate_realized_vol(self, price_series: pd.Series) -> pd.Series:
        """
        Calculate annualized realized volatility.

        Args:
            price_series: Daily price series

        Returns:
            pd.Series: Annualized realized volatility (252 trading days)
        """
        returns = price_series.pct_change()
        vol = returns.rolling(
            window=self.vol_window, min_periods=self.vol_window
        ).std() * np.sqrt(252)

        return vol

    def detect_vol_regime_research(self, vol_series: pd.Series) -> pd.Series:
        """
        Detect vol regime using rolling percentile window (RESEARCH MODE).

        WARNING: This method has minor lookahead bias. Use for backtesting only.

        Args:
            vol_series: Realized volatility series

        Returns:
            pd.Series: Regime labels ('LOW', 'MEDIUM', 'HIGH')
        """
        # Calculate rolling percentile rank
        vol_percentile = vol_series.rolling(
            window=self.percentile_window, min_periods=self.vol_window
        ).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else 0.5,
            raw=False,
        )

        # Classify based on percentile
        regime = pd.Series(index=vol_series.index, dtype=str)
        regime[vol_percentile < self.low_vol_threshold] = "LOW"
        regime[
            (vol_percentile >= self.low_vol_threshold)
            & (vol_percentile < self.high_vol_threshold)
        ] = "MEDIUM"
        regime[vol_percentile >= self.high_vol_threshold] = "HIGH"

        return regime

    def detect_vol_regime_production(self, vol_series: pd.Series) -> pd.Series:
        """
        Detect vol regime using expanding window (PRODUCTION MODE).

        NO LOOKAHEAD BIAS. Suitable for live trading.

        Args:
            vol_series: Realized volatility series

        Returns:
            pd.Series: Regime labels ('LOW', 'MEDIUM', 'HIGH')
        """
        regime = pd.Series(index=vol_series.index, dtype=str)

        for i in range(len(vol_series)):
            date = vol_series.index[i]

            # Need minimum history before classifying
            if i < self.min_history_days:
                regime.iloc[i] = "MEDIUM"  # Default to medium
                continue

            # Use only historical data (no future)
            historical_vol = vol_series.iloc[:i]

            # Calculate thresholds from history
            low_thresh = historical_vol.quantile(self.low_vol_threshold)
            high_thresh = historical_vol.quantile(self.high_vol_threshold)

            # Classify current vol
            current_vol = vol_series.iloc[i]

            if pd.isna(current_vol):
                regime.iloc[i] = "MEDIUM"
            elif current_vol < low_thresh:
                regime.iloc[i] = "LOW"
            elif current_vol < high_thresh:
                regime.iloc[i] = "MEDIUM"
            else:
                regime.iloc[i] = "HIGH"

        return regime

    def detect_vol_regime(self, price_series: pd.Series) -> Tuple[pd.Series, pd.Series]:
        """
        Main entry point for volatility regime detection.

        Args:
            price_series: Daily price series

        Returns:
            Tuple of (vol_series, regime_series)
            - vol_series: Realized volatility
            - regime_series: Regime labels ('LOW', 'MEDIUM', 'HIGH')
        """
        # Calculate realized vol
        vol_series = self.calculate_realized_vol(price_series)

        # Detect regime based on mode
        if self.mode == "research":
            regime_series = self.detect_vol_regime_research(vol_series)
        else:  # production
            regime_series = self.detect_vol_regime_production(vol_series)

        return vol_series, regime_series

    def detect_trend_regime(self, price_series: pd.Series) -> pd.Series:
        """
        Detect trend regime (TRENDING / TRANSITIONAL / RANGING).

        TODO: Implement proper trend classification.
        For MVP, using simplified heuristic based on 30/100d MA relationship.

        Args:
            price_series: Daily price series

        Returns:
            pd.Series: Trend regime labels
        """
        # Calculate moving averages
        ma_fast = price_series.rolling(30).mean()
        ma_slow = price_series.rolling(100).mean()

        # Calculate trend strength (MA separation)
        ma_separation = (ma_fast - ma_slow) / ma_slow

        # Calculate range tightness (20-day high-low range)
        rolling_high = price_series.rolling(20).max()
        rolling_low = price_series.rolling(20).min()
        range_pct = (rolling_high - rolling_low) / price_series

        # Classify trend regime
        regime = pd.Series(index=price_series.index, dtype=str)

        # TRENDING: Clear MA separation and wider range
        trending_mask = (abs(ma_separation) > 0.05) & (range_pct > 0.08)
        regime[trending_mask] = "TRENDING"

        # RANGING: Tight range and minimal MA separation
        ranging_mask = (abs(ma_separation) < 0.02) & (range_pct < 0.06)
        regime[ranging_mask] = "RANGING"

        # TRANSITIONAL: Everything else (MA crossovers, uncertain direction)
        regime[(~trending_mask) & (~ranging_mask)] = "TRANSITIONAL"

        # Handle NaN from rolling calculations
        regime = regime.fillna("TRANSITIONAL")

        return regime

    def detect_combined_regime(self, price_series: pd.Series) -> pd.DataFrame:
        """
        Detect combined (vol × trend) regime.

        Args:
            price_series: Daily price series

        Returns:
            pd.DataFrame with columns:
              - vol: Realized volatility
              - vol_regime: LOW/MEDIUM/HIGH
              - trend_regime: TRENDING/TRANSITIONAL/RANGING
              - combined_regime: e.g., 'low_vol_trending'
              - vol_percentile: Percentile rank (research mode only)
        """
        # Detect volatility regime
        vol_series, vol_regime = self.detect_vol_regime(price_series)

        # Detect trend regime
        trend_regime = self.detect_trend_regime(price_series)

        # Combine regimes (handle NaN)
        combined_regime = (
            vol_regime.fillna("MEDIUM").str.lower()
            + "_vol_"
            + trend_regime.fillna("TRANSITIONAL").str.lower()
        )

        # Calculate vol percentile for monitoring (research mode)
        if self.mode == "research":
            vol_percentile = vol_series.rolling(
                window=self.percentile_window, min_periods=self.vol_window
            ).apply(
                lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else 0.5,
                raw=False,
            )
        else:
            # For production, calculate expanding percentile
            vol_percentile = pd.Series(index=vol_series.index, dtype=float)
            for i in range(len(vol_series)):
                if i < self.min_history_days:
                    vol_percentile.iloc[i] = 0.5
                else:
                    historical_vol = vol_series.iloc[:i]
                    current_vol = vol_series.iloc[i]
                    if pd.notna(current_vol):
                        vol_percentile.iloc[i] = (historical_vol < current_vol).mean()
                    else:
                        vol_percentile.iloc[i] = 0.5

        # Build result DataFrame
        result = pd.DataFrame(
            {
                "vol": vol_series,
                "vol_regime": vol_regime,
                "trend_regime": trend_regime,
                "combined_regime": combined_regime,
                "vol_percentile": vol_percentile,
            },
            index=price_series.index,
        )

        return result

    def get_regime_distribution(self, regime_series: pd.Series) -> pd.DataFrame:
        """
        Calculate regime distribution statistics.

        Args:
            regime_series: Series of regime labels

        Returns:
            pd.DataFrame: Regime frequency and statistics
        """
        # Count occurrences
        counts = regime_series.value_counts()

        # Calculate percentages
        pcts = (counts / len(regime_series) * 100).round(1)

        # Build result
        result = pd.DataFrame(
            {
                "count": counts,
                "pct_of_time": pcts,
                "target_pct": 33.3,  # Expected if balanced
            }
        )

        result["deviation"] = (result["pct_of_time"] - result["target_pct"]).round(1)

        return result.sort_values("count", ascending=False)

    def validate_regime_detection(self, regime_df: pd.DataFrame) -> dict:
        """
        Validate regime detection quality.

        Args:
            regime_df: Output from detect_combined_regime()

        Returns:
            dict: Validation metrics
        """
        validation = {}

        # Vol regime distribution (should be ~33% each)
        vol_dist = self.get_regime_distribution(regime_df["vol_regime"])
        validation["vol_distribution"] = vol_dist

        # Check balance (deviation from 33.3%)
        max_deviation = vol_dist["deviation"].abs().max()
        validation["vol_balance"] = "GOOD" if max_deviation < 10 else "IMBALANCED"

        # Trend regime distribution
        trend_dist = self.get_regime_distribution(regime_df["trend_regime"])
        validation["trend_distribution"] = trend_dist

        # Regime persistence (average days in same regime)
        regime_changes = (
            regime_df["combined_regime"] != regime_df["combined_regime"].shift(1)
        ).sum()
        avg_persistence = len(regime_df) / regime_changes
        validation["avg_regime_persistence_days"] = round(avg_persistence, 1)
        validation["regime_persistence"] = (
            "GOOD"
            if 10 <= avg_persistence <= 40
            else "TOO_FREQUENT" if avg_persistence < 10 else "TOO_STABLE"
        )

        # NaN check
        nan_pct = regime_df["combined_regime"].isna().sum() / len(regime_df) * 100
        validation["nan_pct"] = round(nan_pct, 2)
        validation["data_quality"] = "GOOD" if nan_pct < 5 else "POOR"

        return validation


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def detect_regime_simple(
    price_series: pd.Series, mode: str = "research"
) -> pd.DataFrame:
    """
    Convenience function for simple regime detection.

    Args:
        price_series: Daily price series
        mode: 'research' or 'production'

    Returns:
        pd.DataFrame: Regime classification results
    """
    detector = RegimeDetector(mode=mode)
    return detector.detect_combined_regime(price_series)


def load_and_detect_regime(
    csv_path: str, price_column: str = "price", mode: str = "research"
) -> pd.DataFrame:
    """
    Load CSV and detect regimes in one step.

    Args:
        csv_path: Path to CSV with price data
        price_column: Name of price column
        mode: 'research' or 'production'

    Returns:
        pd.DataFrame: Regime classification results
    """
    # Load data
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)

    # Detect regimes
    detector = RegimeDetector(mode=mode)
    regime_df = detector.detect_combined_regime(df[price_column])

    return regime_df


# ============================================================================
# MAIN - For Testing
# ============================================================================

if __name__ == "__main__":
    """
    Test regime detection on copper data
    """
    import os

    print("=" * 80)
    print("REGIME DETECTOR - Test Mode")
    print("=" * 80)

    # Try to load copper data from project
    copper_paths = [
        "/mnt/project/copper_lme_3mo_canonical.csv",
        "copper_lme_3mo_canonical.csv",
        "../../../Data/copper/pricing/canonical/copper_lme_3mo_canonical.csv",
    ]

    copper_path = None
    for path in copper_paths:
        if os.path.exists(path):
            copper_path = path
            break

    if copper_path is None:
        print("❌ Could not find copper data file")
        print(f"Searched: {copper_paths}")
        exit(1)

    print(f"\n✅ Loading data from: {copper_path}")

    # Load and detect
    regime_df = load_and_detect_regime(copper_path, mode="research")

    print(f"\n📊 Detected {len(regime_df)} days of data")
    print(f"Date range: {regime_df.index[0]} to {regime_df.index[-1]}")

    # Validate
    detector = RegimeDetector(mode="research")
    validation = detector.validate_regime_detection(regime_df)

    print("\n" + "=" * 80)
    print("VOLATILITY REGIME DISTRIBUTION")
    print("=" * 80)
    print(validation["vol_distribution"])
    print(f"\nBalance: {validation['vol_balance']}")

    print("\n" + "=" * 80)
    print("TREND REGIME DISTRIBUTION")
    print("=" * 80)
    print(validation["trend_distribution"])

    print("\n" + "=" * 80)
    print("REGIME PERSISTENCE")
    print("=" * 80)
    print(f"Average days per regime: {validation['avg_regime_persistence_days']}")
    print(f"Assessment: {validation['regime_persistence']}")

    print("\n" + "=" * 80)
    print("SAMPLE REGIMES (Last 10 Days)")
    print("=" * 80)
    print(regime_df[["combined_regime", "vol_percentile", "vol"]].tail(10))

    print("\n✅ Regime detection test complete!")
