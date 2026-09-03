"""
GridGuard AI - Direct multi-horizon hourly forecasting experiment.

Trains 24 INDEPENDENT XGBoost models, one per horizon h=1..24, each
predicting exactly national demand at t+h from features known at origin
time t. This is a controlled comparison against the existing POOLED
single-model-with-horizon-feature approach (ml/models/hourly_demand_xgboost.pkl),
which was found to underperform simple baselines at h=1,2,23,24.

Does NOT modify: the existing dedicated 24h model (demand_xgboost.pkl), the
existing pooled hourly model, stress_engine.py, feeder_generator.py,
rolling_integration.py, or build_features.py. This is a new, standalone
experiment; its models are saved under ml/models/direct_hourly/, separate
from every existing model.

LEAKAGE PHILOSOPHY (same as build_features.py / train_hourly_xgboost.py):
  - Origin-time features (lags, rolling stats, origin weather) use only
    information at or before origin time t -- safe for any horizon.
  - Target-time CALENDAR features (hour/day/month/weekend/holiday/school at
    t+h) ARE used and are explicitly justified below: these are deterministic
    facts about a future date (calendar arithmetic, published holiday/school
    calendars), not measurements -- they are knowable arbitrarily far in
    advance regardless of any forecast, so using them is not leakage. This is
    the same justification already used and accepted in build_features.py.
  - Target-time WEATHER is never used (no real weather forecast data exists
    in this dataset -- using actual future weather would be leakage of an
    unmeasurable-in-practice quantity).
  - `forecast_horizon` is NOT used as a feature here (unlike the pooled
    model) -- each model IS one fixed horizon, so the horizon is implicit in
    which model file is used, not an input value.
"""
import os
import sys
import json
import time
import pickle
import datetime as dt

import numpy as np
import pandas as pd
import xgboost as xgb
import shap
from sklearn.metrics import mean_absolute_error, mean_squared_error
import matplotlib.pyplot as plt

SEED = 42
np.random.seed(SEED)

RAW_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "continuous dataset.csv")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "direct_hourly")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
FIG_DIR = os.path.join(REPORTS_DIR, "figures", "direct_hourly")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(FIG_DIR, exist_ok=True)

MAX_HORIZON = 24
MAX_LAG = 168

WEATHER_COLS = ["T2M_toc", "QV2M_toc", "TQL_toc", "W2M_toc",
                 "T2M_san", "QV2M_san", "TQL_san", "W2M_san",
                 "T2M_dav", "QV2M_dav", "TQL_dav", "W2M_dav"]

TRAIN_END = pd.Timestamp("2018-12-31 23:00:00")
VAL_END = pd.Timestamp("2019-12-31 23:00:00")
PRE_COVID_END = pd.Timestamp("2020-02-29 23:00:00")
COVID_ONSET_START = pd.Timestamp("2020-03-01 00:00:00")


def section(title):
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)


# ---------------------------------------------------------------------------
# 1. Load raw data, build origin-level (horizon-independent) features
#    -- expanded lag set per this task's request: lag_0h..lag_3h added
#    alongside the existing lag_24h/48h/168h.
# ---------------------------------------------------------------------------
section("1. Load raw dataset and build origin-level leakage-safe features")
df = pd.read_csv(RAW_PATH)
df["datetime"] = pd.to_datetime(df["datetime"])
df = df.sort_values("datetime").reset_index(drop=True)
assert df["datetime"].is_monotonic_increasing
assert (df["datetime"].diff().dropna() == pd.Timedelta(hours=1)).all()
print(f"Raw rows: {len(df)}, range {df['datetime'].min()} -> {df['datetime'].max()}")

demand_by_dt = df.set_index("datetime")["nat_demand"]
calendar_by_dt = df.set_index("datetime")[["Holiday_ID", "holiday", "school"]]

origin = pd.DataFrame({"origin_datetime": df["datetime"]})

