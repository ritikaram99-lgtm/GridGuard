"""
GridGuard AI - Baseline evaluation + XGBoost training for 24-hour-ahead
national demand forecasting.

Uses ONLY the verified processed datasets:
  ml/data/processed/train.csv
  ml/data/processed/val.csv
  ml/data/processed/test.csv
  ml/data/processed/feature_metadata.json

No feature-engineering logic is modified here. Chronological workflow:
train -> validation (hyperparameter selection / early stopping) -> test
(final evaluation only, never used for tuning).
"""
import os
import json
import pickle
import datetime as dt

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import xgboost as xgb
import shap
from sklearn.metrics import mean_absolute_error, mean_squared_error

SEED = 42
np.random.seed(SEED)

PROC_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
FIG_DIR = os.path.join(os.path.dirname(__file__), "..", "reports", "figures")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "reports", "model_evaluation.md")
os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(FIG_DIR, exist_ok=True)

TARGET_COL = "target_nat_demand_t_plus_24h"
FORBIDDEN_COLS = {"datetime", "origin_datetime", "target_datetime", TARGET_COL}

def section(title):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)

# ---------------------------------------------------------------------------
# 0. Load processed data + metadata
# ---------------------------------------------------------------------------
section("0. Load processed data (train/val/test) + feature metadata")

with open(os.path.join(PROC_DIR, "feature_metadata.json"), encoding="utf-8") as f:
    feat_meta = json.load(f)

expected_feature_cols = feat_meta["feature_columns"]
assert feat_meta["target_column"] == TARGET_COL

train_df = pd.read_csv(os.path.join(PROC_DIR, "train.csv"))
val_df = pd.read_csv(os.path.join(PROC_DIR, "val.csv"))
test_df = pd.read_csv(os.path.join(PROC_DIR, "test.csv"))

for name, d in [("train", train_df), ("val", val_df), ("test", test_df)]:
    d["origin_datetime"] = pd.to_datetime(d["origin_datetime"])
    assert d["origin_datetime"].is_monotonic_increasing, f"{name} must be chronological (no shuffling)"

print(f"train: {len(train_df)} rows [{train_df['origin_datetime'].min()} -> {train_df['origin_datetime'].max()}]")
print(f"val:   {len(val_df)} rows [{val_df['origin_datetime'].min()} -> {val_df['origin_datetime'].max()}]")
print(f"test:  {len(test_df)} rows [{test_df['origin_datetime'].min()} -> {test_df['origin_datetime'].max()}]")

# ---------------------------------------------------------------------------
# 1. PRE-TRAINING VERIFICATION: exactly the 50 recorded feature columns,
#    none of them a raw timestamp/target column.
# ---------------------------------------------------------------------------
section("1. Pre-training verification of model input features")

print(f"Recorded feature_columns count in feature_metadata.json: {len(expected_feature_cols)}")

forbidden_in_expected = FORBIDDEN_COLS.intersection(expected_feature_cols)
assert not forbidden_in_expected, f"Forbidden columns found in recorded feature_columns: {forbidden_in_expected}"
print("Forbidden columns (datetime/origin_datetime/target/target_datetime) NOT present in recorded feature_columns: OK")

for name, d in [("train", train_df), ("val", val_df), ("test", test_df)]:
    missing = set(expected_feature_cols) - set(d.columns)
    assert not missing, f"{name}.csv is missing expected feature columns: {missing}"
    present_forbidden = FORBIDDEN_COLS.intersection(set(expected_feature_cols)).intersection(set(d.columns))
    assert not present_forbidden

X_train = train_df[expected_feature_cols].copy()
X_val = val_df[expected_feature_cols].copy()
X_test = test_df[expected_feature_cols].copy()
y_train = train_df[TARGET_COL].copy()
y_val = val_df[TARGET_COL].copy()
y_test = test_df[TARGET_COL].copy()

for name, X in [("X_train", X_train), ("X_val", X_val), ("X_test", X_test)]:
    assert list(X.columns) == expected_feature_cols, f"{name} column order does not match feature_metadata.json"
    assert X.shape[1] == 50, f"{name} has {X.shape[1]} columns, expected exactly 50"
    forbidden_present = FORBIDDEN_COLS.intersection(set(X.columns))
    assert not forbidden_present, f"{name} contains forbidden columns: {forbidden_present}"
    non_numeric = [c for c in X.columns if not pd.api.types.is_numeric_dtype(X[c])]
    assert not non_numeric, f"{name} contains non-numeric (e.g. raw timestamp) columns: {non_numeric}"
    assert X.isna().sum().sum() == 0, f"{name} contains unexpected NaNs"

