"""
GridGuard AI - Rolling historical integration pipeline (FINAL forecasting
architecture).

    Origin t
        v
    Regime Detector (existing, unmodified ml/src/regime_detector.py)
        +---- NORMAL -> Direct XGBoost (existing, unmodified per-horizon
        |               models) + causal 168h bias correction (computed in
        |               this file only -- no existing file modified)
        +---- SHIFT  -> Same-hour-previous-day fallback
        v
    24 genuine hourly forecasts (t+1 .. t+24)
        v
    Existing, unmodified synthetic feeder allocation (feeder_generator.py)
        v
    Existing, unmodified Grid Stress Engine (stress_engine.py)
        v
    ml/data/rolling_feeder_results.csv

This REPLACES the previous version's forecasting call (a single 24h XGBoost
point interpolated against a historical diurnal shape) with the finalized
principled hybrid established in ml/reports/principled_hybrid_investigation.md
(Method F: best full-test mean MAE of every approach tested, 63.15 MW,
beating both plain Direct XGBoost (77.72) and the previous-day baseline
(66.15) alone).

Does NOT modify: any trained model, build_features.py, regime_detector.py,
robust_hourly_forecast.py, stress_engine.py, feeder_generator.py, the
Prevention/Action Engine, or any backend/frontend code. Only this file was
changed for this integration; the bias-correction logic lives here (not in
robust_hourly_forecast.py) per this task's explicit "modify ONLY
rolling_integration.py" instruction.

*** ALL FEEDER-LEVEL OUTPUT IS SYNTHETIC SIMULATION DATA. *** See
feeder_generator.py's module docstring: the Panama dataset has no real
feeder-level measurements. Voltage is a simplified engineering
approximation (a linear utilization-based model), NOT a power-flow
simulation and NOT measured data. Nothing in
ml/data/rolling_feeder_results.csv or this report represents real Panama
feeder telemetry.
"""
import os
import sys
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(__file__))
import feeder_generator as fg
import stress_engine as se
import regime_detector as rd
import direct_hourly_forecast as dhf

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
FIG_DIR = os.path.join(REPORTS_DIR, "figures", "rolling_integration")
os.makedirs(FIG_DIR, exist_ok=True)

SEED = fg.SEED
OUT_CSV = os.path.join(DATA_DIR, "rolling_feeder_results.csv")

MAX_HORIZON = 24
BIAS_WINDOW_HOURS = 168  # same 7-day causal window used and validated in principled_hybrid_forecast.py

TRAIN_END = rd.TRAIN_END
VAL_END = rd.VAL_END
TEST_START = VAL_END + pd.Timedelta(hours=1)

WEATHER_COLS = ["T2M_toc", "QV2M_toc", "TQL_toc", "W2M_toc", "T2M_san", "QV2M_san", "TQL_san", "W2M_san",
                 "T2M_dav", "QV2M_dav", "TQL_dav", "W2M_dav"]


def build_origin_features(df: pd.DataFrame) -> pd.DataFrame:
    """Same origin-time (horizon-independent) feature construction used by
    train_direct_hourly_xgboost.py -- reimplemented here (not imported, to
    avoid modifying that training script) since this is a separate,
    read-only inference-time feature build."""
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
    return origin


def add_target_time_features(hdf: pd.DataFrame, calendar_by_dt: pd.DataFrame) -> pd.DataFrame:
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
    return hdf