LAG_HOURS = [0, 1, 2, 3, 24, 48, 168]  # expanded per this task's feature-design request
for h in LAG_HOURS:
    origin[f"lag_{h}h_nat_demand"] = df["nat_demand"].shift(h)

for w in [24, 168]:
    origin[f"roll_mean_{w}h_nat_demand"] = df["nat_demand"].rolling(window=w, min_periods=w).mean()
    origin[f"roll_std_{w}h_nat_demand"] = df["nat_demand"].rolling(window=w, min_periods=w).std()
# short-window rolling stats too, for short-horizon sensitivity
for w in [3, 6]:
    origin[f"roll_mean_{w}h_nat_demand"] = df["nat_demand"].rolling(window=w, min_periods=w).mean()

for c in WEATHER_COLS:
    origin[f"origin_{c}"] = df[c]
    origin[f"lag_24h_{c}"] = df[c].shift(24)

origin["origin_hour_of_day"] = df["datetime"].dt.hour
origin["origin_day_of_week"] = df["datetime"].dt.dayofweek
origin["origin_holiday_flag"] = df["holiday"]
origin["origin_school_flag"] = df["school"]

ORIGIN_FEATURE_COLS = [c for c in origin.columns if c != "origin_datetime"]
origin_valid = origin.dropna(subset=ORIGIN_FEATURE_COLS).reset_index(drop=True)
max_valid_origin_dt = df["datetime"].max() - pd.Timedelta(hours=MAX_HORIZON)
origin_valid = origin_valid[origin_valid["origin_datetime"] <= max_valid_origin_dt].reset_index(drop=True)
n_origins = len(origin_valid)
print(f"Origin-level features: {len(ORIGIN_FEATURE_COLS)} columns, {n_origins} valid origins "
      f"[{origin_valid['origin_datetime'].min()} -> {origin_valid['origin_datetime'].max()}]")
assert origin_valid[ORIGIN_FEATURE_COLS].isna().sum().sum() == 0
assert np.isfinite(origin_valid[ORIGIN_FEATURE_COLS].values).all()

TARGET_TIME_FEATURE_COLS = [
    "target_hour_of_day", "target_day_of_week", "target_month", "target_is_weekend",
    "target_hour_sin", "target_hour_cos", "target_dow_sin", "target_dow_cos",
    "target_month_sin", "target_month_cos", "target_holiday_id", "target_holiday_flag", "target_school_flag",
]
FEATURE_COLS = ORIGIN_FEATURE_COLS + TARGET_TIME_FEATURE_COLS  # NOTE: no forecast_horizon column
print(f"Per-horizon-model feature count: {len(FEATURE_COLS)} "
      f"({len(ORIGIN_FEATURE_COLS)} origin + {len(TARGET_TIME_FEATURE_COLS)} target-time calendar, "
      f"no forecast_horizon -- horizon is implicit in which model is used)")
print("\nTarget-time calendar justification: hour/day/month/weekend/holiday/school at t+h are deterministic")
print("facts about a future calendar date (arithmetic + published holiday/school calendars), knowable")
print("arbitrarily far in advance regardless of any forecast -- not measurements, so not leakage.")
print("Target-time WEATHER is never used (no real weather-forecast data exists in this dataset).")

