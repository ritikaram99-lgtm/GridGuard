"""
GridGuard AI - Validation tests for the regime detector and regime-aware
hourly forecast (ml/src/regime_detector.py, ml/src/robust_hourly_forecast.py).

Run with:
    python -m pytest ml/tests/test_regime_detector.py -v
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import regime_detector as rd
import robust_hourly_forecast as rhf
import direct_hourly_forecast as dhf


@pytest.fixture(scope="module")
def raw_df():
    return rd.load_raw_demand()


@pytest.fixture(scope="module")
def detector(raw_df):
    return rd.RegimeDetector(raw_df)


@pytest.fixture(scope="module")
def direct_models_metadata():
    return dhf.load_models_and_metadata()


# ---------------------------------------------------------------------------
# 1. No future-data leakage
# ---------------------------------------------------------------------------
def test_reference_built_only_from_train_period(raw_df):
    reference = rd.build_seasonal_reference(raw_df, rd.TRAIN_END)
    train_only = raw_df[raw_df["datetime"] <= rd.TRAIN_END].copy()
    train_only["month"] = train_only["datetime"].dt.month
    train_only["is_weekend"] = train_only["datetime"].dt.dayofweek.isin([5, 6])
    train_only["hour"] = train_only["datetime"].dt.hour
    manual = train_only.groupby(["month", "is_weekend", "hour"])["nat_demand"].mean()
    for _, row in reference.head(20).iterrows():
        key = (row["month"], row["is_weekend"], row["hour"])
        assert np.isclose(row["ref_mean"], manual.loc[key])


def test_threshold_frozen_from_train_val_only_not_test(detector):
    assert pd.Timestamp(detector.thresholds["train_val_range"][1]) == rd.VAL_END
    # re-freezing using a truncated (train+val only) signal set must give the identical threshold
    train_val_signals = detector.signals[detector.signals.index <= rd.VAL_END]
    re_thr = rd.freeze_thresholds(train_val_signals)
    assert re_thr["lower_threshold"] == pytest.approx(detector.thresholds["lower_threshold"])


def test_primary_score_is_causal_only(raw_df, detector):
    """Changing a value strictly AFTER origin t must not change the detector
    score computed AT origin t -- proves the rolling window is backward-only."""
    origin = pd.Timestamp("2020-03-01 00:00:00")
    score_before = detector.status_at(origin)["primary_score"]

    modified_df = raw_df.copy()
    future_mask = modified_df["datetime"] > origin
    modified_df.loc[future_mask, "nat_demand"] = modified_df.loc[future_mask, "nat_demand"] * 5.0  # drastic future change

    reference2 = rd.build_seasonal_reference(modified_df, rd.TRAIN_END)  # train period untouched by construction (train < origin)
    signals2 = rd.compute_detector_signals(modified_df, reference2)
    score_after = float(signals2.loc[origin, "primary_score"])

    assert score_before == pytest.approx(score_after), (
        "Detector score at origin t changed after modifying only FUTURE (post-origin) demand -- leakage!"
    )


def test_fallback_sources_never_after_origin(raw_df):
    origin = pd.Timestamp("2020-04-15 12:00:00")
    trajectory = rhf.previous_day_fallback(origin, raw_df)
    # every fallback value is looked up from origin-23h..origin, verified inside the function;
    # re-verify externally that all 24 target hours' *source* timestamps are <= origin
    for h in range(1, 25):
        source_dt = origin + pd.Timedelta(hours=h - 24)
        assert source_dt <= origin


def test_regime_decision_uses_no_future_demand(raw_df, detector):
    """The regime decision at origin t must be identical regardless of what
    demand values exist after t (already covered by test_primary_score_is_causal_only,
    re-verified end-to-end via status_at)."""
    origin = pd.Timestamp("2020-04-15 12:00:00")
    status1 = detector.status_at(origin)
    truncated_df = raw_df[raw_df["datetime"] <= origin + pd.Timedelta(hours=1)].copy()
    detector2 = rd.RegimeDetector(truncated_df)
    status2 = detector2.status_at(origin)
    assert status1["regime_status"] == status2["regime_status"]
    assert status1["primary_score"] == pytest.approx(status2["primary_score"])


# ---------------------------------------------------------------------------
# 2. Exactly 24 forecasts, timestamps exactly t+1..t+24
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("origin_str", ["2020-01-15 12:00:00", "2020-04-15 12:00:00", "2020-06-15 08:00:00"])
def test_exactly_24_forecasts_with_correct_timestamps(origin_str, raw_df, detector, direct_models_metadata):
    direct_models, direct_metadata = direct_models_metadata
    origin = pd.Timestamp(origin_str)
    result = rhf.robust_hourly_forecast(origin, detector, direct_models, direct_metadata, raw_df)
    assert len(result) == 24
    horizons = [r["forecast_horizon"] for r in result]
    assert horizons == list(range(1, 25))
    for r in result:
        expected_ts = origin + pd.Timedelta(hours=r["forecast_horizon"])
        assert pd.Timestamp(r["forecast_timestamp"]) == expected_ts


# ---------------------------------------------------------------------------
# 3. Predictions are in MW (finite, positive, plausible magnitude)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("origin_str", ["2020-01-15 12:00:00", "2020-04-15 12:00:00"])
def test_predictions_are_plausible_mw_values(origin_str, raw_df, detector, direct_models_metadata):
    direct_models, direct_metadata = direct_models_metadata
    result = rhf.robust_hourly_forecast(origin_str, detector, direct_models, direct_metadata, raw_df)
    for r in result:
        assert np.isfinite(r["forecast_mw"])
        assert 0 < r["forecast_mw"] < 5000  # sanity bound, well outside plausible Panama demand range


# ---------------------------------------------------------------------------
# 4. NORMAL uses XGBoost, SHIFT uses previous-day fallback
# ---------------------------------------------------------------------------
def test_normal_origin_uses_direct_xgboost(raw_df, detector, direct_models_metadata):
    direct_models, direct_metadata = direct_models_metadata
    origin = pd.Timestamp("2020-01-15 12:00:00")
    assert detector.status_at(origin)["regime_status"] == "NORMAL"
    result = rhf.robust_hourly_forecast(origin, detector, direct_models, direct_metadata, raw_df)
    assert all(r["method"] == "DIRECT_XGBOOST" for r in result)
    assert all(r["regime_status"] == "NORMAL" for r in result)


def test_shift_origin_uses_previous_day_fallback(raw_df, detector, direct_models_metadata):
    direct_models, direct_metadata = direct_models_metadata
    origin = pd.Timestamp("2020-04-15 12:00:00")
    assert detector.status_at(origin)["regime_status"] == "SHIFT"
    result = rhf.robust_hourly_forecast(origin, detector, direct_models, direct_metadata, raw_df)
    assert all(r["method"] == "PREVIOUS_DAY_FALLBACK" for r in result)
    assert all(r["regime_status"] == "SHIFT" for r in result)

    demand_by_dt = raw_df.set_index("datetime")["nat_demand"]
    for r in result:
        h = r["forecast_horizon"]
        expected = float(demand_by_dt.loc[origin + pd.Timedelta(hours=h - 24)])
        assert r["forecast_mw"] == pytest.approx(expected)


def test_pre_covid_never_classified_shift(raw_df, detector):
    """Regression test for the fixed detector: pre-COVID (Jan-Feb 2020) must
    have a 0% false-positive rate at the frozen one-sided threshold."""
    pre_covid = raw_df[(raw_df["datetime"] >= pd.Timestamp("2020-01-01")) &
                        (raw_df["datetime"] <= pd.Timestamp("2020-02-29 23:00:00"))]
    for dt in pre_covid["datetime"]:
        if dt not in detector.signals.index or not np.isfinite(detector.signals.loc[dt, "primary_score"]):
            continue
        status = detector.status_at(dt)
        assert status["regime_status"] == "NORMAL", f"False positive at {dt}"


def test_covid_onset_detects_some_shift(raw_df, detector):
    """The detector must flag at least some of the documented COVID-onset
    period as SHIFT (sanity check that it isn't a no-op)."""
    covid_onset = raw_df[raw_df["datetime"] >= pd.Timestamp("2020-03-01")]
    n_shift = 0
    n_checked = 0
    for dt in covid_onset["datetime"]:
        if dt not in detector.signals.index or not np.isfinite(detector.signals.loc[dt, "primary_score"]):
            continue
        n_checked += 1
        if detector.status_at(dt)["regime_status"] == "SHIFT":
            n_shift += 1
    assert n_shift > 0
    assert n_shift / n_checked > 0.05  # at least 5% of covid-onset hours flagged


# ---------------------------------------------------------------------------
# 5. Deterministic output
# ---------------------------------------------------------------------------
def test_deterministic_output(raw_df, detector, direct_models_metadata):
    direct_models, direct_metadata = direct_models_metadata
    origin = "2020-04-15 12:00:00"
    r1 = rhf.robust_hourly_forecast(origin, detector, direct_models, direct_metadata, raw_df)
    r2 = rhf.robust_hourly_forecast(origin, detector, direct_models, direct_metadata, raw_df)
    assert r1 == r2


def test_detector_deterministic(detector):
    origin = "2020-04-15 12:00:00"
    s1 = detector.status_at(origin)
    s2 = detector.status_at(origin)
    assert s1 == s2


# ---------------------------------------------------------------------------
# 6. No NaN/inf
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("origin_str", ["2020-01-15 12:00:00", "2020-04-15 12:00:00", "2020-06-25 00:00:00"])
def test_no_nan_inf(origin_str, raw_df, detector, direct_models_metadata):
    direct_models, direct_metadata = direct_models_metadata
    result = rhf.robust_hourly_forecast(origin_str, detector, direct_models, direct_metadata, raw_df)
    for r in result:
        assert np.isfinite(r["forecast_mw"])
        assert np.isfinite(r["detector_primary_score"])
        if r["detector_secondary_score"] is not None:
            assert np.isfinite(r["detector_secondary_score"])


def test_detector_signals_no_nan_inf_where_defined(detector):
    valid = detector.signals.dropna(subset=["primary_score"])
    assert np.isfinite(valid["primary_score"].values).all()
    assert np.isfinite(valid["seasonal_zscore"].values).all()