print(f"X_train shape: {X_train.shape}")
print(f"X_val shape:   {X_val.shape}")
print(f"X_test shape:  {X_test.shape}")
print("VERIFIED: exactly 50 feature columns in train/val/test, matching feature_metadata.json order,")
print("          none of them datetime / origin_datetime / target_nat_demand_t_plus_24h / target_datetime,")
print("          and all numeric with no missing values.")

# ---------------------------------------------------------------------------
# 2. Persistence baseline: prediction(t+24) = nat_demand(t) = lag_0h_nat_demand
# ---------------------------------------------------------------------------
section("2. Persistence baseline (prediction(t+24) = nat_demand(t))")

def compute_metrics(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mape = float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100)
    return {"MAE": mae, "RMSE": rmse, "MAPE": mape}

baseline_val_pred = val_df["lag_0h_nat_demand"].values
baseline_test_pred = test_df["lag_0h_nat_demand"].values

baseline_val_metrics = compute_metrics(y_val.values, baseline_val_pred)
baseline_test_metrics = compute_metrics(y_test.values, baseline_test_pred)

print("Persistence baseline - Validation:", baseline_val_metrics)
print("Persistence baseline - Test:      ", baseline_test_metrics)

# ---------------------------------------------------------------------------
# 3. Train XGBoost (sensible fixed baseline config, early stopping on val)
# ---------------------------------------------------------------------------
section("3. Train XGBoost")

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
print("Hyperparameters:", json.dumps(hyperparameters, indent=2))

model = xgb.XGBRegressor(**hyperparameters)
model.fit(
    X_train, y_train,
    eval_set=[(X_train, y_train), (X_val, y_val)],
    verbose=False,
)

best_iteration = model.best_iteration
print(f"Best iteration (early stopping, selected via validation set): {best_iteration}")
hyperparameters["best_iteration"] = int(best_iteration) if best_iteration is not None else None

# ---------------------------------------------------------------------------
# 4. Evaluate XGBoost on val and test; compare to baseline
# ---------------------------------------------------------------------------
section("4. Evaluate XGBoost vs. persistence baseline")

xgb_val_pred = model.predict(X_val)
xgb_test_pred = model.predict(X_test)

xgb_val_metrics = compute_metrics(y_val.values, xgb_val_pred)
xgb_test_metrics = compute_metrics(y_test.values, xgb_test_pred)

print("XGBoost - Validation:", xgb_val_metrics)
print("XGBoost - Test:      ", xgb_test_metrics)

def relative_improvement(baseline_metrics, model_metrics):
    return {
        k: float((baseline_metrics[k] - model_metrics[k]) / baseline_metrics[k] * 100)
        for k in baseline_metrics
    }

val_improvement = relative_improvement(baseline_val_metrics, xgb_val_metrics)
test_improvement = relative_improvement(baseline_test_metrics, xgb_test_metrics)

print("Relative improvement over baseline - Validation (%):", val_improvement)
print("Relative improvement over baseline - Test (%):      ", test_improvement)

# ---------------------------------------------------------------------------
# 5. Error analysis
# ---------------------------------------------------------------------------
section("5. Error analysis")

test_analysis = test_df[["origin_datetime", "target_datetime", TARGET_COL,
                          "target_is_weekend", "target_holiday_flag", "target_hour_of_day"]].copy()
test_analysis["target_datetime"] = pd.to_datetime(test_analysis["target_datetime"])
test_analysis["y_true"] = y_test.values
test_analysis["y_pred"] = xgb_test_pred
test_analysis["error"] = test_analysis["y_pred"] - test_analysis["y_true"]
test_analysis["abs_error"] = test_analysis["error"].abs()
test_analysis["ape"] = (test_analysis["abs_error"] / test_analysis["y_true"]) * 100