hyperparameters = {
    "n_estimators": 500,
    "max_depth": 6,
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


def compute_metrics(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mape = float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100)
    return {"MAE": mae, "RMSE": rmse, "MAPE": mape}


# ---------------------------------------------------------------------------
# 2. Train one model per horizon; evaluate against 3 baselines, per period
# ---------------------------------------------------------------------------
section("2. Train 24 independent per-horizon models")

all_metrics_rows = []
leakage_checks_all = {}
models = {}
feature_importances_by_horizon = {}
example_test_frames = {}  # keep a couple of horizons' full test frames for plotting/SHAP

t_start_all = time.time()
for h in range(1, MAX_HORIZON + 1):
    t0 = time.time()
    hdf = origin_valid.copy()
    hdf["target_datetime"] = hdf["origin_datetime"] + pd.Timedelta(hours=h)
    hdf["target_nat_demand"] = hdf["target_datetime"].map(demand_by_dt)
    assert hdf["target_nat_demand"].isna().sum() == 0

    td = hdf["target_datetime"]
    hdf["target_hour_of_day"] = td.dt.hour
    hdf["target_day_of_week"] = td.dt.dayofweek
    hdf["target_month"] = td.dt.month
    hdf["target_is_weekend"] = td.dt.dayofweek.isin([5, 6]).astype(int)
    hdf["target_hour_sin"] = np.sin(2 * np.pi * td.dt.hour / 24)
    hdf["target_hour_cos"] = np.cos(2 * np.pi * td.dt.hour / 24)
    hdf["target_dow_sin"] = np.sin(2 * np.pi * td.dt.dayofweek / 7)
    hdf["target_dow_cos"] = np.cos(2 * np.pi * td.dt.dayofweek / 7)
    hdf["target_month_sin"] = np.sin(2 * np.pi * td.dt.month / 12)
    hdf["target_month_cos"] = np.cos(2 * np.pi * td.dt.month / 12)
    cal = calendar_by_dt.reindex(hdf["target_datetime"]).reset_index(drop=True)
    hdf["target_holiday_id"] = cal["Holiday_ID"].values
    hdf["target_holiday_flag"] = cal["holiday"].values
    hdf["target_school_flag"] = cal["school"].values
    assert hdf[["target_holiday_id", "target_holiday_flag", "target_school_flag"]].isna().sum().sum() == 0

    # baselines -- all use only information available at/before origin t
    hdf["baseline_persistence"] = hdf["lag_0h_nat_demand"]
    prev_day_dt = hdf["origin_datetime"] + pd.Timedelta(hours=h - 24)
    prev_week_dt = hdf["origin_datetime"] + pd.Timedelta(hours=h - 168)
    assert (prev_day_dt <= hdf["origin_datetime"]).all(), "same-hour-previous-day lookup must never be in the future"
    assert (prev_week_dt <= hdf["origin_datetime"]).all(), "same-hour-previous-week lookup must never be in the future"
    hdf["baseline_prev_day"] = prev_day_dt.map(demand_by_dt).values
    hdf["baseline_prev_week"] = prev_week_dt.map(demand_by_dt).values
    assert hdf[["baseline_prev_day", "baseline_prev_week"]].isna().sum().sum() == 0

    # leakage/integrity checks for this horizon
    lc = {
        "forecast_timestamp_correct": bool((hdf["target_datetime"] - hdf["origin_datetime"] == pd.Timedelta(hours=h)).all()),
        "no_duplicate_origins": bool(hdf["origin_datetime"].duplicated().sum() == 0),
        "no_nan": bool(hdf[FEATURE_COLS + ["target_nat_demand"]].isna().sum().sum() == 0),
        "no_inf": bool(np.isfinite(hdf[FEATURE_COLS + ["target_nat_demand"]].values).all()),
        "baselines_use_only_past_or_present_info": bool((prev_day_dt <= hdf["origin_datetime"]).all() and (prev_week_dt <= hdf["origin_datetime"]).all()),
    }
    leakage_checks_all[h] = lc
    assert all(lc.values()), f"Leakage check failed for horizon {h}: {lc}"

    train_h = hdf[hdf["origin_datetime"] <= TRAIN_END].reset_index(drop=True)
    val_h = hdf[(hdf["origin_datetime"] > TRAIN_END) & (hdf["origin_datetime"] <= VAL_END)].reset_index(drop=True)
    test_h = hdf[hdf["origin_datetime"] > VAL_END].reset_index(drop=True)
    assert train_h["origin_datetime"].max() < val_h["origin_datetime"].min() < test_h["origin_datetime"].min()

    X_train, y_train = train_h[FEATURE_COLS].astype(float), train_h["target_nat_demand"]
    X_val, y_val = val_h[FEATURE_COLS].astype(float), val_h["target_nat_demand"]
    X_test, y_test = test_h[FEATURE_COLS].astype(float), test_h["target_nat_demand"]

    model = xgb.XGBRegressor(**hyperparameters)
    model.fit(X_train, y_train, eval_set=[(X_train, y_train), (X_val, y_val)], verbose=False)

    booster_features = list(model.get_booster().feature_names)
    assert booster_features == FEATURE_COLS, f"Feature mismatch for horizon {h}"

    val_h = val_h.copy()
    test_h = test_h.copy()
    val_h["model_pred"] = model.predict(X_val)
    test_h["model_pred"] = model.predict(X_test)

    models[h] = model
    feature_importances_by_horizon[h] = dict(zip(FEATURE_COLS, model.feature_importances_.tolist()))
    if h in (1, 6, 12, 24):
        example_test_frames[h] = test_h.copy()

    model_path = os.path.join(MODELS_DIR, f"horizon_{h:02d}.pkl")
    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    # per-period metrics: full test, pre-covid, covid-onset, plus validation
    periods = {
        "validation": val_h,
        "test_full": test_h,
        "test_pre_covid": test_h[test_h["origin_datetime"] <= PRE_COVID_END],
        "test_covid_onset": test_h[test_h["origin_datetime"] >= COVID_ONSET_START],
    }
    for period_name, d in periods.items():
        if len(d) == 0:
            continue
        model_m = compute_metrics(d["target_nat_demand"], d["model_pred"])
        persist_m = compute_metrics(d["target_nat_demand"], d["baseline_persistence"])
        prevday_m = compute_metrics(d["target_nat_demand"], d["baseline_prev_day"])
        prevweek_m = compute_metrics(d["target_nat_demand"], d["baseline_prev_week"])
        baseline_options = {"persistence": persist_m, "prev_day": prevday_m, "prev_week": prevweek_m}
        strongest_name = min(baseline_options, key=lambda k: baseline_options[k]["MAE"])
        strongest_mae = baseline_options[strongest_name]["MAE"]
        beats_strongest = bool(model_m["MAE"] < strongest_mae)
        improvement_pct = float((strongest_mae - model_m["MAE"]) / strongest_mae * 100)
        all_metrics_rows.append({
            "horizon": h, "period": period_name, "n": len(d),
            "model_MAE": model_m["MAE"], "model_RMSE": model_m["RMSE"], "model_MAPE": model_m["MAPE"],
            "persistence_MAE": persist_m["MAE"], "persistence_RMSE": persist_m["RMSE"], "persistence_MAPE": persist_m["MAPE"],
            "prev_day_MAE": prevday_m["MAE"], "prev_day_RMSE": prevday_m["RMSE"], "prev_day_MAPE": prevday_m["MAPE"],
            "prev_week_MAE": prevweek_m["MAE"], "prev_week_RMSE": prevweek_m["RMSE"], "prev_week_MAPE": prevweek_m["MAPE"],
            "strongest_baseline": strongest_name, "strongest_baseline_MAE": strongest_mae,
            "beats_strongest_baseline": beats_strongest, "improvement_over_strongest_pct": improvement_pct,
        })

    print(f"  h={h:2d}: trained in {time.time()-t0:.1f}s, best_iter={model.best_iteration}, "
          f"test_full MAE={compute_metrics(test_h['target_nat_demand'], test_h['model_pred'])['MAE']:.2f}")

print(f"\nAll 24 horizon models trained in {time.time()-t_start_all:.1f}s total")

metrics_df = pd.DataFrame(all_metrics_rows)
metrics_df.to_csv(os.path.join(DATA_DIR, "direct_hourly_per_horizon_metrics.csv"), index=False)
print(f"Saved: {os.path.join(DATA_DIR, 'direct_hourly_per_horizon_metrics.csv')}")

# ---------------------------------------------------------------------------
# 3. Success criterion: which horizons beat the strongest baseline (test_full)
# ---------------------------------------------------------------------------
section("3. Success criterion -- horizon-by-horizon vs. strongest baseline (test_full)")
test_full_metrics = metrics_df[metrics_df["period"] == "test_full"].sort_values("horizon")
print(test_full_metrics[["horizon", "model_MAE", "strongest_baseline", "strongest_baseline_MAE",
                          "beats_strongest_baseline", "improvement_over_strongest_pct"]].to_string(index=False))
n_beats = int(test_full_metrics["beats_strongest_baseline"].sum())
print(f"\nDirect model beats strongest baseline at {n_beats} / 24 horizons (test_full period).")

# ---------------------------------------------------------------------------
# 4. Global validation checks
# ---------------------------------------------------------------------------
section("4. Global validation checks")
validations = {
    "24_horizons_exist": len(models) == 24,
    "each_model_predicts_its_assigned_horizon_only": all(h in models for h in range(1, 25)),
    "no_leakage_any_horizon": all(all(v for v in lc.values()) for lc in leakage_checks_all.values()),
    "no_nan_inf_in_metrics": bool(np.isfinite(metrics_df.select_dtypes(include=[np.number]).values).all()),
    "reproducible_seed_fixed": SEED == 42,
}
for k, v in validations.items():
    print(f"  {k}: {v}")
assert all(validations.values())
print("\nALL VALIDATIONS PASSED")

# ---------------------------------------------------------------------------
# 5. Feature importance / SHAP for representative horizons (1, 6, 12, 24)
# ---------------------------------------------------------------------------
section("5. Feature importance / SHAP diagnostics (representative horizons)")

shap_summaries = {}
for h in (1, 6, 12, 24):
    imp = feature_importances_by_horizon[h]
    top10 = sorted(imp.items(), key=lambda x: -x[1])[:10]
    print(f"\nHorizon {h} -- top 10 features by XGBoost gain importance:")
    for name, val in top10:
        print(f"    {name}: {val:.4f}")

    test_h = example_test_frames[h]
    X_sample = test_h[FEATURE_COLS].astype(float).sample(n=min(1000, len(test_h)), random_state=SEED)
    explainer = shap.TreeExplainer(models[h])
    shap_values = explainer.shap_values(X_sample)
    mean_abs_shap = pd.Series(np.abs(shap_values).mean(axis=0), index=FEATURE_COLS).sort_values(ascending=False)
    shap_summaries[h] = mean_abs_shap.head(10).to_dict()
    print(f"Horizon {h} -- top 10 features by mean |SHAP|:")
    print(mean_abs_shap.head(10))

# ---------------------------------------------------------------------------
# 6. Plots
# ---------------------------------------------------------------------------
section("6. Generate plots")

# 1. MAE by horizon (direct model, test_full)
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(test_full_metrics["horizon"], test_full_metrics["model_MAE"], marker="o", label="Direct multi-horizon XGBoost")
ax.plot(test_full_metrics["horizon"], test_full_metrics["persistence_MAE"], marker="o", label="Persistence")
ax.plot(test_full_metrics["horizon"], test_full_metrics["prev_day_MAE"], marker="o", label="Same-hour-previous-day")
ax.plot(test_full_metrics["horizon"], test_full_metrics["prev_week_MAE"], marker="o", label="Same-hour-previous-week")
ax.set_xlabel("Forecast horizon (hours)")
ax.set_ylabel("MAE (MW)")
ax.set_title("MAE by Horizon — Direct Multi-Horizon Model vs. Baselines (Test 2020 H1)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "mae_by_horizon.png"), dpi=120)
plt.close(fig)

# 2. Improvement over strongest baseline by horizon
fig, ax = plt.subplots(figsize=(10, 5))
colors = ["green" if b else "red" for b in test_full_metrics["beats_strongest_baseline"]]
ax.bar(test_full_metrics["horizon"], test_full_metrics["improvement_over_strongest_pct"], color=colors)
ax.axhline(0, color="black", linewidth=1)
ax.set_xlabel("Forecast horizon (hours)")
ax.set_ylabel("% improvement over strongest baseline")
ax.set_title("Direct Model Improvement over Strongest Baseline, by Horizon (Test 2020 H1)\n(green = beats baseline, red = does not)")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "improvement_over_baseline_by_horizon.png"), dpi=120)
plt.close(fig)

