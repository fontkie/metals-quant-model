from __future__ import annotations
from pathlib import Path
from typing import Any, Dict
import yaml

"""
Purpose:
- Load a single execution/cost policy block for the whole project.
- Provide safe defaults if Config/schema.yaml is missing.
- Print a clear banner so every run shows the real-world assumptions.
- Warn when a script's hard-coded assumptions diverge from policy.

Per-sleeve differences (exec weekdays, event-driven etc.) live in each sleeve's YAML.
Each sleeve must still export `position_Tplus1` so the composite can line them up.
"""

DEFAULT_SCHEMA_PATH = Path("Config/schema.yaml")


def _get(d: Dict, path: str, default=None):
    cur = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def load_execution_policy(
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
) -> Dict[str, Any]:
    p = Path(schema_path)
    if not p.exists():
        # SAFE DEFAULTS (Mon/Wed/Fri exec; T-1 origin for midweek; PnL starts next day)
        return {
            "calendar": {
                "exec_weekdays": [0, 2, 4],  # Mon, Wed, Fri
                "origin_for_exec": {"0": "-3B", "2": "-1B", "4": "-1B"},
                "fill_default": "close_T",  # signals formed on T close
                "pnl_starts_next_day": True,  # positions effective next day
            },
            "sizing": {
                "ann_target": 0.10,
                "vol_lookback_days_default": 21,
                "vol_estimator": "simple_returns_std",
                "vol_info_timing_default": "T",
                "leverage_cap_default": 2.5,
                "hold_between_rebalances": True,
            },
            "costs": {
                "one_way_bps_default": 1.5,
                "apply_on_position_change_only": True,
            },
            "pnl": {"formula": "pos_lag_times_simple_return"},
            "schema_path": str(p),
            "_exists": False,
        }

    with p.open("r", encoding="utf-8") as f:
        y = yaml.safe_load(f) or {}
    exec_block = y.get("execution", {})
    exec_block["schema_path"] = str(p)
    exec_block["_exists"] = True
    return exec_block


def policy_banner(
    policy: Dict[str, Any], sleeve_name: str, overrides: Dict[str, Any] | None = None
) -> str:
    ov = overrides or {}

    def pick(key_path, default):
        return ov.get(key_path, _get(policy, key_path, default))

    lines = [
        f"[policy] schema: {policy.get('schema_path')}",
        f"[policy] sleeve: {sleeve_name}",
        f"[policy] calendar.exec_weekdays: {pick('calendar.exec_weekdays', [0,2,4])}",
        f"[policy] calendar.origin_for_exec: {pick('calendar.origin_for_exec', {'0':'-3B','2':'-1B','4':'-1B'})}",
        f"[policy] calendar.fill_default: {pick('calendar.fill_default', 'close_T')}",
        f"[policy] sizing.ann_target: {pick('sizing.ann_target', 0.10)}",
        f"[policy] sizing.vol_lookback_days_default: {pick('sizing.vol_lookback_days_default', 21)}",
        f"[policy] sizing.vol_info_timing_default: {pick('sizing.vol_info_timing_default', 'T')}",
        f"[policy] sizing.leverage_cap_default: {pick('sizing.leverage_cap_default', 2.5)}",
        f"[policy] costs.one_way_bps_default: {pick('costs.one_way_bps_default', 1.5)}",
        f"[policy] pnl.formula: {pick('pnl.formula', 'pos_lag_times_simple_return')}",
    ]
    return "\n".join(lines)


def warn_if_mismatch(
    policy: Dict[str, Any],
    *,
    exec_weekdays=(0, 2, 4),
    fill_timing="close_T",
    vol_info="T",
    leverage_cap=2.5,
    one_way_bps=1.5,
) -> list[str]:
    msgs = []
    pol_days = tuple(_get(policy, "calendar.exec_weekdays", [0, 2, 4]))
    if pol_days != tuple(exec_weekdays):
        msgs.append(
            f"[policy][WARN] exec_weekdays policy={pol_days} script={exec_weekdays}"
        )
    pol_fill = _get(policy, "calendar.fill_default", "close_T")
    if pol_fill != fill_timing:
        msgs.append(
            f"[policy][WARN] fill_default policy={pol_fill} script={fill_timing}"
        )
    pol_volinfo = _get(policy, "sizing.vol_info_timing_default", "T")
    if pol_volinfo != vol_info:
        msgs.append(f"[policy][WARN] vol_info policy={pol_volinfo} script={vol_info}")
    pol_cap = float(_get(policy, "sizing.leverage_cap_default", 2.5))
    if pol_cap != float(leverage_cap):
        msgs.append(
            f"[policy][WARN] leverage_cap policy={pol_cap} script={leverage_cap}"
        )
    pol_bps = float(_get(policy, "costs.one_way_bps_default", 1.5))
    if pol_bps != float(one_way_bps):
        msgs.append(f"[policy][WARN] one_way_bps policy={pol_bps} script={one_way_bps}")
    return msgs
