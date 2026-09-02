"""
GridGuard AI - Genuine hourly (t+1h .. t+24h) demand forecasting model.

Replaces the previously used INTERPOLATED trajectory (feeder_generator.
build_national_trajectory, which blends a single real t+24h forecast with a
historical diurnal shape) with GENUINE per-horizon XGBoost predictions.

Approach: a single XGBoost model with an explicit `forecast_horizon` feature
(1..24). Each training row is (origin time t, horizon h, target = nat_demand
at t+h). All non-horizon features are computed from information available AT
OR BEFORE origin time t (leakage-safe for every horizon, since none of them
depend on h) plus deterministic calendar facts about the target time t+h
(hour/day/month/holiday/school -- known arbitrarily far in advance, not
measurements, matching the rationale already used in build_features.py).

Does NOT use the existing 24h model, does NOT modify build_features.py,
stress_engine.py, feeder_generator.py, or rolling_integration.py. This is a
new, separate hourly forecasting implementation, built directly from the
raw dataset.

NO target-time (t+h) WEATHER is used anywhere -- only origin-time weather
(current + 24h-lagged), since real weather forecasts are not available in
this dataset. See build_features.py's identical rationale.
"""
import os
import json
import time
import datetime as dt

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error
import matplotlib.pyplot as plt

SEED = 42
np.random.seed(SEED)

RAW_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "continuous dataset.csv")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
FIG_DIR = os.path.join(REPORTS_DIR, "figures", "hourly_forecast")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(FIG_DIR, exist_ok=True)

MAX_HORIZON = 24
MAX_LAG = 168  # 7 days -- same warm-up window as build_features.py

WEATHER_COLS = ["T2M_toc", "QV2M_toc", "TQL_toc", "W2M_toc",
                 "T2M_san", "QV2M_san", "TQL_san", "W2M_san",
                 "T2M_dav", "QV2M_dav", "TQL_dav", "W2M_dav"]


def section(title):
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)


# ---------------------------------------------------------------------------
# 1. Load raw data (read-only)
# ---------------------------------------------------------------------------
section("1. Load raw dataset")
df = pd.read_csv(RAW_PATH)
df["datetime"] = pd.to_datetime(df["datetime"])
df = df.sort_values("datetime").reset_index(drop=True)
assert df["datetime"].is_monotonic_increasing
assert (df["datetime"].diff().dropna() == pd.Timedelta(hours=1)).all(), "Raw data must be gap-free hourly"
n_raw = len(df)
print(f"Raw rows: {n_raw}, range {df['datetime'].min()} -> {df['datetime'].max()}")

demand_by_dt = df.set_index("datetime")["nat_demand"]
calendar_by_dt = df.set_index("datetime")[["Holiday_ID", "holiday", "school"]]

# ---------------------------------------------------------------------------
# 2. Origin-level features (horizon-independent, leakage-safe: everything
#    here uses only information at or before the origin timestamp t).
#    Same feature *definitions* as build_features.py's origin-time subset,
#    reimplemented independently here since this is a separate pipeline.
# ---------------------------------------------------------------------------
section("2. Build origin-level features (leakage-safe, horizon-independent)")

origin = pd.DataFrame({"origin_datetime": df["datetime"]})

lag_hours = [1, 24, 48, 168]
for h in lag_hours:
    origin[f"lag_{h}h_nat_demand"] = df["nat_demand"].shift(h)
origin["lag_0h_nat_demand"] = df["nat_demand"]

for w in [24, 168]:
    origin[f"roll_mean_{w}h_nat_demand"] = df["nat_demand"].rolling(window=w, min_periods=w).mean()
    origin[f"roll_std_{w}h_nat_demand"] = df["nat_demand"].rolling(window=w, min_periods=w).std()

for c in WEATHER_COLS:
    origin[f"origin_{c}"] = df[c]
    origin[f"lag_24h_{c}"] = df[c].shift(24)

origin["origin_hour_of_day"] = df["datetime"].dt.hour
origin["origin_day_of_week"] = df["datetime"].dt.dayofweek
origin["origin_holiday_flag"] = df["holiday"]
origin["origin_school_flag"] = df["school"]

ORIGIN_FEATURE_COLS = [c for c in origin.columns if c != "origin_datetime"]
print(f"Origin-level feature columns: {len(ORIGIN_FEATURE_COLS)}")