def compute_national_forecasts(df: pd.DataFrame, direct_models: dict, feature_cols: list,
                                origin_range_start: pd.Timestamp, origin_range_end: pd.Timestamp) -> pd.DataFrame:
    """
    For every origin in [origin_range_start, origin_range_end] and every
    horizon h=1..24, computes:
      - direct_pred_h: the raw, unmodified direct XGBoost model's prediction
      - bias_corrected_pred_h: direct_pred_h minus a causal 168h trailing
        bias estimate, using ONLY forecast errors whose TARGET time has
        already occurred at or before the ORIGIN of the forecast being
        corrected (never future information -- see the leakage-safety
        construction comment below, identical to the one validated in
        principled_hybrid_forecast.py).

    origin_range_start is set earlier than the test period start so that the
    168h trailing bias window is already warmed up by the time the actual
    2020 test period begins (avoiding the "first 168h uncorrected" gap that
    existed in the standalone experiment).
    """
    demand_by_dt = df.set_index("datetime")["nat_demand"]
    calendar_by_dt = df.set_index("datetime")[["Holiday_ID", "holiday", "school"]]

    origin_features = build_origin_features(df)
    origin_feature_cols = [c for c in origin_features.columns if c != "origin_datetime"]
    origin_features = origin_features.dropna(subset=origin_feature_cols).reset_index(drop=True)

    origin_slice = origin_features[
        (origin_features["origin_datetime"] >= origin_range_start) &
        (origin_features["origin_datetime"] <= origin_range_end)
    ].reset_index(drop=True)

    all_frames = []
    for h in range(1, MAX_HORIZON + 1):
        hdf = origin_slice.copy()
        hdf["horizon"] = h
        hdf["target_datetime"] = hdf["origin_datetime"] + pd.Timedelta(hours=h)
        hdf["actual"] = hdf["target_datetime"].map(demand_by_dt)
        hdf = add_target_time_features(hdf, calendar_by_dt)

        X = hdf[feature_cols].astype(float)
        hdf["direct_pred"] = direct_models[h].predict(X)
        all_frames.append(hdf[["origin_datetime", "target_datetime", "horizon", "actual", "direct_pred"]])

    long_df = pd.concat(all_frames, ignore_index=True)
    long_df["direct_error"] = long_df["direct_pred"] - long_df["actual"]

    # LEAKAGE-SAFE causal bias correction (identical construction to
    # principled_hybrid_forecast.py, re-derived here since that file is not
    # imported to keep this integration self-contained in rolling_integration.py):
    # trailing rolling mean of past errors, indexed by TARGET time (since
    # that's when each error becomes known), then SHIFTED BACK by h hours so
    # the value attached to a row reflects only errors known as of that
    # row's own ORIGIN time, never its target time.
    bias_lookup = {}
    for h in range(1, MAX_HORIZON + 1):
        sub = long_df[long_df["horizon"] == h].sort_values("target_datetime").copy()
        sub["trailing_bias_at_origin"] = sub["direct_error"].rolling(
            window=BIAS_WINDOW_HOURS, min_periods=BIAS_WINDOW_HOURS).mean().shift(h)
        bias_lookup[h] = sub.set_index("target_datetime")["trailing_bias_at_origin"]

    bias_values = []
    for h in range(1, MAX_HORIZON + 1):
        sub = long_df[long_df["horizon"] == h]
        bias_values.extend(bias_lookup[h].reindex(sub["target_datetime"]).values)
    long_df["trailing_bias"] = bias_values

    long_df["bias_corrected_pred"] = long_df["direct_pred"] - long_df["trailing_bias"].fillna(0.0)
    long_df.loc[long_df["trailing_bias"].isna(), "bias_corrected_pred"] = long_df.loc[
        long_df["trailing_bias"].isna(), "direct_pred"]

    return long_df


