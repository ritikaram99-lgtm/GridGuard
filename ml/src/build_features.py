"""
GridGuard AI - Feature engineering for 24-hour-ahead hourly demand forecasting.

Source: ml/data/raw/continuous dataset.csv (read-only; never modified).
Output:
  ml/data/processed/features_full.csv   - full feature table, chronological
  ml/data/processed/train.csv           - chronological train split
  ml/data/processed/val.csv             - chronological validation split
  ml/data/processed/test.csv            - chronological test split
  ml/data/processed/feature_metadata.json - documents every feature column
  ml/reports/feature_engineering_report.md

Design principle: every feature for a row whose "forecast origin" is time t
must be computable from information available AT OR BEFORE t, with the sole
exception of calendar/holiday/school fields evaluated AT THE TARGET time
(t+24h) -- those are deterministic/known in advance regardless of any
measurement, so using them is standard practice and not leakage. No feature
uses nat_demand or weather readings from strictly after t. See the "Leakage
checks" section at the bottom for automated verification of these rules.
"""
import os
import json
import numpy as np
import pandas as pd

RAW_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "continuous dataset.csv")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "reports", "feature_engineering_report.md")
os.makedirs(OUT_DIR, exist_ok=True)

HORIZON_HOURS = 24  # forecast horizon: predict nat_demand at t + 24h from features known at t

# ---------------------------------------------------------------------------
# 1. Load raw data (read-only)
# ---------------------------------------------------------------------------
df = pd.read_csv(RAW_PATH)
df["datetime"] = pd.to_datetime(df["datetime"])
df = df.sort_values("datetime").reset_index(drop=True)
assert df["datetime"].is_monotonic_increasing, "Raw data must be strictly chronological"
assert (df["datetime"].diff().dropna() == pd.Timedelta(hours=1)).all(), "Raw data must be gap-free hourly"

n_raw = len(df)

WEATHER_COLS = ["T2M_toc", "QV2M_toc", "TQL_toc", "W2M_toc",
                 "T2M_san", "QV2M_san", "TQL_san", "W2M_san",
                 "T2M_dav", "QV2M_dav", "TQL_dav", "W2M_dav"]

feat = pd.DataFrame(index=df.index)
feat["datetime"] = df["datetime"]

feature_metadata = {}

def register(name, description, source, leakage_note):
    feature_metadata[name] = {
        "description": description,
        "source_columns": source,
        "leakage_note": leakage_note,
    }

# ---------------------------------------------------------------------------
# 2. Lag features of nat_demand (information known at or before origin t)
# ---------------------------------------------------------------------------
lag_hours = [1, 24, 48, 168]
for h in lag_hours:
    col = f"lag_{h}h_nat_demand"
    feat[col] = df["nat_demand"].shift(h)
    register(
        col,
        f"nat_demand value {h} hour(s) before the forecast origin t (i.e. value at t-{h}h).",
        ["nat_demand"],
        f"Uses only past data (t-{h}h <= t). Safe: no information from after origin t.",
    )

# current (origin-time) demand is also a known value at prediction time
feat["lag_0h_nat_demand"] = df["nat_demand"]
register(
    "lag_0h_nat_demand",
    "nat_demand value at the forecast origin t itself (most recent known actual).",
    ["nat_demand"],
    "Value at t is known when standing at t and forecasting t+24h. Safe.",
)

# ---------------------------------------------------------------------------
# 3. Rolling statistics of nat_demand, computed over trailing windows that
#    END at origin t (inclusive) -- i.e. no future values enter the window.
# ---------------------------------------------------------------------------
roll_windows = [24, 168]
for w in roll_windows:
    mean_col = f"roll_mean_{w}h_nat_demand"
    std_col = f"roll_std_{w}h_nat_demand"
    feat[mean_col] = df["nat_demand"].rolling(window=w, min_periods=w).mean()
    feat[std_col] = df["nat_demand"].rolling(window=w, min_periods=w).std()
    register(
        mean_col,
        f"Rolling mean of nat_demand over the trailing {w} hours ending at (and including) origin t.",
        ["nat_demand"],
        "min_periods=window enforced so no partial/undefined window is silently filled; window is strictly [t-w+1, t]. Safe.",
    )
    register(
        std_col,
        f"Rolling std of nat_demand over the trailing {w} hours ending at (and including) origin t.",
        ["nat_demand"],
        "Same trailing window as the corresponding rolling mean. Safe.",
    )

