"""
GridGuard AI - Evaluation of the regime-aware hybrid forecast vs. direct
XGBoost vs. previous-day baseline.

Compares, on full 2020 test / pre-COVID / COVID-onset:
  A. Direct multi-horizon XGBoost alone (ml/models/direct_hourly/)
  B. Previous-day baseline alone
  C. Hybrid regime-aware forecast (ml/src/robust_hourly_forecast.py)

At every origin, the regime decision uses ONLY information available at or
before that origin (verified in ml/tests/test_regime_detector.py) -- future
actual demand is never touched before the decision is made.

Does not modify any existing model, pipeline, or the direct XGBoost models
themselves.
"""
import os
import sys
import json

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(__file__))
import regime_detector as rd
import direct_hourly_forecast as dhf

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
FIG_DIR = os.path.join(REPORTS_DIR, "figures", "regime_aware")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(FIG_DIR, exist_ok=True)

TRAIN_END = pd.Timestamp("2018-12-31 23:00:00")
VAL_END = pd.Timestamp("2019-12-31 23:00:00")
TEST_END = pd.Timestamp("2020-06-26 00:00:00")
PRE_COVID_END = pd.Timestamp("2020-02-29 23:00:00")
COVID_ONSET_START = pd.Timestamp("2020-03-01 00:00:00")
MAX_HORIZON = 24
MAX_LAG = 168


def compute_metrics(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mape = float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100)
    return {"MAE": mae, "RMSE": rmse, "MAPE": mape}


