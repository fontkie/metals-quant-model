#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CrashAndRecover — live-safe builder (T+1 PnL, YAML + CLI driven)
- Updated to standards: directional vol, SMA gate, vol_gate, daily exec option.
"""

import argparse
import json
from pathlib import Path
from datetime import datetime as _dt

import numpy as np
import pandas as pd
import yaml
from pandas.api.types import is_datetime64_any_dtype

# ----------------------- Paths & CLI -----------------------
BASE = Path(__file__).resolve().parent  # .../src
REPO = BASE.parent  # repo root

DEFAULT_COMMODITY = "Copper"
DEFAULT_SLEEVE = "CrashAndRecover"


def _default_yaml_path(commodity=DEFAULT_COMMODITY, sleeve=DEFAULT_SLEEVE):
    docs = REPO / "Docs" / commodity / sleeve / f"{sleeve}.yaml"
    if docs.exists():
        return docs
    return REPO / "Config" / commodity.lower() / f"{sleeve.lower()}.yaml"


DEFAULT_YAML = _default_yaml_path()
DEFAULT_XLSX = (
    REPO / "Data" / DEFAULT_COMMODITY.lower() / "pricing" / "pricing_values.xlsx"
)
DEFAULT_OUT = REPO / "outputs" / DEFAULT_COMMODITY / DEFAULT_SLEEVE


def _sha256_file(path: Path) -> str | None:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except Exception:
        return None


def _coerce_datetime(series: pd.Series) -> pd.Series:
    if is_datetime64_any_dtype(series):
        return series
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_datetime("1899-12-30") + pd.to_timedelta(
            series.astype(float), unit="D"
        )
    return pd.to_datetime(series, errors="coerce")


p = argparse.ArgumentParser()
p.add_argument("--yaml", type=Path, default=DEFAULT_YAML)
p.add_argument("--excel", type=Path, default=DEFAULT_XLSX)
p.add_argument("--outdir", type=Path, default=DEFAULT_OUT)
p.add_argument("--sheet", default="Raw")
p.add_argument("--date-col", default="Date")
p.add_argument("--price-col", default="copper_lme_3mo")
p.add_argument("--vol-col", default="copper_lme_3mo_volume")
args = p.parse_args()

CONFIG_PATH = args.yaml
PRICE_PATH = args.excel
OUTDIR = args.outdir
OUTDIR.mkdir(parents=True, exist_ok=True)

# ----------------------- Load YAML -----------------------
with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

POL = config.get("policy", {})
CAL = config.get("calendar", {})
SIZ = POL.get("sizing", {})
COST = POL.get("costs", {})
PNL = config.get("pnl", {})

SIG = config.get("signal", {})

commodity = DEFAULT_COMMODITY  # Or from config if present
sleeve = DEFAULT_SLEEVE

EXEC_WEEKDAYS = CAL.get("exec_weekdays", [0, 1, 2, 3, 4])
ORIGIN_FOR_EXEC = CAL.get("origin_for_exec", {str(i): "-1B" for i in EXEC_WEEKDAYS})

ANN_TARGET = float(SIZ.get("ann_target", 0.10))
VOL_LB = int(SIZ.get("vol_lookback_days_default", 21))
LEV_CAP = float(SIZ.get("leverage_cap_default", 2.5))

ONE_WAY_BPS = float(COST.get("one_way_bps_default", 1.5))

PNL_FORMULA = PNL.get("formula", "pos_lag_times_simple_return")

SMA_WIN = int(SIG.get("sma_window", 200))
STRUCT_WIN = int(SIG.get("structure_window", 60))
VOL_MEAN_WIN = int(SIG.get("volume_lookback", 20))
VOL_MULT = float(SIG.get("volume_threshold_multiple", 2.0))
VOL_GATE_THRESH = float(SIG.get("vol_gate_threshold", 0.25))
TIMEOUT_DAYS = int(SIG.get("exit_timeout_days", 90))

# ----------------------- Load price data -----------------------
df_price = pd.read_excel(PRICE_PATH, sheet_name=args.sheet)
df_price[args.date_col] = _coerce_datetime(df_price[args.date_col])

cols_in = [args.date_col, args.price_col]
if args.vol_col in df_price.columns:
    cols_in.append(args.vol_col)

cols_map = {
    args.date_col: "Date",
    args.price_col: "Price",
}
if args.vol_col in df_price.columns:
    cols_map[args.vol_col] = "volume"

df = (
    df_price[cols_in]
    .rename(columns=cols_map)
    .sort_values("Date")
    .dropna(subset=["Date", "Price"])
    .reset_index(drop=True)
)

if "volume" in df.columns:
    df["volume"] = df["volume"].fillna(df["volume"].mean())
else:
    df["volume"] = 1.0

df["ret"] = df["Price"].pct_change()

# ----------------------- Indicators -----------------------
df["sma"] = df["Price"].rolling(SMA_WIN).mean().shift(1)
df["structure_high"] = df["Price"].rolling(STRUCT_WIN).max().shift(1)
df["structure_high_prev"] = df["Price"].rolling(STRUCT_WIN).max().shift(1 + STRUCT_WIN)
df["structure_low"] = df["Price"].rolling(STRUCT_WIN).min().shift(1)
df["structure_low_prev"] = df["Price"].rolling(STRUCT_WIN).min().shift(1 + STRUCT_WIN)
df["volume_mean"] = df["volume"].rolling(VOL_MEAN_WIN).mean().shift(1)

# Directional volume
df["high_volume_down"] = (df["volume"] > VOL_MULT * df["volume_mean"]) & (df["ret"] < 0)
df["high_volume_up"] = (df["volume"] > VOL_MULT * df["volume_mean"]) & (df["ret"] > 0)

# Structure conditions
df["lower_high"] = df["structure_high"] < df["structure_high_prev"]
df["higher_low"] = df["structure_low"] > df["structure_low_prev"]

# Signals
df["short_signal"] = (
    (df["Price"] < df["sma"]) & df["lower_high"] & df["high_volume_down"]
)
df["long_signal"] = (df["Price"] > df["sma"]) & df["higher_low"] & df["high_volume_up"]
df["signal"] = 0
df.loc[df["long_signal"], "signal"] = 1
df.loc[df["short_signal"], "signal"] = -1

# ----------------------- Execution calendar -----------------------
df["weekday"] = df["Date"].dt.weekday
exec_days = set(EXEC_WEEKDAYS)
df["is_exec_day"] = df["weekday"].isin(exec_days)

# Queue signals to next exec day (simplified; assumes daily data)
df["queued_long"] = np.where(df["is_exec_day"], df["long_signal"], np.nan)
df["queued_short"] = np.where(df["is_exec_day"], df["short_signal"], np.nan)
df["queued_long"] = df["queued_long"].ffill()
df["queued_short"] = df["queued_short"].ffill()

# ----------------------- Position engine -----------------------
df["position"] = 0.0
holding = None
last_entry_dt = None

start_i = int(max(SMA_WIN, 2 * STRUCT_WIN)) + 1

for i in range(start_i, len(df)):
    df.loc[i, "position"] = df.loc[i - 1, "position"]

    if holding is not None and (df.loc[i, "Date"] - last_entry_dt).days > TIMEOUT_DAYS:
        df.loc[i, "position"] = 0.0
        holding = None
        continue

    if not df.loc[i, "is_exec_day"]:
        continue

    go_long = bool(df.loc[i, "queued_long"])
    go_short = bool(df.loc[i, "queued_short"])

    if go_long and holding != "long":
        df.loc[i, "position"] = 1.0
        holding = "long"
        last_entry_dt = df.loc[i, "Date"]

    if go_short and holding != "short":
        df.loc[i, "position"] = -1.0
        holding = "short"
        last_entry_dt = df.loc[i, "Date"]

    # Vol gate (flat if high vol)
    if df.loc[i, "rv"] > VOL_GATE_THRESH:
        df.loc[i, "position"] = 0.0
        holding = None

# ----------------------- Sizing (vol target) -----------------------
df["rv"] = df["ret"].rolling(VOL_LB).std(ddof=1).shift(1) * np.sqrt(252)
df["lev_raw"] = ANN_TARGET / df["rv"]
df["lev"] = df["lev_raw"].clip(upper=LEV_CAP).fillna(0.0)

# ----------------------- PnL (T+1) & costs -----------------------
df["turnover"] = df["position"].diff().abs().fillna(0.0)
bps = ONE_WAY_BPS / 10000.0

df["ret_pos"] = df["position"].shift(1) * df["ret"] * df["lev"].shift(1)
df["costs"] = df["turnover"].shift(1) * bps * df["lev"].shift(1)
df["pnl"] = (df["ret_pos"] - df["costs"]).fillna(0.0)
df["equity"] = (1.0 + df["pnl"]).cumprod()

# ----------------------- Outputs -----------------------
OUT_CSV = OUTDIR / "daily_series.csv"
cols = [
    "Date",
    "Price",
    "ret",
    "signal",
    "position",
    "rv",
    "lev",
    "turnover",
    "ret_pos",
    "costs",
    "pnl",
    "equity",
]  # Simplified to standard schema
df[cols].to_csv(OUT_CSV, index=False)

RUN_JSON = OUTDIR / "run_config.json"
run_header = {
    "commodity": commodity,
    "sleeve": sleeve,
    "timestamp_utc": _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "yaml_path": str(CONFIG_PATH),
    "yaml_sha256": _sha256_file(CONFIG_PATH),
    "code_sha256": _sha256_file(Path(__file__)),
    "pricing_path": str(PRICE_PATH),
    "pricing_sheet": args.sheet,
    "date_col": args.date_col,
    "price_col": args.price_col,
    "vol_col": args.vol_col,
    "calendar_exec_weekdays": EXEC_WEEKDAYS,
    "origin_for_exec": ORIGIN_FOR_EXEC,
    "ann_target": ANN_TARGET,
    "vol_lookback_days": VOL_LB,
    "leverage_cap": LEV_CAP,
    "costs_one_way_bps": ONE_WAY_BPS,
    "pnl_formula": PNL_FORMULA,
    "signal_params": SIG,
    "notes": "Updated to standards: T+1, directional vol, SMA gate, vol_gate applied, CLI-driven.",
}
with open(RUN_JSON, "w") as f:
    json.dump(run_header, f, indent=2)

print(f"[{sleeve}] Saved: {OUT_CSV}")
print(f"[{sleeve}] Saved: {RUN_JSON}")