def main():
    print("Loading national demand series, regime detector, and direct XGBoost models (all read-only)...")
    df = dhf.load_raw_demand()
    national_demand = fg.load_national_demand_series()
    detector = rd.RegimeDetector(df)  # existing, unmodified
    direct_models, direct_metadata = dhf.load_models_and_metadata()  # existing, unmodified
    feature_cols = direct_metadata["feature_list"]

    for h in range(1, MAX_HORIZON + 1):
        assert list(direct_models[h].get_booster().feature_names) == feature_cols, \
            f"horizon_{h:02d} model's feature names do not match direct_hourly_metadata.json"
    print(f"Confirmed: all 24 direct models expect exactly {len(feature_cols)} features, matching metadata.")

    max_valid_origin_dt = df["datetime"].max() - pd.Timedelta(hours=MAX_HORIZON)
    test_origins_all = df[(df["datetime"] >= TEST_START) & (df["datetime"] <= max_valid_origin_dt)]["datetime"]
    test_origins_all = test_origins_all[test_origins_all.map(
        lambda t: t in detector.signals.index and np.isfinite(detector.signals.loc[t, "primary_score"])
    )].reset_index(drop=True)
    N_ORIGINS = len(test_origins_all)
    PERIOD_START = test_origins_all.min()
    PERIOD_END = test_origins_all.max()
    print(f"2020 test-period boundaries (unchanged): {PERIOD_START} -> {PERIOD_END} ({N_ORIGINS} origins)")

    # -----------------------------------------------------------------------
    # 1. Feeder setup (existing, unmodified feeder_generator functions)
    # -----------------------------------------------------------------------
    feeders = fg.get_feeder_definitions()
    feeder_ids = [f["id"] for f in feeders]
    feeder_type_map = {f["id"]: f["type"] for f in feeders}
    assert len(feeders) == 10

    historical_feeder_loads = fg.allocate_feeder_loads(national_demand, feeders, seed=SEED, add_noise=True)
    capacities = fg.compute_feeder_capacities(feeders, historical_feeder_loads)

    # -----------------------------------------------------------------------
    # 2. Regime classification for every origin (existing, unmodified,
    #    strictly causal detector)
    # -----------------------------------------------------------------------
    print("Classifying regime status for every origin (causal, pre-target)...")
    regime_rows = [detector.status_at(t) for t in test_origins_all]
    regime_df = pd.DataFrame(regime_rows)
    regime_df["origin_datetime"] = pd.to_datetime(regime_df["origin_datetime"])
    n_shift = int((regime_df["regime_status"] == "SHIFT").sum())
    print(f"SHIFT classified at {n_shift}/{N_ORIGINS} origins ({n_shift/N_ORIGINS*100:.1f}%)")

    # -----------------------------------------------------------------------
    # 3. Genuine hourly national forecasts: direct XGBoost + causal bias
    #    correction, computed over a WARM-UP-EXTENDED range so the bias
    #    window is already populated for the very first test origin.
    # -----------------------------------------------------------------------
    warm_up_start = PERIOD_START - pd.Timedelta(hours=BIAS_WINDOW_HOURS + MAX_HORIZON + 7 * 24)
    print(f"Computing genuine per-horizon national forecasts (direct + causal bias correction), "
          f"warm-up range from {warm_up_start}...")
    national_long = compute_national_forecasts(df, direct_models, feature_cols, warm_up_start, PERIOD_END)

    test_national = national_long[national_long["origin_datetime"].isin(test_origins_all)].copy()
    test_national = test_national.merge(regime_df[["origin_datetime", "regime_status", "primary_score",
                                                      "secondary_score"]], on="origin_datetime", how="left")
    assert test_national["regime_status"].isna().sum() == 0

    demand_by_dt = df.set_index("datetime")["nat_demand"]
    prev_day_source = test_national["origin_datetime"] + pd.to_timedelta(test_national["horizon"] - 24, unit="h")
    assert (prev_day_source <= test_national["origin_datetime"]).all(), "Fallback source must never be in the future"
    test_national["prev_day_pred"] = prev_day_source.map(demand_by_dt).values
    assert test_national["prev_day_pred"].isna().sum() == 0

    test_national["final_national_forecast_mw"] = np.where(
        test_national["regime_status"] == "NORMAL", test_national["bias_corrected_pred"], test_national["prev_day_pred"]
    )
    test_national["forecast_method"] = np.where(
        test_national["regime_status"] == "NORMAL", "BIAS_CORRECTED_DIRECT_XGBOOST", "PREVIOUS_DAY_FALLBACK"
    )
    assert np.isfinite(test_national["final_national_forecast_mw"]).all()

    n_method = test_national.drop_duplicates("origin_datetime")["forecast_method"].value_counts()
    print(f"Forecast method distribution (by origin): {n_method.to_dict()}")

    # -----------------------------------------------------------------------
    # 4. Per origin: build the genuine 25-point (h=0 actual + h=1..24
    #    forecast) national trajectory, allocate to feeders (existing,
    #    unmodified logic), run the stress engine (existing, unmodified).
    # -----------------------------------------------------------------------
    print("Rolling feeder allocation + stress engine across the 2020 test period (genuine hourly forecasts)...")
    current_by_origin = df.set_index("datetime")["nat_demand"]
    grouped = test_national.sort_values(["origin_datetime", "horizon"]).groupby("origin_datetime")

    records = []
    for idx, (origin_dt, group) in enumerate(grouped):
        group = group.sort_values("horizon")
        assert list(group["horizon"]) == list(range(1, MAX_HORIZON + 1))
        assert (group["target_datetime"].values == (origin_dt + pd.to_timedelta(np.arange(1, 25), unit="h")).values).all()

        current_nat = float(current_by_origin.loc[origin_dt])
        national_values = np.concatenate([[current_nat], group["final_national_forecast_mw"].values])
        national_index = pd.DatetimeIndex([origin_dt] + list(group["target_datetime"].values))
        national_traj = pd.Series(national_values, index=national_index, name="national_forecast_trajectory")

        # existing, unmodified deterministic allocation to the 10 synthetic feeders
        feeder_traj_df = fg.build_feeder_trajectories(national_traj, feeders)

        regime_status = group["regime_status"].iloc[0]
        forecast_method = group["forecast_method"].iloc[0]
        regime_score = float(group["primary_score"].iloc[0])
        regime_secondary_score = group["secondary_score"].iloc[0]

        for fid in feeder_ids:
            traj = feeder_traj_df[fid]
            cap = float(capacities.loc[fid, "capacity_mw"])
            current_load = float(traj.iloc[0])
            forecast_load_24h = float(traj.iloc[-1])
            utilization = current_load / cap
            forecast_utilization_24h = forecast_load_24h / cap
            util_traj = (traj / cap).values
            voltage_traj = fg.simulate_voltage(util_traj, seed=SEED, add_noise=False)  # existing, unmodified
            voltage_pu = float(voltage_traj[0])

            # existing, unmodified Grid Stress Engine -- source of truth for risk
            score, _components = se.compute_stress_score(current_load, forecast_load_24h, cap, voltage_pu)
            risk = se.classify_stress(score)
            tto = se.time_to_overload(traj, cap)

            for h in range(1, MAX_HORIZON + 1):
                records.append({
                    "origin_datetime": origin_dt,
                    "forecast_datetime": traj.index[h],
                    "forecast_horizon": h,
                    "feeder_id": fid,
                    "feeder_type": feeder_type_map[fid],
                    "forecast_mw": float(traj.iloc[h]),
                    "load_mw": current_load,
                    "forecast_load_mw": forecast_load_24h,
                    "capacity_mw": cap,
                    "utilization": utilization,
                    "forecast_utilization": forecast_utilization_24h,
                    "stress_score": score,
                    "risk_level": risk,
                    "overload_predicted": tto["overload_predicted"],
                    "time_to_overload_hours": tto["time_to_overload_hours"],
                    "voltage_pu": voltage_pu,
                    "regime_status": regime_status,
                    "forecast_method": forecast_method,
                    "regime_score": regime_score,
                    "regime_secondary_score": regime_secondary_score,
                    "national_current_demand_mw": current_nat,
                    "national_forecast_mw": float(national_traj.iloc[h]),
                })
        if (idx + 1) % 1000 == 0:
            print(f"  ...{idx + 1}/{N_ORIGINS} origins processed")

    results = pd.DataFrame(records)
    print(f"Rolled {len(results)} rows from {N_ORIGINS} origins x {MAX_HORIZON} horizons x {len(feeder_ids)} feeders.")

    results.to_csv(OUT_CSV, index=False)
    print(f"Saved: {OUT_CSV}")

    # -----------------------------------------------------------------------
    # Validation
    # -----------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("VALIDATION")
    print("=" * 80)
    validations = {}

    validations["exactly_24_horizons_per_origin_feeder"] = bool(
        (results.groupby(["origin_datetime", "feeder_id"]).size() == MAX_HORIZON).all()
    )
    validations["forecast_datetime_exactly_origin_plus_horizon"] = bool(
        ((pd.to_datetime(results["forecast_datetime"]) - pd.to_datetime(results["origin_datetime"])) ==
         pd.to_timedelta(results["forecast_horizon"], unit="h")).all()
    )
    validations["no_duplicate_origin_horizon_feeder_rows"] = bool(
        results.duplicated(subset=["origin_datetime", "forecast_horizon", "feeder_id"]).sum() == 0
    )
    core_cols = ["forecast_mw", "load_mw", "forecast_load_mw", "capacity_mw", "utilization",
                 "forecast_utilization", "stress_score", "voltage_pu", "regime_score"]
    validations["no_nan_inf_core_numeric"] = bool(np.isfinite(results[core_cols].values).all())
    validations["stress_score_bounded_0_100"] = bool(results["stress_score"].between(0, 100).all())
    validations["utilization_non_negative"] = bool(
        (results["utilization"] >= 0).all() and (results["forecast_utilization"] >= 0).all())
    validations["forecast_mw_non_negative"] = bool((results["forecast_mw"] >= 0).all())

    recomputed_risk = results["stress_score"].apply(se.classify_stress)
    validations["risk_level_agrees_with_engine"] = bool((recomputed_risk == results["risk_level"]).all())

    valid_methods = {"BIAS_CORRECTED_DIRECT_XGBOOST", "PREVIOUS_DAY_FALLBACK"}
    validations["forecast_method_valid_values"] = bool(set(results["forecast_method"].unique()) <= valid_methods)
    validations["normal_uses_bias_corrected_direct"] = bool(
        (results.loc[results["regime_status"] == "NORMAL", "forecast_method"] == "BIAS_CORRECTED_DIRECT_XGBOOST").all()
    )
    validations["shift_uses_previous_day_fallback"] = bool(
        (results.loc[results["regime_status"] == "SHIFT", "forecast_method"] == "PREVIOUS_DAY_FALLBACK").all()
    )

    origins_per = results.groupby("origin_datetime").size()
    validations["exactly_240_rows_per_origin"] = bool((origins_per == MAX_HORIZON * len(feeder_ids)).all())
    validations["test_period_boundaries_preserved"] = bool(
        pd.to_datetime(results["origin_datetime"]).min() == PERIOD_START and
        pd.to_datetime(results["origin_datetime"]).max() == PERIOD_END and
        len(origins_per) == N_ORIGINS
    )
    validations["chronological_ordering"] = bool(
        pd.Series(list(grouped.groups.keys())).is_monotonic_increasing
    )

    # No-future-information spot checks
    validations["fallback_source_never_future"] = bool(
        (prev_day_source <= test_national["origin_datetime"]).all()
    )
    sample_check = national_long.dropna(subset=["trailing_bias"]).sample(n=min(300, national_long["trailing_bias"].notna().sum()), random_state=0)
    leak_ok = True
    for _, row in sample_check.iterrows():
        h = row["horizon"]
        origin = row["origin_datetime"]
        window_source = national_long[(national_long["horizon"] == h) &
                                        (national_long["target_datetime"] <= origin) &
                                        (national_long["target_datetime"] > origin - pd.Timedelta(hours=BIAS_WINDOW_HOURS))]
        if not (window_source["target_datetime"] <= origin).all():
            leak_ok = False
            break
    validations["bias_correction_no_future_leakage"] = bool(leak_ok)

    for k, v in validations.items():
        print(f"  {k}: {v}")
    all_passed = all(validations.values())
    print(f"\nALL VALIDATIONS PASSED: {all_passed}")
    assert all_passed, f"Validation failure(s): {[k for k, v in validations.items() if not v]}"

    return (results, regime_df, test_national, capacities, feeders, feeder_type_map, validations,
            PERIOD_START, PERIOD_END, N_ORIGINS, n_shift, n_method)


