sleeve: TrendCore
calendar:
  exec_weekdays: [0, 2]
  origin_for_exec: {"0": "-1B", "2": "-1B"}
policy:
  sizing: { ann_target: 0.10, vol_lookback_days_default: 28, leverage_cap_default: 2.5 }
  costs: { one_way_bps_default: 1.5 }
signal:
  z_std_lb_default: 252
  z_std_lb_short: 126
  vol_threshold_for_lb: 0.22  # Slight increase for robustness
  threshold_long: 0.6
  threshold_short: -0.85  # Minor asymmetry boost
  vol_filter_type: "percentile"
  vol_filter_percentile: 85  # Less aggressive filtering
  lookback_vol_period: 252
pnl:
  formula: pos_lag_times_simple_return