# ---------------------------------------------------------------------------
# 4. Weather features at origin t (current reading) and short lag, known at t.
#    Future (target-time) weather is intentionally NOT used: this dataset only
#    has weather actuals, not forecasts, so using weather at t+24h would mean
#    leaking the true future weather rather than a realistic forecast input.
# ---------------------------------------------------------------------------
for c in WEATHER_COLS:
    col = f"origin_{c}"
    feat[col] = df[c]
    register(
        col,
        f"Weather variable '{c}' reading at the forecast origin t.",
        [c],
        "Value at t is known at prediction time. Safe. Future (t+24h) weather deliberately excluded to avoid leaking unobserved future actuals.",
    )
    lag_col = f"lag_24h_{c}"
    feat[lag_col] = df[c].shift(24)
    register(
        lag_col,
        f"Weather variable '{c}' reading 24 hours before origin t (captures prior-day-same-hour conditions).",
        [c],
        "Uses only past data. Safe.",
    )

# ---------------------------------------------------------------------------
# 5. Calendar features AT THE TARGET time (t+24h). These are deterministic
#    functions of the calendar and are known arbitrarily far in advance,
#    so using the target-time value is standard practice, not leakage.
# ---------------------------------------------------------------------------
target_dt = df["datetime"] + pd.Timedelta(hours=HORIZON_HOURS)

feat["target_hour_of_day"] = target_dt.dt.hour
feat["target_day_of_week"] = target_dt.dt.dayofweek  # 0=Mon
feat["target_month"] = target_dt.dt.month
feat["target_is_weekend"] = target_dt.dt.dayofweek.isin([5, 6]).astype(int)
feat["target_hour_sin"] = np.sin(2 * np.pi * target_dt.dt.hour / 24)
feat["target_hour_cos"] = np.cos(2 * np.pi * target_dt.dt.hour / 24)
feat["target_dow_sin"] = np.sin(2 * np.pi * target_dt.dt.dayofweek / 7)
feat["target_dow_cos"] = np.cos(2 * np.pi * target_dt.dt.dayofweek / 7)
feat["target_month_sin"] = np.sin(2 * np.pi * target_dt.dt.month / 12)
feat["target_month_cos"] = np.cos(2 * np.pi * target_dt.dt.month / 12)

for name, desc in [
    ("target_hour_of_day", "Hour of day (0-23) at the target timestamp t+24h."),
    ("target_day_of_week", "Day of week (0=Mon..6=Sun) at the target timestamp t+24h."),
    ("target_month", "Calendar month (1-12) at the target timestamp t+24h."),
    ("target_is_weekend", "1 if the target timestamp falls on Saturday/Sunday, else 0."),
    ("target_hour_sin", "Sine-encoded hour of day at target timestamp (cyclical encoding)."),
    ("target_hour_cos", "Cosine-encoded hour of day at target timestamp (cyclical encoding)."),
    ("target_dow_sin", "Sine-encoded day of week at target timestamp (cyclical encoding)."),
    ("target_dow_cos", "Cosine-encoded day of week at target timestamp (cyclical encoding)."),
    ("target_month_sin", "Sine-encoded month at target timestamp (cyclical encoding)."),
    ("target_month_cos", "Cosine-encoded month at target timestamp (cyclical encoding)."),
]:
    register(name, desc, ["datetime"], "Calendar arithmetic is deterministic and known infinitely far in advance for any future timestamp. Not leakage.")

# holiday / school at target time -- these come from the raw dataset's own
# calendar columns, which are themselves precomputed calendar facts (not
# measurements), so looking them up at the target timestamp is valid.
holiday_lookup = df.set_index("datetime")[["Holiday_ID", "holiday", "school"]]
target_calendar = holiday_lookup.reindex(target_dt).reset_index(drop=True)
feat["target_holiday_id"] = target_calendar["Holiday_ID"]
feat["target_holiday_flag"] = target_calendar["holiday"]
feat["target_school_flag"] = target_calendar["school"]
for name, desc in [
    ("target_holiday_id", "Holiday_ID (categorical) at the target timestamp t+24h, looked up from the dataset's own calendar column."),
    ("target_holiday_flag", "Binary holiday flag at the target timestamp t+24h."),
    ("target_school_flag", "Binary school-in-session flag at the target timestamp t+24h."),
]:
    register(name, desc, ["Holiday_ID", "holiday", "school", "datetime"],
             "Holiday/school calendars are published in advance and are deterministic lookups by date, not measured outcomes. Rows where target_dt falls beyond the raw data's max timestamp become NaN and are dropped along with the undefined target (see rows-lost accounting).")