# 5a. Actual vs predicted over a representative period (first 14 days of test)
rep_start = test_analysis["target_datetime"].min()
rep_end = rep_start + pd.Timedelta(days=14)
rep_slice = test_analysis[(test_analysis["target_datetime"] >= rep_start) & (test_analysis["target_datetime"] < rep_end)]

fig, ax = plt.subplots(figsize=(14, 4))
ax.plot(rep_slice["target_datetime"], rep_slice["y_true"], label="Actual", linewidth=1)
ax.plot(rep_slice["target_datetime"], rep_slice["y_pred"], label="Predicted", linewidth=1, alpha=0.8)
ax.set_title(f"Actual vs Predicted Demand — Representative Test Period ({rep_start.date()} to {rep_end.date()})")
ax.set_ylabel("nat_demand (MW)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "actual_vs_predicted_period.png"), dpi=120)
plt.close(fig)

# 5b. Actual vs predicted for a full single week
week_start = rep_start
week_end = week_start + pd.Timedelta(days=7)
week_slice = test_analysis[(test_analysis["target_datetime"] >= week_start) & (test_analysis["target_datetime"] < week_end)]

fig, ax = plt.subplots(figsize=(14, 4))
ax.plot(week_slice["target_datetime"], week_slice["y_true"], label="Actual", linewidth=1.2, marker="o", markersize=2)
ax.plot(week_slice["target_datetime"], week_slice["y_pred"], label="Predicted", linewidth=1.2, marker="o", markersize=2, alpha=0.8)
ax.set_title(f"Actual vs Predicted Demand — Full Week ({week_start.date()} to {week_end.date()})")
ax.set_ylabel("nat_demand (MW)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "actual_vs_predicted_week.png"), dpi=120)
plt.close(fig)

# 5c. Residual/error distribution
fig, ax = plt.subplots(figsize=(8, 4))
ax.hist(test_analysis["error"], bins=60)
ax.axvline(0, color="black", linewidth=1)
ax.set_title("Residual Distribution (Predicted - Actual), Test Set")
ax.set_xlabel("Error (MW)")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "residual_distribution.png"), dpi=120)
plt.close(fig)

# 5d. Predicted vs actual scatter
fig, ax = plt.subplots(figsize=(6, 6))
ax.scatter(test_analysis["y_true"], test_analysis["y_pred"], s=4, alpha=0.3)
lims = [min(test_analysis["y_true"].min(), test_analysis["y_pred"].min()),
        max(test_analysis["y_true"].max(), test_analysis["y_pred"].max())]
ax.plot(lims, lims, color="red", linewidth=1, linestyle="--", label="y=x")
ax.set_xlabel("Actual nat_demand (MW)")
ax.set_ylabel("Predicted nat_demand (MW)")
ax.set_title("Predicted vs Actual — Test Set")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "predicted_vs_actual_scatter.png"), dpi=120)
plt.close(fig)

# Error pattern analysis (test set)
demand_terciles = pd.qcut(test_analysis["y_true"], 3, labels=["low", "mid", "high"])
error_by_demand_level = test_analysis.groupby(demand_terciles, observed=True)["abs_error"].agg(["mean", "count"])
error_by_weekend = test_analysis.groupby("target_is_weekend")["abs_error"].agg(["mean", "count"])
error_by_holiday = test_analysis.groupby("target_holiday_flag")["abs_error"].agg(["mean", "count"])
error_by_hour = test_analysis.groupby("target_hour_of_day")["abs_error"].agg(["mean", "count"])

print("\nMean absolute error by demand tercile (test):")
print(error_by_demand_level)
print("\nMean absolute error by weekend flag (test):")
print(error_by_weekend)
print("\nMean absolute error by holiday flag (test):")
print(error_by_holiday)
print("\nMean absolute error by target hour of day (test):")
print(error_by_hour)

overall_test_mae = test_analysis["abs_error"].mean()

# ---------------------------------------------------------------------------
# 6. SHAP explainability
# ---------------------------------------------------------------------------
section("6. SHAP explainability (TreeExplainer)")

explainer = shap.TreeExplainer(model)
# use a sample of test set for SHAP (full test set is small enough, use all)
shap_values = explainer.shap_values(X_test)

mean_abs_shap = pd.Series(np.abs(shap_values).mean(axis=0), index=expected_feature_cols).sort_values(ascending=False)
top10_shap = mean_abs_shap.head(10)
print("Top 10 features by mean |SHAP value| (test set):")
print(top10_shap)

