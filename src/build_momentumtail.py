import os, json, hashlib
from datetime import datetime
import pandas as pd
import numpy as np
import yaml

# ---------- Config paths ----------
COMMODITY = "Copper"
SLEEVE = "MomentumTail"
YAML_PATH = f"Config/{COMMODITY.lower()}/{SLEEVE.lower()}.yaml"
PRICE_PATH = f"Data/{COMMODITY.lower()}/pricing/pricing_values.xlsx"
VOL_PATH = f"Data/{COMMODITY.lower()}/vol/vol_values.xlsx"
OUT_DIR = f"outputs/{COMMODITY}/{SLEEVE}"
OUT_CSV = os.path.join(OUT_DIR, "daily_series.csv")
RUN_JSON = os.path.join(OUT_DIR, "run_config.json")


# ---------- Helpers ----------
def _sha256_file(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except Exception:
        return None


def write_run_header(params, df):
    os.makedirs(OUT_DIR, exist_ok=True)
    header = {
        "run_ts": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "yaml_path": YAML_PATH,
        "yaml_sha": _sha256_file(YAML_PATH),
        "code_sha": _sha256_file(__file__),
        "pnl_convention": "T+1 (pos_{t-1} * ret_t), costs on turnover.shift(1)",
        "costs_one_way_bps": params["policy"]["costs"]["one_way_bps_default"],
        "ann_target_vol": params["policy"]["sizing"]["ann_target"],
        "vol_lookback_days": params["policy"]["sizing"]["vol_lookback_days_default"],
        "leverage_cap": params["policy"]["sizing"]["leverage_cap_default"],
        "signal": params["signal"],
        "data_start": str(df["Date"].min().date()),
        "data_end": str(df["Date"].max().date()),
        "lookahead_protection": True,
    }
    print("\n=== RUN HEADER ===")
    for k, v in header.items():
        print(f"{k}: {v}")
    print("=== END HEADER ===\n")
    with open(RUN_JSON, "w") as f:
        json.dump(header, f, indent=2)


# ---------- Load YAML ----------
with open(YAML_PATH, "r") as f:
    config = yaml.safe_load(f)

# ---------- Load price and vol data ----------
df_price = pd.read_excel(PRICE_PATH, sheet_name="Raw")
df_vol = pd.read_excel(VOL_PATH, sheet_name="Sheet1")

if not pd.api.types.is_datetime64_any_dtype(df_price["Date"]):
    df_price["Date"] = pd.to_timedelta(df_price["Date"], unit="D") + datetime(
        1899, 12, 30
    )
if not pd.api.types.is_datetime64_any_dtype(df_vol["Date"]):
    df_vol["Date"] = pd.to_timedelta(df_vol["Date"], unit="D") + datetime(1899, 12, 30)

df = df_price[["Date", "copper_lme_3mo"]].copy()
df = df.merge(df_vol[["Date", "copper_lme_1mo_impliedvol"]], on="Date", how="left")
df = df.rename(
    columns={"copper_lme_3mo": "Price", "copper_lme_1mo_impliedvol": "implied_vol1mo"}
)
df = df.sort_values("Date").dropna(subset=["Price"]).reset_index(drop=True)

df["ret"] = df["Price"].pct_change()

# Apply calendar
df["weekday"] = df["Date"].dt.weekday
exec_weekdays = config["calendar"]["exec_weekdays"]
df = df[df["weekday"].isin(exec_weekdays)].copy()

# ---------- Signal block ----------
sp = config["signal"]
one_way_bps = config["policy"]["costs"]["one_way_bps_default"] / 10000
ann_target = config["policy"]["sizing"]["ann_target"]
vol_lb = config["policy"]["sizing"]["vol_lookback_days_default"]
lev_cap = config["policy"]["sizing"]["leverage_cap_default"]

df["atr20"] = df["Price"].shift(1) * df["ret"].rolling(20).std() * np.sqrt(20).shift(1)

df["donch_high_prev"] = df["Price"].rolling(sp["breakout_window"]).max().shift(1)
df["donch_low_prev"] = df["Price"].rolling(sp["exit_window"]).min().shift(1)

df["vol_mean252"] = df["implied_vol1mo"].rolling(sp["vol_z_lookback"]).mean()
df["vol_std252"] = df["implied_vol1mo"].rolling(sp["vol_z_lookback"]).std()
df["vol_zscore252"] = (df["implied_vol1mo"] - df["vol_mean252"]) / df["vol_std252"]
if sp["use_rv_proxy"]:
    rv_proxy = df["ret"].rolling(21).std() * np.sqrt(252)
    df["vol_zscore252"] = df["vol_zscore252"].fillna(rv_proxy / rv_proxy.mean())
else:
    df["vol_zscore252"] = df["vol_zscore252"].fillna(0.1)

df["overshoot"] = (df["Price"] - df["donch_high_prev"]) >= sp[
    "overshoot_multiple"
] * df["atr20"]
df["breakout"] = df["Price"] > df["donch_high_prev"]
df["vol_gate"] = df["vol_zscore252"] > sp["z_threshold"]
df["signal"] = df["breakout"] & df["overshoot"] & df["vol_gate"]

# Position logic
df["position"] = 0.0
df["trailing_high"] = np.nan
df["trailing_stop_level"] = np.nan
holding = False
current_trailing_high = np.nan
for i in range(max(sp["breakout_window"], sp["vol_z_lookback"]) + 1, len(df)):
    if not holding and df.loc[i, "signal"]:
        df.loc[i, "position"] = 1.0
        holding = True
        current_trailing_high = df.loc[i, "Price"]
        df.loc[i, "trailing_high"] = current_trailing_high
        df["trailing_stop_level"].loc[i] = (
            current_trailing_high - sp["atr_multiple_trailing"] * df.loc[i, "atr20"]
        )
    elif holding:
        df.loc[i, "position"] = 1.0
        if df.loc[i, "Price"] > current_trailing_high:
            current_trailing_high = df.loc[i, "Price"]
        df.loc[i, "trailing_high"] = current_trailing_high
        df["trailing_stop_level"].loc[i] = (
            current_trailing_high - sp["atr_multiple_trailing"] * df.loc[i, "atr20"]
        )
        if (df.loc[i, "Price"] < df.loc[i, "donch_low_prev"]) or (
            df.loc[i, "Price"] < df.loc[i, "trailing_stop_level"]
        ):
            df.loc[i, "position"] = 0.0
            holding = False
    else:
        df.loc[i, "position"] = 0.0

# ---------- Sizing, costs, PnL ----------
df["rv"] = df["ret"].rolling(vol_lb).std() * np.sqrt(252)
df["lev"] = (ann_target / df["rv"].clip(lower=1e-8)).clip(upper=lev_cap)
df["turnover"] = (df["position"] - df["position"].shift(1)).abs()
df["costs"] = df["turnover"].shift(1) * one_way_bps * df["lev"].shift(1)
df["ret_pos"] = df["position"].shift(1) * df["ret"] * df["lev"].shift(1)
df["pnl"] = df["ret_pos"] - df["costs"]
df["equity"] = (1 + df["pnl"].fillna(0)).cumprod()

# ---------- Write outputs ----------
os.makedirs(OUT_DIR, exist_ok=True)
cols = [
    "Date",
    "Price",
    "ret",
    "signal",
    "position",
    "lev",
    "ret_pos",
    "costs",
    "pnl",
    "equity",
    "rv",
]
df[cols].to_csv(OUT_CSV, index=False)

# ---------- Provenance ----------
write_run_header(config, df)

print(f"Saved: {OUT_CSV}")