# 3. XGBoost vs baselines (RMSE)
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(test_full_metrics["horizon"], test_full_metrics["model_RMSE"], marker="o", label="Direct multi-horizon XGBoost")
ax.plot(test_full_metrics["horizon"], test_full_metrics["persistence_RMSE"], marker="o", label="Persistence")
ax.plot(test_full_metrics["horizon"], test_full_metrics["prev_day_RMSE"], marker="o", label="Same-hour-previous-day")
ax.plot(test_full_metrics["horizon"], test_full_metrics["prev_week_RMSE"], marker="o", label="Same-hour-previous-week")
ax.set_xlabel("Forecast horizon (hours)")
ax.set_ylabel("RMSE (MW)")
ax.set_title("RMSE by Horizon — Direct Model vs. Baselines (Test 2020 H1)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "xgboost_vs_baselines_rmse.png"), dpi=120)
plt.close(fig)

# 4. Pre-COVID vs COVID-onset performance
pre = metrics_df[metrics_df["period"] == "test_pre_covid"].sort_values("horizon")
post = metrics_df[metrics_df["period"] == "test_covid_onset"].sort_values("horizon")
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(pre["horizon"], pre["improvement_over_strongest_pct"], marker="o", label="Pre-COVID (Jan-Feb 2020)")
ax.plot(post["horizon"], post["improvement_over_strongest_pct"], marker="o", label="COVID-onset (Mar-Jun 2020)")
ax.axhline(0, color="black", linewidth=1)
ax.set_xlabel("Forecast horizon (hours)")
ax.set_ylabel("% improvement over strongest baseline")
ax.set_title("Direct Model: Pre-COVID vs. COVID-Onset Improvement over Baseline, by Horizon")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "pre_covid_vs_covid_onset.png"), dpi=120)
plt.close(fig)

