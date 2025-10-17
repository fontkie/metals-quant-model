import copy
import math
from itertools import product


def deep_merge(a: dict, b: dict) -> dict:
    """Right-biased deep merge: values in b override a."""
    out = copy.deepcopy(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def expand_grid_coarse(grids: dict) -> list[dict]:
    """Expand coarse grid where each key has a list of values."""
    keys, values = [], []
    for k, vals in grids.items():
        if isinstance(vals, dict):
            continue
        keys.append(k)
        values.append(vals)
    combos = []
    for combo in product(*values):
        combos.append({k: v for k, v in zip(keys, combo)})
    return combos


def _mk_band(v_best: float, band_pct: float, min_band: float, step: float, bounds=None):
    lo = v_best - max(min_band, abs(v_best) * band_pct)
    hi = v_best + max(min_band, abs(v_best) * band_pct)
    if bounds:
        lo = max(lo, bounds[0])
        hi = min(hi, bounds[1])
    lo_i, hi_i = int(round(lo)), int(round(hi))
    st = max(1, int(round(step)))
    return sorted(set(range(lo_i, hi_i + 1, st)))


def expand_grid_local(
    template: dict, prev_best: dict, coarse_bounds: dict, max_total: int = 120
) -> list[dict]:
    """Create a local grid around previous best using template."""
    keys, values = [], []
    for k, spec in template.items():
        if "candidates" in spec:
            vals = spec["candidates"]
        else:
            bp = spec.get("band_pct", 0.10)
            mb = spec.get("min_band", 3)
            st = spec.get("step", 1)
            bounds = None
            if (
                k in coarse_bounds
                and isinstance(coarse_bounds[k], list)
                and len(coarse_bounds[k]) > 0
            ):
                bounds = (min(coarse_bounds[k]), max(coarse_bounds[k]))
            vals = _mk_band(prev_best[k], bp, mb, st, bounds=bounds)
        keys.append(k)
        values.append(vals)
    combos = []
    for combo in product(*values):
        combos.append({k: v for k, v in zip(keys, combo)})
    if len(combos) > max_total:
        stride = math.ceil(len(combos) / max_total)
        combos = combos[::stride]
    return combos


def composite_score(
    sharpe, dd_pct, turnover, tail_ratio, ws=1.0, wdd=0.2, wto=0.05, wtail=0.0
):
    return ws * sharpe - wdd * abs(dd_pct) - wto * turnover + wtail * tail_ratio