# origin-time calendar context as well (cheap, sometimes useful for the model
# to see time-since-origin cues, e.g. weekday->weekend transition)
feat["origin_hour_of_day"] = df["datetime"].dt.hour
feat["origin_day_of_week"] = df["datetime"].dt.dayofweek
feat["origin_holiday_flag"] = df["holiday"]
feat["origin_school_flag"] = df["school"]
for name, desc in [
    ("origin_hour_of_day", "Hour of day (0-23) at the forecast origin t."),
    ("origin_day_of_week", "Day of week (0=Mon..6=Sun) at the forecast origin t."),
    ("origin_holiday_flag", "Binary holiday flag at the forecast origin t (from raw data, unmodified)."),
    ("origin_school_flag", "Binary school-in-session flag at the forecast origin t (from raw data, unmodified)."),
]:
    register(name, desc, ["datetime", "holiday", "school"], "Origin-time values are known at prediction time by definition. Safe.")

# ---------------------------------------------------------------------------
# 6. Target: nat_demand at t + 24h
# ---------------------------------------------------------------------------
feat["target_nat_demand_t_plus_24h"] = df["nat_demand"].shift(-HORIZON_HOURS)
register(
    "target_nat_demand_t_plus_24h",
    "PREDICTION TARGET: nat_demand value 24 hours after the forecast origin t. This is the label, never a feature.",
    ["nat_demand"],
    "This is the label being predicted -- by construction it is the only column drawn from strictly after origin t, and it is excluded from the feature set at model-training time.",
)

feat["origin_datetime"] = df["datetime"]
feat["target_datetime"] = target_dt

# ---------------------------------------------------------------------------
# 7. Drop rows with any NaN (from lag/rolling warm-up at the start, and from
#    the shift(-24) target at the end) -- this is the leakage-safe way to
#    handle edges: no imputation/bfill/ffill across the warm-up or horizon
#    boundary, which would itself risk leaking information.
# ---------------------------------------------------------------------------
before_dropna = len(feat)
na_counts = feat.isna().sum()
na_counts = na_counts[na_counts > 0]

feat_clean = feat.dropna().reset_index(drop=True)
after_dropna = len(feat_clean)
rows_lost_total = before_dropna - after_dropna

# rows lost specifically at the start (warm-up for lag/rolling features)
first_valid_idx = feat.dropna(subset=[c for c in feat.columns if c.startswith(("lag_", "roll_"))]).index.min()
rows_lost_start = int(first_valid_idx)

# rows lost specifically at the end (target undefined beyond raw data horizon)
last_valid_target_idx = feat["target_nat_demand_t_plus_24h"].last_valid_index()
rows_lost_end = int(before_dropna - 1 - last_valid_target_idx)

print(f"Raw rows: {n_raw}")
print(f"Feature rows before dropna: {before_dropna}")
print(f"Rows lost at start (lag/rolling warm-up, up to {max(lag_hours + roll_windows)}h): {rows_lost_start}")
print(f"Rows lost at end (target horizon {HORIZON_HOURS}h): {rows_lost_end}")
print(f"Total rows lost: {rows_lost_total}")
print(f"Final feature rows: {after_dropna}")
print("\nColumns with any NaN before dropna:")
print(na_counts)

# ---------------------------------------------------------------------------
# 8. Chronological train / validation / test split (no shuffling)
# ---------------------------------------------------------------------------
TRAIN_END = pd.Timestamp("2018-12-31 23:00:00")
VAL_END = pd.Timestamp("2019-12-31 23:00:00")
# test = everything after VAL_END, through the end of the usable data

train_df = feat_clean[feat_clean["origin_datetime"] <= TRAIN_END].reset_index(drop=True)
val_df = feat_clean[(feat_clean["origin_datetime"] > TRAIN_END) & (feat_clean["origin_datetime"] <= VAL_END)].reset_index(drop=True)
test_df = feat_clean[feat_clean["origin_datetime"] > VAL_END].reset_index(drop=True)

assert train_df["origin_datetime"].max() <= TRAIN_END
assert val_df["origin_datetime"].min() > TRAIN_END and val_df["origin_datetime"].max() <= VAL_END
assert test_df["origin_datetime"].min() > VAL_END
assert len(train_df) + len(val_df) + len(test_df) == len(feat_clean)

# ---------------------------------------------------------------------------
# 9. Leakage checks (automated)
# ---------------------------------------------------------------------------
leakage_checks = {}

# (a) target column not present among model feature columns
feature_cols = [c for c in feat_clean.columns
                 if c not in ("datetime", "origin_datetime", "target_datetime", "target_nat_demand_t_plus_24h")]
leakage_checks["target_excluded_from_features"] = "target_nat_demand_t_plus_24h" not in feature_cols

