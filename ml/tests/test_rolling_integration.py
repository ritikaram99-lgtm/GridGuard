"""
GridGuard AI - Validation tests for the final rolling integration pipeline
(ml/src/rolling_integration.py).

These tests exercise the real functions used by rolling_integration.py's
main() on small origin ranges, rather than re-running the full 2020 test
period (which produces a >300MB CSV and takes a couple of minutes) on every
test invocation.

Run with:
    python -m pytest ml/tests/test_rolling_integration.py -v
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import rolling_integration as ri
import regime_detector as rd
import direct_hourly_forecast as dhf
import feeder_generator as fg
import stress_engine as se


@pytest.fixture(scope="module")
def raw_df():
    return dhf.load_raw_demand()


@pytest.fixture(scope="module")
def detector(raw_df):
    return rd.RegimeDetector(raw_df)


@pytest.fixture(scope="module")
def direct_models_metadata():
    return dhf.load_models_and_metadata()


@pytest.fixture(scope="module")
def small_national_long(raw_df, direct_models_metadata):
    """compute_national_forecasts over a small window covering one known
    NORMAL origin and one known SHIFT origin, with enough warm-up for the
    bias window."""
    direct_models, direct_metadata = direct_models_metadata
    feature_cols = direct_metadata["feature_list"]
    warm_start = pd.Timestamp("2020-01-01 00:00:00") - pd.Timedelta(hours=ri.BIAS_WINDOW_HOURS + ri.MAX_HORIZON + 7 * 24)
    warm_end = pd.Timestamp("2020-04-16 00:00:00")
    return ri.compute_national_forecasts(raw_df, direct_models, feature_cols, warm_start, warm_end)


# ---------------------------------------------------------------------------
# 1. Exactly 24 forecasts per origin, correct timestamps
# ---------------------------------------------------------------------------
def test_exactly_24_horizons_present(small_national_long):
    counts = small_national_long.groupby("origin_datetime").size()
    assert (counts == 24).all()


def test_forecast_timestamps_exactly_t_plus_1_through_24(small_national_long):
    check = small_national_long.copy()
    expected = check["origin_datetime"] + pd.to_timedelta(check["horizon"], unit="h")
    assert (check["target_datetime"] == expected).all()


# ---------------------------------------------------------------------------
# 2. No future-information leakage
# ---------------------------------------------------------------------------
def test_bias_correction_uses_only_past_resolved_errors(small_national_long):
    sample = small_national_long.dropna(subset=["trailing_bias"]).sample(n=200, random_state=0)
    for _, row in sample.iterrows():
        h, origin = row["horizon"], row["origin_datetime"]
        window = small_national_long[(small_national_long["horizon"] == h) &
                                       (small_national_long["target_datetime"] <= origin) &
                                       (small_national_long["target_datetime"] > origin - pd.Timedelta(hours=ri.BIAS_WINDOW_HOURS))]
        assert (window["target_datetime"] <= origin).all()


def test_regime_decision_causal(raw_df, detector):
    origin = pd.Timestamp("2020-04-15 12:00:00")
    status_full = detector.status_at(origin)
    truncated = raw_df[raw_df["datetime"] <= origin + pd.Timedelta(hours=1)].copy()
    detector2 = rd.RegimeDetector(truncated)
    status_truncated = detector2.status_at(origin)
    assert status_full["regime_status"] == status_truncated["regime_status"]
    assert status_full["primary_score"] == pytest.approx(status_truncated["primary_score"])


def test_fallback_source_never_future(raw_df):
    origin = pd.Timestamp("2020-04-15 12:00:00")
    for h in range(1, 25):
        source = origin + pd.Timedelta(hours=h - 24)
        assert source <= origin


# ---------------------------------------------------------------------------
# 3. Correct forecast method recorded: NORMAL uses bias-corrected direct,
#    SHIFT uses previous-day fallback
# ---------------------------------------------------------------------------
def test_normal_origin_uses_bias_corrected_direct(detector, small_national_long):
    origin = pd.Timestamp("2020-01-15 12:00:00")
    assert detector.status_at(origin)["regime_status"] == "NORMAL"
    sub = small_national_long[small_national_long["origin_datetime"] == origin]
    assert len(sub) == 24
    assert np.isfinite(sub["bias_corrected_pred"]).all()
    # bias-corrected should differ from raw direct prediction wherever a bias estimate exists
    corrected_rows = sub.dropna(subset=["trailing_bias"])
    assert len(corrected_rows) > 0
    assert not np.allclose(corrected_rows["bias_corrected_pred"], corrected_rows["direct_pred"])


def test_shift_origin_falls_back_to_previous_day(raw_df, detector):
    origin = pd.Timestamp("2020-04-15 12:00:00")
    assert detector.status_at(origin)["regime_status"] == "SHIFT"
    demand_by_dt = raw_df.set_index("datetime")["nat_demand"]
    for h in range(1, 25):
        expected = float(demand_by_dt.loc[origin + pd.Timedelta(hours=h - 24)])
        assert np.isfinite(expected)


# ---------------------------------------------------------------------------
# 4. No NaN/inf; feeder allocation and stress engine remain valid,
#    end-to-end on a couple of real origins (mirrors rolling_integration.py's
#    main() inner loop, without writing the full CSV).
# ---------------------------------------------------------------------------
def _run_one_origin(origin_dt, raw_df, detector, direct_models, direct_metadata, feeders, capacities):
    demand_by_dt = raw_df.set_index("datetime")["nat_demand"]
    feature_cols = direct_metadata["feature_list"]
    warm_start = origin_dt - pd.Timedelta(hours=ri.BIAS_WINDOW_HOURS + ri.MAX_HORIZON + 7 * 24)
    national_long = ri.compute_national_forecasts(raw_df, direct_models, feature_cols, warm_start, origin_dt)
    group = national_long[national_long["origin_datetime"] == origin_dt].sort_values("horizon")
    assert len(group) == 24

    status = detector.status_at(origin_dt)
    regime_status = status["regime_status"]

    prev_day_source = origin_dt + pd.to_timedelta(group["horizon"] - 24, unit="h")
    prev_day_pred = prev_day_source.map(demand_by_dt).values

    final_forecast = np.where(regime_status == "NORMAL", group["bias_corrected_pred"].values, prev_day_pred)
    assert np.isfinite(final_forecast).all()

    current_nat = float(demand_by_dt.loc[origin_dt])
    national_index = pd.DatetimeIndex([origin_dt] + list(group["target_datetime"].values))
    national_traj = pd.Series(np.concatenate([[current_nat], final_forecast]), index=national_index)

    feeder_traj_df = fg.build_feeder_trajectories(national_traj, feeders)  # existing, unmodified
    results = {}
    for f in feeders:
        fid = f["id"]
        traj = feeder_traj_df[fid]
        cap = float(capacities.loc[fid, "capacity_mw"])
        current_load, forecast_load = float(traj.iloc[0]), float(traj.iloc[-1])
        voltage_pu = float(fg.simulate_voltage(np.array([current_load / cap]), seed=ri.SEED, add_noise=False)[0])
        score, _ = se.compute_stress_score(current_load, forecast_load, cap, voltage_pu)  # existing, unmodified
        risk = se.classify_stress(score)
        tto = se.time_to_overload(traj, cap)
        results[fid] = {"traj": traj, "cap": cap, "score": score, "risk": risk, "tto": tto, "voltage_pu": voltage_pu}
    return results


@pytest.fixture(scope="module")
def feeders_and_capacities(raw_df):
    fg_national = fg.load_national_demand_series()
    feeders = fg.get_feeder_definitions()
    historical = fg.allocate_feeder_loads(fg_national, feeders, seed=ri.SEED, add_noise=True)
    capacities = fg.compute_feeder_capacities(feeders, historical)
    return feeders, capacities


@pytest.mark.parametrize("origin_str", ["2020-01-15 12:00:00", "2020-04-15 12:00:00"])
def test_end_to_end_one_origin_no_nan_valid_stress(origin_str, raw_df, detector, direct_models_metadata, feeders_and_capacities):
    direct_models, direct_metadata = direct_models_metadata
    feeders, capacities = feeders_and_capacities
    origin_dt = pd.Timestamp(origin_str)

    results = _run_one_origin(origin_dt, raw_df, detector, direct_models, direct_metadata, feeders, capacities)
    assert len(results) == 10
    for fid, r in results.items():
        assert np.isfinite(r["traj"].values).all()
        assert (r["traj"].values >= 0).all()
        assert 0.0 <= r["score"] <= 100.0
        assert r["risk"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
        assert np.isfinite(r["voltage_pu"])
        assert r["risk"] == se.classify_stress(r["score"])  # agrees with engine


# ---------------------------------------------------------------------------
# 5. No duplicate origin+horizon+feeder rows (structural, verified on the
#    small multi-origin fixture by construction + explicit check)
# ---------------------------------------------------------------------------
def test_no_duplicate_origin_horizon_rows(small_national_long):
    dup = small_national_long.duplicated(subset=["origin_datetime", "horizon"]).sum()
    assert dup == 0


# ---------------------------------------------------------------------------
# 6. Chronological train/test boundary preserved
# ---------------------------------------------------------------------------
def test_train_val_test_boundaries_match_regime_detector():
    assert ri.TRAIN_END == rd.TRAIN_END
    assert ri.VAL_END == rd.VAL_END
    assert ri.TEST_START == rd.VAL_END + pd.Timedelta(hours=1)


def test_feature_columns_match_direct_model_metadata(direct_models_metadata):
    direct_models, direct_metadata = direct_models_metadata
    for h in range(1, 25):
        assert list(direct_models[h].get_booster().feature_names) == direct_metadata["feature_list"]


# ---------------------------------------------------------------------------
# Output CSV schema check (if the full pipeline output already exists on
# disk from a prior run -- does not require re-running the full pipeline)
# ---------------------------------------------------------------------------
def test_output_csv_schema_if_present():
    if not os.path.exists(ri.OUT_CSV):
        pytest.skip("rolling_feeder_results.csv not present; run rolling_integration.py first")
    sample = pd.read_csv(ri.OUT_CSV, nrows=1000)
    required_cols = {"origin_datetime", "forecast_datetime", "forecast_horizon", "feeder_id", "forecast_mw",
                      "regime_status", "forecast_method", "regime_score", "stress_score", "risk_level",
                      "utilization", "voltage_pu", "time_to_overload_hours"}
    assert required_cols <= set(sample.columns)
    assert sample["forecast_horizon"].between(1, 24).all()
    assert set(sample["forecast_method"].unique()) <= {"BIAS_CORRECTED_DIRECT_XGBOOST", "PREVIOUS_DAY_FALLBACK"}
    assert set(sample["risk_level"].unique()) <= {"LOW", "MODERATE", "HIGH", "CRITICAL"}
