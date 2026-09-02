"""
GridGuard AI - Regime-shift diagnostic.

Splits the existing test set (2020-01-01 to 2020-06-26) into a pre-COVID
period (Jan-Feb 2020) and a COVID-onset period (Mar-Jun 2020), and compares
persistence-baseline vs. saved-XGBoost performance in each, plus the same
error-pattern breakdowns (hour of day, weekday/weekend, demand tercile)
already reported in model_evaluation.md.

Read-only diagnostic: does NOT retrain the model, does NOT touch feature
engineering or the dataset, does NOT modify demand_xgboost.pkl. Loads the
already-saved model and the already-saved test.csv only.
"""
import os
import json
import pickle

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

PROC_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")

TARGET_COL = "target_nat_demand_t_plus_24h"

with open(os.path.join(MODELS_DIR, "model_metadata.json"), encoding="utf-8") as f:
    model_meta = json.load(f)
feature_cols = model_meta["feature_list"]

with open(os.path.join(MODELS_DIR, "demand_xgboost.pkl"), "rb") as f:
    model = pickle.load(f)

assert list(model.get_booster().feature_names) == feature_cols, "Loaded model feature names do not match model_metadata.json"

test_df = pd.read_csv(os.path.join(PROC_DIR, "test.csv"))
test_df["origin_datetime"] = pd.to_datetime(test_df["origin_datetime"])
test_df["target_datetime"] = pd.to_datetime(test_df["target_datetime"])
assert test_df["origin_datetime"].is_monotonic_increasing

X_test = test_df[feature_cols].copy()
y_test = test_df[TARGET_COL].copy()

xgb_pred = model.predict(X_test)
persistence_pred = test_df["lag_0h_nat_demand"].values

test_df["y_true"] = y_test.values
test_df["xgb_pred"] = xgb_pred
test_df["persistence_pred"] = persistence_pred

# ---------------------------------------------------------------------------
# Define periods using the row's forecast ORIGIN date, so the two periods
# partition the existing test set without overlap and without re-deriving
# rows from any other split.
# ---------------------------------------------------------------------------
PRE_START = pd.Timestamp("2020-01-01 00:00:00")
PRE_END = pd.Timestamp("2020-02-29 23:00:00")
POST_START = pd.Timestamp("2020-03-01 00:00:00")
POST_END = test_df["origin_datetime"].max()

pre_mask = (test_df["origin_datetime"] >= PRE_START) & (test_df["origin_datetime"] <= PRE_END)
post_mask = (test_df["origin_datetime"] >= POST_START) & (test_df["origin_datetime"] <= POST_END)

pre_df = test_df[pre_mask].copy()
post_df = test_df[post_mask].copy()

assert len(pre_df) + len(post_df) == len(test_df), "Periods must partition the full test set exactly"
assert pre_df["origin_datetime"].max() < post_df["origin_datetime"].min()

def compute_metrics(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mape = float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100)
    return {"MAE": mae, "RMSE": rmse, "MAPE": mape}

def rel_improvement(baseline, model_m):
    return {k: float((baseline[k] - model_m[k]) / baseline[k] * 100) for k in baseline}

results = {}
for name, d in [("pre_covid", pre_df), ("covid_onset", post_df), ("full_test", test_df)]:
    baseline_m = compute_metrics(d["y_true"].values, d["persistence_pred"].values)
    xgb_m = compute_metrics(d["y_true"].values, d["xgb_pred"].values)
    improvement = rel_improvement(baseline_m, xgb_m)
    results[name] = {
        "n_rows": int(len(d)),
        "origin_start": str(d["origin_datetime"].min()),
        "origin_end": str(d["origin_datetime"].max()),
        "baseline_metrics": baseline_m,
        "xgboost_metrics": xgb_m,
        "improvement_pct": improvement,
    }

print(json.dumps(results, indent=2))

# ---------------------------------------------------------------------------
# Same error-pattern breakdowns as model_evaluation.md, per period
# (XGBoost absolute error only, to keep this focused and comparable).
# ---------------------------------------------------------------------------
for name, d in [("pre_covid", pre_df), ("covid_onset", post_df)]:
    d["abs_error"] = (d["xgb_pred"] - d["y_true"]).abs()

def by_hour(d):
    return d.groupby("target_hour_of_day")["abs_error"].agg(["mean", "count"])

def by_weekend(d):
    return d.groupby("target_is_weekend")["abs_error"].agg(["mean", "count"])

def by_demand_tercile(d, edges=None):
    if edges is None:
        terciles = pd.qcut(d["y_true"], 3, labels=["low", "mid", "high"])
    else:
        terciles = pd.cut(d["y_true"], bins=edges, labels=["low", "mid", "high"], include_lowest=True)
    return d.groupby(terciles, observed=True)["abs_error"].agg(["mean", "count"])

breakdowns = {}
for name, d in [("pre_covid", pre_df), ("covid_onset", post_df)]:
    breakdowns[name] = {
        "by_hour": by_hour(d).to_dict(orient="index"),
        "by_weekend": by_weekend(d).to_dict(orient="index"),
        "by_demand_tercile_period_specific": by_demand_tercile(d).to_dict(orient="index"),
    }

# also compute demand terciles using the FULL TEST SET's tercile edges (fixed
# thresholds), so pre/post comparisons of "high demand" use the same
# definition of high/low rather than period-relative terciles.
full_edges = pd.qcut(test_df["y_true"], 3, retbins=True)[1]
for name, d in [("pre_covid", pre_df), ("covid_onset", post_df)]:
    breakdowns[name]["by_demand_tercile_full_test_edges"] = by_demand_tercile(d, edges=full_edges).to_dict(orient="index")

print("\n--- BREAKDOWNS ---")
print(json.dumps(breakdowns, indent=2, default=str))

out = {"period_definitions": {
            "pre_covid": {"start": str(PRE_START), "end": str(PRE_END)},
            "covid_onset": {"start": str(POST_START), "end": str(POST_END)},
        },
       "metrics": results,
       "error_breakdowns": breakdowns,
       "full_test_demand_tercile_edges": list(full_edges)}

out_path = os.path.join(os.path.dirname(__file__), "..", "reports", "regime_shift_diagnostic_raw.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, default=str)
print(f"\nSaved raw diagnostic output: {out_path}")