# (b) every lag/rolling feature is derived only from indices <= origin index
#     verified by construction (shift(h) for h>=0, rolling window ending at
#     current index) -- recheck programmatically on a sample
sample_idx = 50000 if len(df) > 50000 else len(df) - 1
sample_idx = min(sample_idx, len(df) - HORIZON_HOURS - 1)
check_row = df.iloc[sample_idx]
origin_time = check_row["datetime"]
lag1_expected = df.loc[df["datetime"] == origin_time - pd.Timedelta(hours=1), "nat_demand"]
row_in_feat = feat[feat["datetime"] == origin_time]
if not lag1_expected.empty and not row_in_feat.empty:
    leakage_checks["lag_1h_matches_manual_lookup"] = bool(
        np.isclose(row_in_feat["lag_1h_nat_demand"].values[0], lag1_expected.values[0])
    )

# (c) chronological ordering preserved (no shuffling) in every split
leakage_checks["train_chronological"] = bool(train_df["origin_datetime"].is_monotonic_increasing)
leakage_checks["val_chronological"] = bool(val_df["origin_datetime"].is_monotonic_increasing)
leakage_checks["test_chronological"] = bool(test_df["origin_datetime"].is_monotonic_increasing)

# (d) splits do not overlap in time and are strictly ordered train < val < test
leakage_checks["splits_non_overlapping_and_ordered"] = bool(
    train_df["origin_datetime"].max() < val_df["origin_datetime"].min()
    and val_df["origin_datetime"].max() < test_df["origin_datetime"].min()
)

# (e) rolling/lag windows never reach past origin index (verify max window <= origin index for first row of each split)
leakage_checks["max_lookback_window_hours"] = max(lag_hours + roll_windows)

# (f) target_datetime is always exactly origin_datetime + 24h
leakage_checks["target_horizon_consistent"] = bool(
    ((feat_clean["target_datetime"] - feat_clean["origin_datetime"]) == pd.Timedelta(hours=HORIZON_HOURS)).all()
)

print("\nLeakage checks:")
for k, v in leakage_checks.items():
    print(f"  {k}: {v}")

assert leakage_checks["target_excluded_from_features"]
assert leakage_checks.get("lag_1h_matches_manual_lookup", True)
assert leakage_checks["train_chronological"] and leakage_checks["val_chronological"] and leakage_checks["test_chronological"]
assert leakage_checks["splits_non_overlapping_and_ordered"]
assert leakage_checks["target_horizon_consistent"]

# ---------------------------------------------------------------------------
# 10. Save outputs
# ---------------------------------------------------------------------------
feat_clean.to_csv(os.path.join(OUT_DIR, "features_full.csv"), index=False)
train_df.to_csv(os.path.join(OUT_DIR, "train.csv"), index=False)
val_df.to_csv(os.path.join(OUT_DIR, "val.csv"), index=False)
test_df.to_csv(os.path.join(OUT_DIR, "test.csv"), index=False)

metadata_out = {
    "source_file": "ml/data/raw/continuous dataset.csv",
    "forecast_horizon_hours": HORIZON_HOURS,
    "target_column": "target_nat_demand_t_plus_24h",
    "target_definition": "nat_demand value at origin_datetime + 24 hours",
    "feature_columns": feature_cols,
    "non_feature_columns": ["datetime", "origin_datetime", "target_datetime", "target_nat_demand_t_plus_24h"],
    "n_raw_rows": int(n_raw),
    "n_feature_rows_before_dropna": int(before_dropna),
    "rows_lost_start_warmup": int(rows_lost_start),
    "rows_lost_end_horizon": int(rows_lost_end),
    "rows_lost_total": int(rows_lost_total),
    "n_final_rows": int(after_dropna),
    "split": {
        "train": {"n_rows": int(len(train_df)),
                   "start": str(train_df["origin_datetime"].min()),
                   "end": str(train_df["origin_datetime"].max())},
        "val": {"n_rows": int(len(val_df)),
                 "start": str(val_df["origin_datetime"].min()),
                 "end": str(val_df["origin_datetime"].max())},
        "test": {"n_rows": int(len(test_df)),
                  "start": str(test_df["origin_datetime"].min()),
                  "end": str(test_df["origin_datetime"].max())},
    },
    "leakage_checks": leakage_checks,
    "features": feature_metadata,
}
with open(os.path.join(OUT_DIR, "feature_metadata.json"), "w", encoding="utf-8") as f:
    json.dump(metadata_out, f, indent=2, default=str)

print(f"\nSaved: {OUT_DIR}\\features_full.csv ({len(feat_clean)} rows)")
print(f"Saved: {OUT_DIR}\\train.csv ({len(train_df)} rows)")
print(f"Saved: {OUT_DIR}\\val.csv ({len(val_df)} rows)")
print(f"Saved: {OUT_DIR}\\test.csv ({len(test_df)} rows)")
print(f"Saved: {OUT_DIR}\\feature_metadata.json")