# Drop warm-up rows (insufficient lag/rolling history) -- same 168h cutoff as build_features.py
origin_valid = origin.dropna(subset=ORIGIN_FEATURE_COLS).reset_index(drop=True)
# Also require the origin to have at least MAX_HORIZON hours of future data available
# (so every horizon 1..24 is valid for every retained origin -- a clean rectangular design)
max_valid_origin_dt = df["datetime"].max() - pd.Timedelta(hours=MAX_HORIZON)
origin_valid = origin_valid[origin_valid["origin_datetime"] <= max_valid_origin_dt].reset_index(drop=True)

n_origins = len(origin_valid)
print(f"Valid origins after {MAX_LAG}h warm-up + {MAX_HORIZON}h tail truncation: {n_origins}")
print(f"Origin range: {origin_valid['origin_datetime'].min()} -> {origin_valid['origin_datetime'].max()}")

assert origin_valid[ORIGIN_FEATURE_COLS].isna().sum().sum() == 0
assert np.isfinite(origin_valid[ORIGIN_FEATURE_COLS].values).all()

# ---------------------------------------------------------------------------
# 3. Expand to long format: one row per (origin, horizon) pair, horizon = 1..24
# ---------------------------------------------------------------------------
section("3. Expand to (origin, horizon) long format")
t0 = time.time()

horizons = np.arange(1, MAX_HORIZON + 1)
long_df = origin_valid.loc[origin_valid.index.repeat(MAX_HORIZON)].reset_index(drop=True)
long_df["forecast_horizon"] = np.tile(horizons, n_origins)
long_df["target_datetime"] = long_df["origin_datetime"] + pd.to_timedelta(long_df["forecast_horizon"], unit="h")

print(f"Long-format rows: {len(long_df)} ({n_origins} origins x {MAX_HORIZON} horizons), "
      f"built in {time.time()-t0:.1f}s")

# ---------------------------------------------------------------------------
# 4. Target + target-time (deterministic calendar, NOT weather) features
# ---------------------------------------------------------------------------
section("4. Attach targets and target-time calendar features")

long_df["target_nat_demand"] = long_df["target_datetime"].map(demand_by_dt)
assert long_df["target_nat_demand"].isna().sum() == 0, "Target lookup produced NaNs -- target_datetime out of raw data range"

target_dt = long_df["target_datetime"]
long_df["target_hour_of_day"] = target_dt.dt.hour
long_df["target_day_of_week"] = target_dt.dt.dayofweek
long_df["target_month"] = target_dt.dt.month
long_df["target_is_weekend"] = target_dt.dt.dayofweek.isin([5, 6]).astype(int)
long_df["target_hour_sin"] = np.sin(2 * np.pi * target_dt.dt.hour / 24)
long_df["target_hour_cos"] = np.cos(2 * np.pi * target_dt.dt.hour / 24)
long_df["target_dow_sin"] = np.sin(2 * np.pi * target_dt.dt.dayofweek / 7)
long_df["target_dow_cos"] = np.cos(2 * np.pi * target_dt.dt.dayofweek / 7)
long_df["target_month_sin"] = np.sin(2 * np.pi * target_dt.dt.month / 12)
long_df["target_month_cos"] = np.cos(2 * np.pi * target_dt.dt.month / 12)

cal_lookup = calendar_by_dt.reindex(long_df["target_datetime"]).reset_index(drop=True)
long_df["target_holiday_id"] = cal_lookup["Holiday_ID"].values
long_df["target_holiday_flag"] = cal_lookup["holiday"].values
long_df["target_school_flag"] = cal_lookup["school"].values
assert long_df[["target_holiday_id", "target_holiday_flag", "target_school_flag"]].isna().sum().sum() == 0

TARGET_TIME_FEATURE_COLS = [
    "target_hour_of_day", "target_day_of_week", "target_month", "target_is_weekend",
    "target_hour_sin", "target_hour_cos", "target_dow_sin", "target_dow_cos",
    "target_month_sin", "target_month_cos", "target_holiday_id", "target_holiday_flag", "target_school_flag",
]

