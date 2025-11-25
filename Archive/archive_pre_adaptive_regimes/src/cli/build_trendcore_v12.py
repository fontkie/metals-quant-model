import os, json, hashlib
from datetime import datetime
import pandas as pd
import numpy as np
import yaml

# ---------- Config paths ----------
COMMODITY = "Copper"
SLEEVE = "TrendCore"
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

# ---------- Load data ----------
df_price = pd.read_excel(PRICE_PATH, sheet_name="Raw")
df_vol = pd.read_excel(VOL_PATH, sheet_name="Sheet1")
if not np.issubdtype(df_price["Date"].dtype, np.datetime64):
    df_price["Date"] = pd.to_timedelta(df_price["Date"], unit="D") + datetime(
        1899, 12, 30
    )
if not np.issubdtype(df_vol["Date"].dtype, np.datetime64):
    df_vol["Date"] = pd.to_timedelta(df_vol["Date"], unit="D") + datetime(1899, 12, 30)

df = pd.merge(
    df_price[["Date", "copper_lme_3mo"]],
    df_vol[["Date", "copper_lme_3mo_impliedvol"]],
    on="Date",
    how="left",
)
df.rename(
    columns={"copper_lme_3mo": "Price", "copper_lme_3mo_impliedvol": "iv"}, inplace=True
)
df = df.sort_values("Date").dropna(subset=["Price"]).reset_index(drop=True)
df["iv"] = df["iv"].replace("#N/A N/A", np.nan)

# Compute returns
df["ret"] = df["Price"].pct_change()

# ---------- Global policy params ----------
ann_target = config["policy"]["sizing"]["ann_target"]
vol_lb = config["policy"]["sizing"]["vol_lookback_days_default"]
lev_cap = config["policy"]["sizing"]["leverage_cap_default"]
one_way_bps = config["policy"]["costs"]["one_way_bps_default"] / 10000

# ---------- SIGNAL BLOCK (TrendCore v1.3) ----------
sp = config["signal"]
df["rv"] = df["ret"].rolling(vol_lb).std() * np.sqrt(252).shift(1)
df["lb"] = np.where(
    df["rv"] > sp["vol_threshold_for_lb"], sp["z_std_lb_short"], sp["z_std_lb_default"]
)
df["log_price"] = np.log(df["Price"])


# Variable rolling (custom function for dynamic window)
def var_rolling(series, lb_series, func):
    result = pd.Series(np.nan, index=series.index)
    for i in range(len(series)):
        lb = int(lb_series.iloc[i])
        window = series.iloc[max(0, i - lb + 1) : i + 1]
        if len(window) >= 10:  # Min periods
            result.iloc[i] = func(window)
    return result.shift(1)  # Shift for no lookahead


df["rolling_mean"] = var_rolling(df["log_price"], df["lb"], np.mean)
df["rolling_std"] = var_rolling(df["log_price"], df["lb"], np.std)
df["z"] = (df["log_price"] - df["rolling_mean"]) / df["rolling_std"]

# Vol filter
df["iv_pctl"] = (
    df["iv"]
    .rolling(sp["lookback_vol_period"])
    .quantile(sp["vol_filter_percentile"] / 100)
    .shift(1)
)
df["filter_flat"] = (df["iv"] > df["iv_pctl"]) & df["iv"].notna()

# Signal
df["signal"] = np.where(
    df["z"] >= sp["threshold_long"],
    1,
    np.where(df["z"] <= sp["threshold_short"], -1, 0),
)
df["signal"] = np.where(df["filter_flat"], 0, df["signal"])

# Positions (only on trade days)
exec_days = config["calendar"]["exec_weekdays"]
df["weekday"] = df["Date"].dt.weekday
is_trade_day = df["weekday"].isin(exec_days)
df["position"], prev_pos = 0.0, 0.0
for i in range(1, len(df)):
    if is_trade_day.iloc[i]:
        prev_pos = df["signal"].iloc[i]
    df["position"].iloc[i] = prev_pos

# Sizing, costs, PnL
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
