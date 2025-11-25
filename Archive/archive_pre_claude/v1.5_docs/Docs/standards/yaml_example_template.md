yaml_example_template.md (v2.1)

Purpose
Authoritative YAML template for sleeves. Fields marked required must be present.

# Config/<Commodity>/<sleeve>.yaml

io:
  commodity: Copper           # required
  sleeve: CrashAndRecover     # required

policy:
  calendar:                   # required
    exec_weekdays: [0,1,2,3,4]
    origin_for_exec: {"0":"-1B","1":"-1B","2":"-1B","3":"-1B","4":"-1B"}
    fill_default: close_T

  sizing:                     # required
    ann_target: 0.10
    vol_lookback_days_default: 21
    leverage_cap_default: 2.5

  costs:                      # required
    one_way_bps_default: 1.5

  pnl:                        # required
    formula: pos_lag_times_simple_return
    t_plus_one_pnl: true

# Sleeve-specific signal parameters (free-form)
signal:
  # examples (delete/edit for your sleeve)
  trend_window: 63
  vol_window: 21
  entry_z: 0.5
  exit_z: 0.0
  exit_timeout_days: 63
  volume_lookback: 21
  volume_threshold_multiple: 1.5


Notes

No Excel paths/columns here; builds read canonical CSV (date,price) only.

pnl.formula must be pos_lag_times_simple_return for live-safe T→T+1.

Add any sleeve-specific keys under signal:; the core will pass them to your signal.

Validation checklist

io.commodity & io.sleeve present ✅

policy blocks present ✅

pnl.t_plus_one_pnl: true ✅

Signal params defined (as needed) ✅