FEATURE_COLS = ORIGIN_FEATURE_COLS + ["forecast_horizon"] + TARGET_TIME_FEATURE_COLS
TARGET_COL = "target_nat_demand"
print(f"Total feature columns: {len(FEATURE_COLS)} "
      f"({len(ORIGIN_FEATURE_COLS)} origin + 1 horizon + {len(TARGET_TIME_FEATURE_COLS)} target-time calendar)")
print("NOTE: no target-time WEATHER features are used anywhere (real weather forecasts unavailable).")

# ---------------------------------------------------------------------------
# 5. Leakage / integrity checks on the assembled long dataframe
# ---------------------------------------------------------------------------
section("5. Leakage and integrity checks")

checks = {}
checks["all_horizons_1_to_24_present"] = set(long_df["forecast_horizon"].unique()) == set(range(1, 25))
checks["forecast_timestamp_equals_origin_plus_horizon"] = bool(
    (long_df["target_datetime"] - long_df["origin_datetime"] == pd.to_timedelta(long_df["forecast_horizon"], unit="h")).all()
)
checks["no_duplicate_origin_horizon_pairs"] = bool(long_df.duplicated(subset=["origin_datetime", "forecast_horizon"]).sum() == 0)
checks["no_nan_in_features_or_target"] = bool(long_df[FEATURE_COLS + [TARGET_COL]].isna().sum().sum() == 0)
checks["no_inf_in_features_or_target"] = bool(np.isfinite(long_df[FEATURE_COLS + [TARGET_COL]].values).all())
checks["no_weather_target_time_features"] = not any(
    c.startswith("target_") and any(w in c for w in ["T2M", "QV2M", "TQL", "W2M"]) for c in FEATURE_COLS
)
# max lookback bound: origin features only reach back MAX_LAG hours -- verified by construction
# (identical shift/rolling logic to build_features.py, which was itself leakage-checked there)
checks["max_origin_lookback_hours"] = MAX_LAG
# every row's origin-time features are drawn strictly from indices <= origin (spot check)
sample = long_df.sample(n=min(500, len(long_df)), random_state=SEED)
lag1_ok = True
for _, row in sample.head(50).iterrows():
    expected = demand_by_dt.get(row["origin_datetime"] - pd.Timedelta(hours=1))
    if expected is not None and not np.isclose(row["lag_1h_nat_demand"], expected):
        lag1_ok = False
        break
checks["origin_lag_1h_matches_manual_lookup_sample"] = bool(lag1_ok)

for k, v in checks.items():
    print(f"  {k}: {v}")
assert all(v for v in checks.values() if isinstance(v, bool)), f"Leakage/integrity check failed: {checks}"
print("\nALL LEAKAGE/INTEGRITY CHECKS PASSED")

# ---------------------------------------------------------------------------
# 6. Chronological train/val/test split (same boundaries as build_features.py,
#    applied uniformly across all 24 horizons -- origins are shared, so a
#    given origin's rows for h=1..24 all fall in the same split, never split
#    across train/val/test).
# ---------------------------------------------------------------------------
section("6. Chronological train/validation/test split")

TRAIN_END = pd.Timestamp("2018-12-31 23:00:00")
VAL_END = pd.Timestamp("2019-12-31 23:00:00")

train_df = long_df[long_df["origin_datetime"] <= TRAIN_END].reset_index(drop=True)
val_df = long_df[(long_df["origin_datetime"] > TRAIN_END) & (long_df["origin_datetime"] <= VAL_END)].reset_index(drop=True)
test_df = long_df[long_df["origin_datetime"] > VAL_END].reset_index(drop=True)

for name, d in [("train", train_df), ("val", val_df), ("test", test_df)]:
    assert d["origin_datetime"].is_monotonic_increasing
print(f"train: {len(train_df)} rows [{train_df['origin_datetime'].min()} -> {train_df['origin_datetime'].max()}]")
print(f"val:   {len(val_df)} rows [{val_df['origin_datetime'].min()} -> {val_df['origin_datetime'].max()}]")
print(f"test:  {len(test_df)} rows [{test_df['origin_datetime'].min()} -> {test_df['origin_datetime'].max()}]")
assert train_df["origin_datetime"].max() < val_df["origin_datetime"].min()
assert val_df["origin_datetime"].max() < test_df["origin_datetime"].min()
assert len(train_df) + len(val_df) + len(test_df) == len(long_df)