# global feature importance (mean abs SHAP), bar chart
fig, ax = plt.subplots(figsize=(8, 6))
top10_shap.sort_values().plot(kind="barh", ax=ax)
ax.set_title("Top 10 Features by Mean |SHAP Value| (Test Set)")
ax.set_xlabel("Mean |SHAP value| (MW)")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "shap_feature_importance_top10.png"), dpi=120)
plt.close(fig)

# SHAP summary plot (beeswarm)
plt.figure(figsize=(9, 8))
shap.summary_plot(shap_values, X_test, show=False)
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "shap_summary_plot.png"), dpi=120)
plt.close()

# ---------------------------------------------------------------------------
# 7. POST-TRAINING VERIFICATION: saved model feature names/order match
#    feature_metadata.json exactly.
# ---------------------------------------------------------------------------
section("7. Post-training verification of saved model feature names/order")

model_path = os.path.join(MODELS_DIR, "demand_xgboost.pkl")
with open(model_path, "wb") as f:
    pickle.dump(model, f)

with open(model_path, "rb") as f:
    reloaded_model = pickle.load(f)

booster_feature_names = reloaded_model.get_booster().feature_names
sklearn_feature_names_in = list(reloaded_model.feature_names_in_)

assert booster_feature_names == expected_feature_cols, (
    "Booster feature_names do not match feature_metadata.json feature_columns order!"
)
assert sklearn_feature_names_in == expected_feature_cols, (
    "model.feature_names_in_ does not match feature_metadata.json feature_columns order!"
)
print(f"Booster feature_names count: {len(booster_feature_names)} -- matches feature_metadata.json order: "
      f"{booster_feature_names == expected_feature_cols}")
print(f"model.feature_names_in_ count: {len(sklearn_feature_names_in)} -- matches feature_metadata.json order: "
      f"{sklearn_feature_names_in == expected_feature_cols}")
print("VERIFIED: reloaded saved model's feature names and order exactly match feature_metadata.json.")

# ---------------------------------------------------------------------------
# 8. Save model metadata
# ---------------------------------------------------------------------------
section("8. Save model metadata")

model_metadata = {
    "target_definition": {
        "column": TARGET_COL,
        "definition": "nat_demand value at origin_datetime + 24 hours",
    },
    "feature_list": expected_feature_cols,
    "n_features": len(expected_feature_cols),
    "date_ranges": {
        "train": {"start": str(train_df["origin_datetime"].min()), "end": str(train_df["origin_datetime"].max()), "n_rows": int(len(train_df))},
        "val": {"start": str(val_df["origin_datetime"].min()), "end": str(val_df["origin_datetime"].max()), "n_rows": int(len(val_df))},
        "test": {"start": str(test_df["origin_datetime"].min()), "end": str(test_df["origin_datetime"].max()), "n_rows": int(len(test_df))},
    },
    "hyperparameters": hyperparameters,
    "random_seed": SEED,
    "baseline_metrics": {
        "validation": baseline_val_metrics,
        "test": baseline_test_metrics,
    },
    "xgboost_metrics": {
        "validation": xgb_val_metrics,
        "test": xgb_test_metrics,
    },
    "relative_improvement_over_baseline_pct": {
        "validation": val_improvement,
        "test": test_improvement,
    },
    "top10_shap_features": top10_shap.to_dict(),
    "pre_training_verification": {
        "n_feature_columns": int(X_train.shape[1]),
        "forbidden_columns_absent": True,
        "all_numeric": True,
        "no_missing_values": True,
    },
    "post_training_verification": {
        "booster_feature_names_match_metadata": booster_feature_names == expected_feature_cols,
        "sklearn_feature_names_in_match_metadata": sklearn_feature_names_in == expected_feature_cols,
    },
    "training_timestamp_utc": dt.datetime.utcnow().isoformat() + "Z",
}

with open(os.path.join(MODELS_DIR, "model_metadata.json"), "w", encoding="utf-8") as f:
    json.dump(model_metadata, f, indent=2, default=str)

print(f"Saved model: {model_path}")
print(f"Saved metadata: {os.path.join(MODELS_DIR, 'model_metadata.json')}")
print(f"Saved figures under: {FIG_DIR}")

print("\nDONE.")