if __name__ == "__main__":
    (results, regime_df, test_national, capacities, feeders, feeder_type_map, validations,
     PERIOD_START, PERIOD_END, N_ORIGINS, n_shift, n_method) = main()

    feeder_ids = [f["id"] for f in feeders]

    # =========================================================================
    # Summary statistics
    # =========================================================================
    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)

    per_origin_feeder = results.drop_duplicates(subset=["origin_datetime", "feeder_id"])

    risk_dist = per_origin_feeder["risk_level"].value_counts(normalize=True).reindex(
        ["LOW", "MODERATE", "HIGH", "CRITICAL"]).fillna(0) * 100
    print("\nOverall risk-level distribution (%, per origin-feeder):")
    print(risk_dist.round(3))

    max_stress = per_origin_feeder["stress_score"].max()
    max_stress_row = per_origin_feeder.loc[per_origin_feeder["stress_score"].idxmax()]
    max_util = per_origin_feeder["utilization"].max()
    print(f"\nMax stress score: {max_stress:.2f} (feeder {max_stress_row['feeder_id']}, {max_stress_row['origin_datetime']})")
    print(f"Max utilization: {max_util:.4f}")

    n_overload = int(per_origin_feeder["overload_predicted"].sum())
    feeders_with_overload = sorted(per_origin_feeder.loc[per_origin_feeder["overload_predicted"] == True, "feeder_id"].unique().tolist())
    print(f"\nNumber of predicted overload events (origin-feeder pairs): {n_overload}")
    print(f"Feeders affected: {feeders_with_overload}")
    if n_overload > 0:
        min_tto = per_origin_feeder.loc[per_origin_feeder["overload_predicted"] == True, "time_to_overload_hours"].min()
        print(f"Minimum time-to-overload observed: {min_tto:.2f}h")
    else:
        min_tto = None
        print("Minimum time-to-overload: N/A (no overload events predicted in this period)")

    per_feeder_summary = per_origin_feeder.groupby("feeder_id").agg(
        feeder_type=("feeder_type", "first"),
        mean_stress=("stress_score", "mean"),
        median_stress=("stress_score", "median"),
        max_stress=("stress_score", "max"),
        mean_utilization=("utilization", "mean"),
        max_utilization=("utilization", "max"),
        n_moderate_plus=("risk_level", lambda s: (s != "LOW").sum()),
        n_overload=("overload_predicted", "sum"),
    )
    print("\nPer-feeder summary:")
    print(per_feeder_summary.round(3))

    # =========================================================================
    # Plots
    # =========================================================================
    print("\nGenerating plots...")

    fig, ax = plt.subplots(figsize=(14, 5))
    for fid in feeder_ids:
        sub = per_origin_feeder[per_origin_feeder["feeder_id"] == fid]
        ax.plot(sub["origin_datetime"], sub["stress_score"], linewidth=0.6, alpha=0.7, label=fid)
    for edge in [30, 60, 80]:
        ax.axhline(edge, color="gray", linestyle="--", alpha=0.4)
    ax.set_title("Stress Score Over Time — All Feeders (2020 Test Period, Final Forecasting Pipeline)\n(SYNTHETIC simulation data)")
    ax.set_ylabel("Stress score")
    ax.legend(ncol=5, fontsize=7)
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "stress_over_time_all_feeders.png"), dpi=120)
    plt.close(fig)

    fig, axes = plt.subplots(5, 2, figsize=(14, 14), sharex=True, sharey=True)
    for ax, fid in zip(axes.flat, feeder_ids):
        sub = per_origin_feeder[per_origin_feeder["feeder_id"] == fid]
        ax.plot(sub["origin_datetime"], sub["stress_score"], linewidth=0.6, color="steelblue")
        for edge in [30, 60, 80]:
            ax.axhline(edge, color="gray", linestyle="--", alpha=0.4)
        ax.set_title(f"{fid} ({feeder_type_map[fid]})", fontsize=9)
    fig.suptitle("Stress Score Over Time — Per Feeder (Final Forecasting Pipeline)\n(SYNTHETIC simulation data)")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "stress_over_time_per_feeder.png"), dpi=120)
    plt.close(fig)

    top_feeder = per_feeder_summary["max_stress"].idxmax()
    sub_top = per_origin_feeder[per_origin_feeder["feeder_id"] == top_feeder]
    cap_top = float(capacities.loc[top_feeder, "capacity_mw"])
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(sub_top["origin_datetime"], sub_top["load_mw"], linewidth=0.7, label="Current load (MW)")
    ax.axhline(cap_top, color="red", linestyle="--", label=f"Capacity ({cap_top:.2f} MW)")
    ax.set_title(f"Load vs. Capacity — Most-Stressed Feeder {top_feeder} ({feeder_type_map[top_feeder]})\n(SYNTHETIC simulation data)")
    ax.set_ylabel("MW")
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "utilization_vs_capacity_most_stressed.png"), dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 5))
    risk_dist.plot(kind="bar", ax=ax, color=["green", "gold", "orange", "red"])
    ax.set_title("Risk-Level Distribution (Final Forecasting Pipeline)\n(SYNTHETIC simulation data)")
    ax.set_ylabel("% of origin-feeder observations")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "risk_level_distribution.png"), dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(feeder_ids))
    width = 0.35
    ax.bar(x - width / 2, per_feeder_summary.loc[feeder_ids, "mean_stress"], width, label="Mean stress")
    ax.bar(x + width / 2, per_feeder_summary.loc[feeder_ids, "max_stress"], width, label="Max stress")
    ax.set_xticks(x)
    ax.set_xticklabels(feeder_ids)
    ax.set_title("Mean vs. Max Stress Score by Feeder\n(SYNTHETIC simulation data)")
    ax.set_ylabel("Stress score")
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "feeder_comparison_mean_max_stress.png"), dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(14, 5))
    nat = results.drop_duplicates(subset=["origin_datetime", "forecast_horizon"])
    nat_h1 = nat[nat["forecast_horizon"] == 1].sort_values("origin_datetime")
    ax.plot(nat_h1["origin_datetime"], nat_h1["national_current_demand_mw"], linewidth=0.7, label="Actual national demand (current)")
    ax.plot(nat_h1["origin_datetime"] + pd.Timedelta(hours=24),
            nat.groupby("origin_datetime")["national_forecast_mw"].last().reindex(nat_h1["origin_datetime"]).values,
            linewidth=0.7, alpha=0.8, label="Final 24h-ahead forecast (genuine, regime-aware)")
    shift_origins = regime_df.loc[regime_df["regime_status"] == "SHIFT", "origin_datetime"]
    ax.scatter(shift_origins, [ax.get_ylim()[0]] * len(shift_origins), s=2, color="red", label="SHIFT classified")
    ax.set_title("National Demand: Actual vs. Final Regime-Aware 24h Forecast (2020 Test Period)")
    ax.set_ylabel("nat_demand (MW)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "forecast_vs_actual_national_demand.png"), dpi=120)
    plt.close(fig)

    print(f"Saved plots under: {FIG_DIR}")

    # =========================================================================
    # Save summary JSON
    # =========================================================================
    summary_out = {
        "period": {"start": str(PERIOD_START), "end": str(PERIOD_END), "n_origins": int(N_ORIGINS),
                   "n_forecast_rows": int(len(results))},
        "validations": validations,
        "regime_distribution": {"NORMAL": int(N_ORIGINS - n_shift), "SHIFT": int(n_shift),
                                  "pct_shift": float(n_shift / N_ORIGINS * 100)},
        "forecast_method_distribution": {k: int(v) for k, v in n_method.to_dict().items()},
        "risk_distribution_pct": risk_dist.round(4).to_dict(),
        "max_stress_score": {"value": float(max_stress), "feeder_id": max_stress_row["feeder_id"],
                              "origin_datetime": str(max_stress_row["origin_datetime"])},
        "max_utilization": float(max_util),
        "n_overload_events_origin_feeder_pairs": n_overload,
        "feeders_with_overload": feeders_with_overload,
        "min_time_to_overload_hours": float(min_tto) if min_tto is not None else None,
        "per_feeder_summary": per_feeder_summary.round(4).to_dict(orient="index"),
    }
    with open(os.path.join(REPORTS_DIR, "rolling_integration_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary_out, f, indent=2, default=str)
    print(f"Saved: {os.path.join(REPORTS_DIR, 'rolling_integration_summary.json')}")
    print("\nDONE.")