X_train, y_train = train_df[FEATURE_COLS].astype(float), train_df[TARGET_COL]
X_val, y_val = val_df[FEATURE_COLS].astype(float), val_df[TARGET_COL]
X_test, y_test = test_df[FEATURE_COLS].astype(float), test_df[TARGET_COL]

# ---------------------------------------------------------------------------
# 7. Train XGBoost (single model, forecast_horizon as a feature)
# ---------------------------------------------------------------------------
section("7. Train XGBoost (single model, forecast_horizon as an explicit feature)")

hyperparameters = {
    "n_estimators": 500,
    "max_depth": 7,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "reg_lambda": 1.0,
    "reg_alpha": 0.0,
    "objective": "reg:squarederror",
    "eval_metric": "mae",
    "random_state": SEED,
    "n_jobs": -1,
    "early_stopping_rounds": 30,
}
print("Hyperparameters:", json.dumps(hyperparameters, indent=2))

t0 = time.time()
model = xgb.XGBRegressor(**hyperparameters)
model.fit(X_train, y_train, eval_set=[(X_train, y_train), (X_val, y_val)], verbose=False)
train_time_s = time.time() - t0
best_iteration = model.best_iteration
print(f"Training completed in {train_time_s:.1f}s. Best iteration: {best_iteration} of {hyperparameters['n_estimators']}")
hyperparameters["best_iteration"] = int(best_iteration) if best_iteration is not None else None

# ---------------------------------------------------------------------------
# 8. Persistence baseline (generalized to any horizon: prediction(t+h) = nat_demand(t))
# ---------------------------------------------------------------------------
section("8. Persistence baseline (prediction(t+h) = nat_demand(t), for every h)")

def compute_metrics(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mape = float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100)
    return {"MAE": mae, "RMSE": rmse, "MAPE": mape}

val_baseline_pred = val_df["lag_0h_nat_demand"].values
test_baseline_pred = test_df["lag_0h_nat_demand"].values

val_pred = model.predict(X_val)
test_pred = model.predict(X_test)

# ---------------------------------------------------------------------------
# 9. Per-horizon evaluation: model vs baseline, MAE/RMSE/MAPE, for h=1..24
# ---------------------------------------------------------------------------
section("9. Per-horizon evaluation (validation and test)")

val_df = val_df.copy()
val_df["model_pred"] = val_pred
val_df["baseline_pred"] = val_baseline_pred
test_df = test_df.copy()
test_df["model_pred"] = test_pred
test_df["baseline_pred"] = test_baseline_pred

per_horizon_rows = []
for h in range(1, MAX_HORIZON + 1):
    for split_name, d in [("validation", val_df), ("test", test_df)]:
        sub = d[d["forecast_horizon"] == h]
        model_m = compute_metrics(sub[TARGET_COL].values, sub["model_pred"].values)
        baseline_m = compute_metrics(sub[TARGET_COL].values, sub["baseline_pred"].values)
        improvement = {k: float((baseline_m[k] - model_m[k]) / baseline_m[k] * 100) for k in baseline_m}
        per_horizon_rows.append({
            "horizon": h, "split": split_name, "n": len(sub),
            "model_MAE": model_m["MAE"], "model_RMSE": model_m["RMSE"], "model_MAPE": model_m["MAPE"],
            "baseline_MAE": baseline_m["MAE"], "baseline_RMSE": baseline_m["RMSE"], "baseline_MAPE": baseline_m["MAPE"],
            "improvement_MAE_pct": improvement["MAE"], "improvement_RMSE_pct": improvement["RMSE"],
            "improvement_MAPE_pct": improvement["MAPE"],
        })

per_horizon_df = pd.DataFrame(per_horizon_rows)
print("\nPer-horizon metrics (test split):")
print(per_horizon_df[per_horizon_df["split"] == "test"].drop(columns=["split"]).to_string(index=False))

per_horizon_df.to_csv(os.path.join(DATA_DIR, "hourly_forecast_per_horizon_metrics.csv"), index=False)

# ---------------------------------------------------------------------------
# 10. "Genuine predictions, not interpolation" check
# ---------------------------------------------------------------------------
section("10. Verify predictions are genuine per-horizon model outputs, not interpolation")