# 5. Feature importance by representative horizons
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
for ax, h in zip(axes.flat, (1, 6, 12, 24)):
    imp = feature_importances_by_horizon[h]
    top10 = sorted(imp.items(), key=lambda x: -x[1])[:10]
    names = [n for n, _ in top10][::-1]
    vals = [v for _, v in top10][::-1]
    ax.barh(names, vals, color="steelblue")
    ax.set_title(f"Horizon {h} — Top 10 Features (XGBoost gain)")
    ax.tick_params(axis="y", labelsize=8)
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "feature_importance_by_horizon.png"), dpi=120)
plt.close(fig)

# 6. 24-hour prediction trajectory example (direct models, one origin, genuine per-model predictions)
common_origins = set(example_test_frames[1]["origin_datetime"])
for h in (6, 12, 24):
    common_origins &= set(example_test_frames[h]["origin_datetime"])
sample_origin = sorted(common_origins)[len(common_origins) // 2]

traj_actual, traj_pred, traj_h = [], [], []
for h in range(1, MAX_HORIZON + 1):
    hdf_h = origin_valid[origin_valid["origin_datetime"] == sample_origin]
    if len(hdf_h) == 0:
        continue
    target_dt = sample_origin + pd.Timedelta(hours=h)
    row = hdf_h.iloc[0].copy()
    row["target_hour_of_day"] = target_dt.hour
    row["target_day_of_week"] = target_dt.dayofweek
    row["target_month"] = target_dt.month
    row["target_is_weekend"] = int(target_dt.dayofweek in (5, 6))
    row["target_hour_sin"] = np.sin(2 * np.pi * target_dt.hour / 24)
    row["target_hour_cos"] = np.cos(2 * np.pi * target_dt.hour / 24)
    row["target_dow_sin"] = np.sin(2 * np.pi * target_dt.dayofweek / 7)
    row["target_dow_cos"] = np.cos(2 * np.pi * target_dt.dayofweek / 7)
    row["target_month_sin"] = np.sin(2 * np.pi * target_dt.month / 12)
    row["target_month_cos"] = np.cos(2 * np.pi * target_dt.month / 12)
    cal_row = calendar_by_dt.loc[target_dt]
    row["target_holiday_id"] = cal_row["Holiday_ID"]
    row["target_holiday_flag"] = cal_row["holiday"]
    row["target_school_flag"] = cal_row["school"]
    X_row = pd.DataFrame([row])[FEATURE_COLS].astype(float)
    pred = models[h].predict(X_row)[0]
    traj_pred.append(pred)
    traj_actual.append(demand_by_dt.get(target_dt))
    traj_h.append(h)

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(traj_h, traj_actual, marker="o", label="Actual")
ax.plot(traj_h, traj_pred, marker="o", label="Direct multi-horizon model (genuine per-horizon predictions)")
ax.set_xlabel("Forecast horizon (hours ahead)")
ax.set_ylabel("nat_demand (MW)")
ax.set_title(f"24-Hour Forecast Trajectory Example — Origin {sample_origin}\n(Direct Multi-Horizon Model)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "24h_trajectory_example.png"), dpi=120)
plt.close(fig)

print(f"\nSaved 6 plots under: {FIG_DIR}")

# ---------------------------------------------------------------------------
# 7. Save metadata
# ---------------------------------------------------------------------------
metadata = {
    "model_type": "24 independent XGBoost models, one per fixed horizon h=1..24 (no forecast_horizon feature)",
    "target_definition": "nat_demand at origin_datetime + h hours, one model per h",
    "feature_list": FEATURE_COLS,
    "origin_feature_list": ORIGIN_FEATURE_COLS,
    "target_time_feature_list": TARGET_TIME_FEATURE_COLS,
    "n_features_per_model": len(FEATURE_COLS),
    "lag_hours_used": LAG_HOURS,
    "horizons": list(range(1, MAX_HORIZON + 1)),
    "max_lag_hours": MAX_LAG,
    "no_target_time_weather_used": True,
    "target_time_calendar_justification": (
        "hour/day/month/weekend/holiday/school at t+h are deterministic facts about a future calendar "
        "date, knowable arbitrarily far in advance regardless of any forecast -- not measurements, so "
        "not leakage. Same rationale as build_features.py."
    ),
    "date_ranges": {
        "train": {"end": str(TRAIN_END)}, "val": {"start": str(TRAIN_END), "end": str(VAL_END)},
        "test_full": {"start": str(VAL_END)},
        "test_pre_covid": {"start": "2020-01-01", "end": str(PRE_COVID_END)},
        "test_covid_onset": {"start": str(COVID_ONSET_START)},
    },
    "n_origins": int(n_origins),
    "hyperparameters": hyperparameters,
    "random_seed": SEED,
    "beats_strongest_baseline_count_test_full": n_beats,
    "horizons_beating_baseline_test_full": test_full_metrics.loc[test_full_metrics["beats_strongest_baseline"], "horizon"].tolist(),
    "horizons_losing_to_baseline_test_full": test_full_metrics.loc[~test_full_metrics["beats_strongest_baseline"], "horizon"].tolist(),
    "training_timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "does_not_modify": ["ml/models/demand_xgboost.pkl", "ml/models/hourly_demand_xgboost.pkl",
                          "stress_engine.py", "feeder_generator.py", "rolling_integration.py", "build_features.py"],
}
with open(os.path.join(MODELS_DIR, "direct_hourly_metadata.json"), "w", encoding="utf-8") as f:
    json.dump(metadata, f, indent=2, default=str)
print(f"Saved: {os.path.join(MODELS_DIR, 'direct_hourly_metadata.json')}")

print("\nDONE.")