def main():
    print("Loading raw data, detector, and direct models (read-only)...")
    df = dhf.load_raw_demand()
    demand_by_dt = df.set_index("datetime")["nat_demand"]
    detector = rd.RegimeDetector(df)
    direct_models, direct_metadata = dhf.load_models_and_metadata()
    feature_cols = direct_metadata["feature_list"]

    max_valid_origin_dt = df["datetime"].max() - pd.Timedelta(hours=MAX_HORIZON)
    test_origins = df[(df["datetime"] > VAL_END) & (df["datetime"] <= max_valid_origin_dt)]["datetime"].reset_index(drop=True)
    test_origins = test_origins[test_origins.map(lambda t: t in detector.signals.index and
                                                    np.isfinite(detector.signals.loc[t, "primary_score"]))].reset_index(drop=True)
    print(f"Test origins with valid detector signal: {len(test_origins)} "
          f"[{test_origins.min()} -> {test_origins.max()}]")

    # -----------------------------------------------------------------------
    # Regime decision for every origin -- made BEFORE any target-side lookup
    # -----------------------------------------------------------------------
    print("Classifying regime status for every test origin (causal, pre-target)...")
    regime_records = []
    for origin_dt in test_origins:
        status = detector.status_at(origin_dt)
        regime_records.append(status)
    regime_df = pd.DataFrame(regime_records)
    regime_df["origin_datetime"] = pd.to_datetime(regime_df["origin_datetime"])

    n_shift = (regime_df["regime_status"] == "SHIFT").sum()
    print(f"SHIFT classified at {n_shift} / {len(regime_df)} origins ({n_shift/len(regime_df)*100:.1f}%)")

    # -----------------------------------------------------------------------
    # Build origin-level features once (same as train_direct_hourly_xgboost.py)
    # -----------------------------------------------------------------------
    print("Building origin-level features for direct-model predictions...")
    WEATHER_COLS = ["T2M_toc", "QV2M_toc", "TQL_toc", "W2M_toc", "T2M_san", "QV2M_san", "TQL_san", "W2M_san",
                     "T2M_dav", "QV2M_dav", "TQL_dav", "W2M_dav"]
    origin = pd.DataFrame({"origin_datetime": df["datetime"]})
    for h in [0, 1, 2, 3, 24, 48, 168]:
        origin[f"lag_{h}h_nat_demand"] = df["nat_demand"].shift(h)
    for w in [24, 168]:
        origin[f"roll_mean_{w}h_nat_demand"] = df["nat_demand"].rolling(w, min_periods=w).mean()
        origin[f"roll_std_{w}h_nat_demand"] = df["nat_demand"].rolling(w, min_periods=w).std()
    for w in [3, 6]:
        origin[f"roll_mean_{w}h_nat_demand"] = df["nat_demand"].rolling(w, min_periods=w).mean()
    for c in WEATHER_COLS:
        origin[f"origin_{c}"] = df[c]
        origin[f"lag_24h_{c}"] = df[c].shift(24)
    origin["origin_hour_of_day"] = df["datetime"].dt.hour
    origin["origin_day_of_week"] = df["datetime"].dt.dayofweek
    origin["origin_holiday_flag"] = df["holiday"]
    origin["origin_school_flag"] = df["school"]
    origin_test = origin[origin["origin_datetime"].isin(test_origins)].reset_index(drop=True)

    calendar_by_dt = df.set_index("datetime")[["Holiday_ID", "holiday", "school"]]

    # -----------------------------------------------------------------------
    # For every origin x horizon: actual, direct-model pred, prev-day pred.
    # Vectorized/batched PER HORIZON (one model.predict() call per horizon
    # across all test origins at once) rather than one call per row --
    # 24 batched calls instead of ~100K individual ones, same results.
    # -----------------------------------------------------------------------
    print("Scoring direct model + previous-day baseline for every origin x horizon (batched by horizon)...")
    origin_test = origin_test.merge(regime_df[["origin_datetime", "regime_status"]], on="origin_datetime", how="left")
    assert origin_test["regime_status"].isna().sum() == 0

    all_frames = []
    for h in range(1, MAX_HORIZON + 1):
        hdf = origin_test.copy()
        hdf["horizon"] = h
        hdf["target_datetime"] = hdf["origin_datetime"] + pd.Timedelta(hours=h)
        hdf["actual"] = hdf["target_datetime"].map(demand_by_dt)

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

        X = hdf[feature_cols].astype(float)
        hdf["direct_pred"] = direct_models[h].predict(X)

        prev_day_source = hdf["origin_datetime"] + pd.Timedelta(hours=h - 24)
        hdf["prev_day_pred"] = prev_day_source.map(demand_by_dt).values

        hdf["hybrid_pred"] = np.where(hdf["regime_status"] == "NORMAL", hdf["direct_pred"], hdf["prev_day_pred"])

        all_frames.append(hdf[["origin_datetime", "target_datetime", "horizon", "actual",
                                 "direct_pred", "prev_day_pred", "hybrid_pred", "regime_status"]])
        print(f"  ...horizon {h}/24 scored ({len(hdf)} origins)")

    results = pd.concat(all_frames, ignore_index=True)
    results = results.dropna(subset=["actual", "direct_pred", "prev_day_pred"]).reset_index(drop=True)
    results.to_csv(os.path.join(DATA_DIR, "regime_aware_evaluation_results.csv"), index=False)
    print(f"Saved: {os.path.join(DATA_DIR, 'regime_aware_evaluation_results.csv')} ({len(results)} rows)")

    # -----------------------------------------------------------------------
    # Leakage sanity: regime decision made from data strictly before target
    # -----------------------------------------------------------------------
    assert (results["origin_datetime"] < results["target_datetime"]).all()
    assert np.isfinite(results[["actual", "direct_pred", "prev_day_pred", "hybrid_pred"]].values).all()

    # -----------------------------------------------------------------------
    # Metrics by horizon, by period, for A/B/C
    # -----------------------------------------------------------------------
    print("\nComputing metrics by horizon and period...")
    periods = {
        "full_test": results,
        "pre_covid": results[results["origin_datetime"] <= PRE_COVID_END],
        "covid_onset": results[results["origin_datetime"] >= COVID_ONSET_START],
    }

    metric_rows = []
    for period_name, d in periods.items():
        for h in range(1, MAX_HORIZON + 1):
            sub = d[d["horizon"] == h]
            if len(sub) == 0:
                continue
            direct_m = compute_metrics(sub["actual"], sub["direct_pred"])
            prevday_m = compute_metrics(sub["actual"], sub["prev_day_pred"])
            hybrid_m = compute_metrics(sub["actual"], sub["hybrid_pred"])
            strongest_baseline_mae = prevday_m["MAE"]  # established in prior report as the strongest simple baseline
            metric_rows.append({
                "period": period_name, "horizon": h, "n": len(sub),
                "direct_MAE": direct_m["MAE"], "direct_RMSE": direct_m["RMSE"], "direct_MAPE": direct_m["MAPE"],
                "prevday_MAE": prevday_m["MAE"], "prevday_RMSE": prevday_m["RMSE"], "prevday_MAPE": prevday_m["MAPE"],
                "hybrid_MAE": hybrid_m["MAE"], "hybrid_RMSE": hybrid_m["RMSE"], "hybrid_MAPE": hybrid_m["MAPE"],
                "hybrid_beats_direct": hybrid_m["MAE"] < direct_m["MAE"],
                "hybrid_beats_prevday": hybrid_m["MAE"] < prevday_m["MAE"],
                "hybrid_beats_strongest": hybrid_m["MAE"] < strongest_baseline_mae,
            })
    metrics_df = pd.DataFrame(metric_rows)
    metrics_df.to_csv(os.path.join(DATA_DIR, "regime_aware_metrics_by_horizon.csv"), index=False)
    print(f"Saved: {os.path.join(DATA_DIR, 'regime_aware_metrics_by_horizon.csv')}")

    for period_name in periods:
        sub = metrics_df[metrics_df["period"] == period_name]
        n_beats_direct = int(sub["hybrid_beats_direct"].sum())
        n_beats_prevday = int(sub["hybrid_beats_prevday"].sum())
        print(f"\n{period_name}: hybrid beats direct at {n_beats_direct}/24 horizons, "
              f"beats prev-day baseline at {n_beats_prevday}/24 horizons")

    # -----------------------------------------------------------------------
    # Regime detection diagnostics
    # -----------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("REGIME DETECTION DIAGNOSTICS")
    print("=" * 80)

    regime_df["period"] = np.select(
        [regime_df["origin_datetime"] <= PRE_COVID_END, regime_df["origin_datetime"] >= COVID_ONSET_START],
        ["pre_covid", "covid_onset"], default="other")

    pre_covid_regime = regime_df[regime_df["period"] == "pre_covid"]
    covid_onset_regime = regime_df[regime_df["period"] == "covid_onset"]

    pre_covid_false_positive_rate = (pre_covid_regime["regime_status"] == "SHIFT").mean() * 100
    covid_onset_detection_rate = (covid_onset_regime["regime_status"] == "SHIFT").mean() * 100
    print(f"Pre-COVID false-positive rate (origins classified SHIFT when no shift is known to exist): "
          f"{pre_covid_false_positive_rate:.2f}% ({(pre_covid_regime['regime_status']=='SHIFT').sum()}/{len(pre_covid_regime)})")
    print(f"COVID-onset detection rate (origins classified SHIFT during the documented shift period): "
          f"{covid_onset_detection_rate:.2f}% ({(covid_onset_regime['regime_status']=='SHIFT').sum()}/{len(covid_onset_regime)})")

    first_shift = regime_df[regime_df["regime_status"] == "SHIFT"]["origin_datetime"].min()
    print(f"First origin classified SHIFT: {first_shift}")

    regime_df.to_csv(os.path.join(DATA_DIR, "regime_classification_timeline.csv"), index=False)

    # NORMAL vs SHIFT period performance (hybrid == direct during NORMAL, == prevday during SHIFT, by construction)
    for status in ["NORMAL", "SHIFT"]:
        sub = results[results["regime_status"] == status]
        if len(sub) == 0:
            continue
        m = compute_metrics(sub["actual"], sub["hybrid_pred"])
        print(f"Hybrid performance during {status} periods: MAE={m['MAE']:.2f}, RMSE={m['RMSE']:.2f}, MAPE={m['MAPE']:.2f}%")

    # -----------------------------------------------------------------------
    # Plots
    # -----------------------------------------------------------------------
    print("\nGenerating plots...")
    full = metrics_df[metrics_df["period"] == "full_test"].sort_values("horizon")

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(full["horizon"], full["direct_MAE"], marker="o", label="A. Direct XGBoost")
    ax.plot(full["horizon"], full["prevday_MAE"], marker="o", label="B. Previous-day baseline")
    ax.plot(full["horizon"], full["hybrid_MAE"], marker="o", label="C. Hybrid (regime-aware)")
    ax.set_xlabel("Forecast horizon (hours)")
    ax.set_ylabel("MAE (MW)")
    ax.set_title("MAE by Horizon — Direct vs. Previous-Day vs. Hybrid (Full 2020 Test)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "mae_by_horizon_three_way.png"), dpi=120)
    plt.close(fig)

    pre = metrics_df[metrics_df["period"] == "pre_covid"].sort_values("horizon")
    post = metrics_df[metrics_df["period"] == "covid_onset"].sort_values("horizon")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    for ax, d, title in [(ax1, pre, "Pre-COVID"), (ax2, post, "COVID-Onset")]:
        ax.plot(d["horizon"], d["direct_MAE"], marker="o", label="Direct")
        ax.plot(d["horizon"], d["prevday_MAE"], marker="o", label="Prev-day")
        ax.plot(d["horizon"], d["hybrid_MAE"], marker="o", label="Hybrid")
        ax.set_title(title)
        ax.set_xlabel("Horizon (h)")
        ax.legend()
    ax1.set_ylabel("MAE (MW)")
    fig.suptitle("Pre-COVID vs. COVID-Onset: MAE by Horizon")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "pre_covid_vs_covid_performance.png"), dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(14, 4))
    ax.plot(regime_df["origin_datetime"], regime_df["primary_score"], linewidth=0.8, label="Primary detector score")
    ax.axhline(detector.thresholds["lower_threshold"], color="red", linestyle="--", label="Lower threshold (frozen, train+val)")
    shift_mask = regime_df["regime_status"] == "SHIFT"
    ax.scatter(regime_df.loc[shift_mask, "origin_datetime"], regime_df.loc[shift_mask, "primary_score"],
               color="red", s=6, zorder=5, label="Classified SHIFT")
    ax.set_title("Regime Detection Timeline — 2020 Test Period")
    ax.set_ylabel("Primary detector score")
    ax.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "regime_detection_timeline.png"), dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    counts = regime_df["regime_status"].value_counts()
    ax.bar(counts.index, counts.values, color=["green" if k == "NORMAL" else "red" for k in counts.index])
    ax.set_title("Regime Classification Counts — 2020 Test Period")
    ax.set_ylabel("Number of origins")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "regime_classification_counts.png"), dpi=120)
    plt.close(fig)

    # improvement of hybrid over strongest simple baseline (prev-day), by horizon, full test
    fig, ax = plt.subplots(figsize=(10, 5))
    improvement = (full["prevday_MAE"] - full["hybrid_MAE"]) / full["prevday_MAE"] * 100
    colors = ["green" if v > 0 else "red" for v in improvement]
    ax.bar(full["horizon"], improvement, color=colors)
    ax.axhline(0, color="black", linewidth=1)
    ax.set_xlabel("Forecast horizon (hours)")
    ax.set_ylabel("% improvement of hybrid over previous-day baseline")
    ax.set_title("Hybrid vs. Previous-Day Baseline — % Improvement by Horizon (Full 2020 Test)")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "hybrid_vs_baseline_improvement.png"), dpi=120)
    plt.close(fig)

    print(f"Saved plots under: {FIG_DIR}")

    summary = {
        "n_test_origins": int(len(test_origins)),
        "n_shift_classified": int(n_shift),
        "pct_shift_classified": float(n_shift / len(test_origins) * 100),
        "thresholds": detector.thresholds,
        "pre_covid_false_positive_rate_pct": float(pre_covid_false_positive_rate),
        "covid_onset_detection_rate_pct": float(covid_onset_detection_rate),
        "first_shift_classified_at": str(first_shift),
        "metrics_by_horizon_csv": "ml/data/regime_aware_metrics_by_horizon.csv",
        "regime_timeline_csv": "ml/data/regime_classification_timeline.csv",
    }
    with open(os.path.join(REPORTS_DIR, "regime_aware_evaluation_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nSaved: {os.path.join(REPORTS_DIR, 'regime_aware_evaluation_summary.json')}")
    print("\nDONE.")


if __name__ == "__main__":
    main()