sample_origin = test_df["origin_datetime"].iloc[len(test_df) // 2]
sample_rows = test_df[test_df["origin_datetime"] == sample_origin].sort_values("forecast_horizon")
genuine_preds = sample_rows["model_pred"].values
h0_value = sample_rows["lag_0h_nat_demand"].iloc[0]
h24_value = sample_rows[sample_rows["forecast_horizon"] == 24]["model_pred"].values[0]
naive_linear_interp = h0_value + (h24_value - h0_value) * (np.arange(1, 25) / 24)

max_abs_diff_from_linear = float(np.max(np.abs(genuine_preds - naive_linear_interp)))
print(f"Sample origin: {sample_origin}")
print(f"Genuine model predictions (h=1..24): {np.round(genuine_preds, 1).tolist()}")
print(f"Naive linear interpolation (h=0 -> h=24 for comparison): {np.round(naive_linear_interp, 1).tolist()}")
print(f"Max absolute difference from naive linear interpolation: {max_abs_diff_from_linear:.2f} MW")
print("(A non-trivial difference confirms the model is producing independent per-horizon predictions "
      "shaped by real hourly demand patterns, not a straight-line interpolation between two endpoints.)")
assert max_abs_diff_from_linear > 1.0, "Model predictions are suspiciously close to naive linear interpolation"

# each horizon's prediction is produced by an independent call with a different
# forecast_horizon feature value -- demonstrated directly:
distinct_horizon_feature_values = sample_rows["forecast_horizon"].nunique()
assert distinct_horizon_feature_values == 24
print(f"Confirmed: {distinct_horizon_feature_values} distinct forecast_horizon feature values used for this origin's 24 predictions.")

# ---------------------------------------------------------------------------
# 11. Post-training verification: saved model feature names/order
# ---------------------------------------------------------------------------
section("11. Save model + verify feature names/order")

model_path = os.path.join(MODELS_DIR, "hourly_demand_xgboost.pkl")
import pickle
with open(model_path, "wb") as f:
    pickle.dump(model, f)

with open(model_path, "rb") as f:
    reloaded = pickle.load(f)
booster_features = list(reloaded.get_booster().feature_names)
sklearn_features = list(reloaded.feature_names_in_)
assert booster_features == FEATURE_COLS
assert sklearn_features == FEATURE_COLS
print(f"Reloaded model's feature_names match the recorded {len(FEATURE_COLS)}-feature list exactly: True")

# ---------------------------------------------------------------------------
# 12. Save metadata
# ---------------------------------------------------------------------------
model_metadata = {
    "model_type": "single XGBoost model, forecast_horizon as explicit feature (1-24)",
    "target_definition": "nat_demand at origin_datetime + forecast_horizon hours",
    "target_column": TARGET_COL,
    "feature_list": FEATURE_COLS,
    "origin_feature_list": ORIGIN_FEATURE_COLS,
    "target_time_feature_list": TARGET_TIME_FEATURE_COLS,
    "n_features": len(FEATURE_COLS),
    "horizons": list(range(1, MAX_HORIZON + 1)),
    "max_lag_hours": MAX_LAG,
    "no_target_time_weather_used": True,
    "date_ranges": {
        "train": {"start": str(train_df["origin_datetime"].min()), "end": str(train_df["origin_datetime"].max()), "n_rows": int(len(train_df))},
        "val": {"start": str(val_df["origin_datetime"].min()), "end": str(val_df["origin_datetime"].max()), "n_rows": int(len(val_df))},
        "test": {"start": str(test_df["origin_datetime"].min()), "end": str(test_df["origin_datetime"].max()), "n_rows": int(len(test_df))},
    },
    "n_origins": int(n_origins),
    "hyperparameters": hyperparameters,
    "random_seed": SEED,
    "leakage_checks": checks,
    "training_time_seconds": train_time_s,
    "training_timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "supersedes_note": ("This model produces GENUINE per-horizon predictions for t+1h..t+24h. It replaces "
                          "the previous approach of interpolating between the existing 24h model's single "
                          "forecast point and a historical diurnal shape (feeder_generator.build_national_trajectory). "
                          "The existing 24h model (ml/models/demand_xgboost.pkl) is preserved unmodified as a "
                          "separate baseline/model."),
}
with open(os.path.join(MODELS_DIR, "hourly_model_metadata.json"), "w", encoding="utf-8") as f:
    json.dump(model_metadata, f, indent=2, default=str)
print(f"Saved: {model_path}")
print(f"Saved: {os.path.join(MODELS_DIR, 'hourly_model_metadata.json')}")

# ---------------------------------------------------------------------------
# 13. Plots
# ---------------------------------------------------------------------------
section("13. Generate plots")

test_metrics = per_horizon_df[per_horizon_df["split"] == "test"].sort_values("horizon")

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(test_metrics["horizon"], test_metrics["model_MAE"], marker="o", label="XGBoost hourly model")
ax.plot(test_metrics["horizon"], test_metrics["baseline_MAE"], marker="o", label="Persistence baseline")
ax.set_xlabel("Forecast horizon (hours)")
ax.set_ylabel("MAE (MW)")
ax.set_title("MAE by Forecast Horizon (Test Set, 2020 H1)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "mae_by_horizon.png"), dpi=120)
plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(test_metrics["horizon"], test_metrics["model_RMSE"], marker="o", label="XGBoost hourly model")
ax.plot(test_metrics["horizon"], test_metrics["baseline_RMSE"], marker="o", label="Persistence baseline")
ax.set_xlabel("Forecast horizon (hours)")
ax.set_ylabel("RMSE (MW)")
ax.set_title("RMSE by Forecast Horizon (Test Set, 2020 H1)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "rmse_by_horizon.png"), dpi=120)
plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(test_metrics["horizon"], test_metrics["model_MAPE"], marker="o", label="XGBoost hourly model")
ax.plot(test_metrics["horizon"], test_metrics["baseline_MAPE"], marker="o", label="Persistence baseline")
ax.set_xlabel("Forecast horizon (hours)")
ax.set_ylabel("MAPE (%)")
ax.set_title("MAPE by Forecast Horizon (Test Set, 2020 H1)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "mape_by_horizon.png"), dpi=120)
plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(test_metrics["horizon"], test_metrics["improvement_MAE_pct"], marker="o", color="green")
ax.axhline(0, color="black", linewidth=1)
ax.set_xlabel("Forecast horizon (hours)")
ax.set_ylabel("MAE improvement over baseline (%)")
ax.set_title("Model vs. Baseline: % MAE Improvement by Horizon (Test Set)")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "model_vs_baseline_by_horizon.png"), dpi=120)
plt.close(fig)

# Actual vs predicted example: one origin, full 24h genuine forecast
fig, ax = plt.subplots(figsize=(10, 5))
actuals = sample_rows[TARGET_COL].values
ax.plot(sample_rows["forecast_horizon"], actuals, marker="o", label="Actual")
ax.plot(sample_rows["forecast_horizon"], genuine_preds, marker="o", label="Genuine hourly XGBoost forecast")
ax.plot(sample_rows["forecast_horizon"], naive_linear_interp, marker="x", linestyle="--",
        label="Naive linear interpolation (for comparison only)")
ax.set_xlabel("Forecast horizon (hours ahead)")
ax.set_ylabel("nat_demand (MW)")
ax.set_title(f"24-Hour Forecast Example — Origin {sample_origin}\n(genuine per-horizon predictions vs. actual)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "24h_forecast_example.png"), dpi=120)
plt.close(fig)

# Additional actual-vs-predicted example: a different, randomly chosen origin
rng = np.random.default_rng(SEED)
another_origin = rng.choice(test_df["origin_datetime"].unique())
another_rows = test_df[test_df["origin_datetime"] == another_origin].sort_values("forecast_horizon")
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(another_rows["forecast_horizon"], another_rows[TARGET_COL].values, marker="o", label="Actual")
ax.plot(another_rows["forecast_horizon"], another_rows["model_pred"].values, marker="o", label="Genuine hourly XGBoost forecast")
ax.set_xlabel("Forecast horizon (hours ahead)")
ax.set_ylabel("nat_demand (MW)")
ax.set_title(f"Actual vs. Predicted — Second Example Origin {another_origin}")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "actual_vs_predicted_example2.png"), dpi=120)
plt.close(fig)

print(f"Saved plots under: {FIG_DIR}")

section("DONE")
print(f"Best/worst horizon by test MAE: "
      f"best={test_metrics.loc[test_metrics['model_MAE'].idxmin(), 'horizon']}, "
      f"worst={test_metrics.loc[test_metrics['model_MAE'].idxmax(), 'horizon']}")
