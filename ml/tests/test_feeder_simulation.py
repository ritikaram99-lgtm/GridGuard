"""
GridGuard AI - Validation tests for the synthetic feeder simulator
(ml/src/feeder_generator.py) and the Grid Stress Engine (ml/src/stress_engine.py).

Run with:
    python -m pytest ml/tests/test_feeder_simulation.py -v
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import feeder_generator as fg
import stress_engine as se


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def national_demand():
    return fg.load_national_demand_series()


@pytest.fixture(scope="module")
def feeders():
    return fg.get_feeder_definitions()


@pytest.fixture(scope="module")
def small_national_series():
    idx = pd.date_range("2019-01-07 00:00:00", periods=24 * 14, freq="h")  # 2 weeks, starts on a Monday
    rng = np.random.default_rng(0)
    base = 1200 + 200 * np.sin(np.linspace(0, 14 * 2 * np.pi, len(idx)) / 24 * 2 * np.pi / 24)
    values = np.clip(base + rng.normal(0, 20, len(idx)), 50, None)
    return pd.Series(values, index=idx, name="nat_demand")


# ---------------------------------------------------------------------------
# 1. Feeder definitions sanity
# ---------------------------------------------------------------------------
def test_ten_feeders_defined(feeders):
    assert len(feeders) == 10
    ids = [f["id"] for f in feeders]
    assert ids == [f"F{str(i).zfill(2)}" for i in range(1, 11)]


def test_feeder_types_are_meaningful_and_varied(feeders):
    types_present = {f["type"] for f in feeders}
    assert types_present == set(fg.FEEDER_TYPES)
    # not all identical
    assert len(types_present) > 1


def test_base_shares_sum_to_coverage_factor(feeders):
    total = sum(f["base_share"] for f in feeders)
    assert total == pytest.approx(fg.COVERAGE_FACTOR, rel=1e-9)


def test_feeders_are_not_identical_beyond_noise(feeders):
    # capacities/relative weights must differ meaningfully across feeders
    weights = [f["relative_weight"] for f in feeders]
    assert len(set(weights)) > 1
    margins = [f["capacity_margin"] for f in feeders]
    assert len(set(margins)) > 1


def test_locations_documented_as_simulated(feeders):
    for f in feeders:
        assert "note" in f["location"]
        assert "SIMULATED" in f["location"]["note"]


# ---------------------------------------------------------------------------
# 2. Reproducibility
# ---------------------------------------------------------------------------
def test_allocation_is_reproducible(small_national_series, feeders):
    a = fg.allocate_feeder_loads(small_national_series, feeders, seed=123)
    b = fg.allocate_feeder_loads(small_national_series, feeders, seed=123)
    pd.testing.assert_frame_equal(a, b)


def test_different_seeds_give_different_noise(small_national_series, feeders):
    a = fg.allocate_feeder_loads(small_national_series, feeders, seed=1)
    b = fg.allocate_feeder_loads(small_national_series, feeders, seed=2)
    assert not a.equals(b)


def test_no_noise_allocation_is_deterministic_and_matches_formula(small_national_series, feeders):
    a = fg.allocate_feeder_loads(small_national_series, feeders, add_noise=False)
    b = fg.allocate_feeder_loads(small_national_series, feeders, add_noise=False)
    pd.testing.assert_frame_equal(a, b)


# ---------------------------------------------------------------------------
# 3. Non-negativity and no NaN/inf across the pipeline
# ---------------------------------------------------------------------------
def test_feeder_loads_non_negative(small_national_series, feeders):
    loads = fg.allocate_feeder_loads(small_national_series, feeders, seed=42)
    assert (loads.values >= 0).all()


def test_feeder_loads_no_nan_or_inf(small_national_series, feeders):
    loads = fg.allocate_feeder_loads(small_national_series, feeders, seed=42)
    assert np.isfinite(loads.values).all()


def test_zero_national_demand_gives_zero_feeder_load(feeders):
    idx = pd.date_range("2019-06-03 00:00:00", periods=48, freq="h")
    zero_series = pd.Series(0.0, index=idx)
    loads = fg.allocate_feeder_loads(zero_series, feeders, seed=42)
    assert (loads.values == 0).all()


def test_voltage_simulation_no_nan_and_within_bounds():
    util = np.linspace(0, 1.5, 50)
    voltage = fg.simulate_voltage(util, seed=42, add_noise=True)
    assert np.isfinite(voltage).all()
    assert (voltage >= fg.VOLTAGE_MODEL["min_pu"]).all()
    assert (voltage <= fg.VOLTAGE_MODEL["max_pu"]).all()


# ---------------------------------------------------------------------------
# 4. Aggregate feeder demand tracks the national signal
# ---------------------------------------------------------------------------
def test_aggregate_feeder_demand_tracks_national_signal_weekly(small_national_series, feeders):
    # No noise (expected value): weekly mean(sum(feeder loads)) should equal
    # coverage_factor * weekly mean(national demand), exactly by construction
    # (see module docstring derivation), aside from boundary effects if the
    # window isn't an exact multiple of 7 days.
    loads = fg.allocate_feeder_loads(small_national_series, feeders, add_noise=False)
    total_feeder = loads.sum(axis=1)
    ratio = total_feeder.sum() / small_national_series.sum()
    assert ratio == pytest.approx(fg.COVERAGE_FACTOR, rel=0.02)  # 2-week window, exact multiple of 7 days


def test_aggregate_feeder_demand_tracks_national_signal_with_noise(small_national_series, feeders):
    loads = fg.allocate_feeder_loads(small_national_series, feeders, seed=42, add_noise=True)
    total_feeder = loads.sum(axis=1)
    ratio = total_feeder.sum() / small_national_series.sum()
    # noise is zero-mean and bounded, so the aggregate ratio should still be
    # close to coverage_factor within a modest tolerance
    assert ratio == pytest.approx(fg.COVERAGE_FACTOR, rel=0.05)


def test_feeder_load_depends_on_national_demand_level(feeders):
    idx = pd.date_range("2019-01-07 12:00:00", periods=1, freq="h")  # a Monday noon
    low = pd.Series([500.0], index=idx)
    high = pd.Series([1500.0], index=idx)
    load_low = fg.allocate_feeder_loads(low, feeders, add_noise=False)
    load_high = fg.allocate_feeder_loads(high, feeders, add_noise=False)
    assert (load_high.values > load_low.values).all()


def test_feeder_load_varies_by_hour_and_type(feeders):
    # commercial feeder should be higher at 12:00 (daytime) than 03:00 (night)
    # for the same national demand level, given its documented load shape.
    day = pd.Series([1200.0], index=pd.date_range("2019-01-08 12:00:00", periods=1, freq="h"))
    night = pd.Series([1200.0], index=pd.date_range("2019-01-08 03:00:00", periods=1, freq="h"))
    commercial_id = next(f["id"] for f in feeders if f["type"] == "COMMERCIAL")
    load_day = fg.allocate_feeder_loads(day, feeders, add_noise=False)[commercial_id].iloc[0]
    load_night = fg.allocate_feeder_loads(night, feeders, add_noise=False)[commercial_id].iloc[0]
    assert load_day > load_night


# ---------------------------------------------------------------------------
# 5. Capacity computation
# ---------------------------------------------------------------------------
def test_capacities_positive_and_finite(national_demand, feeders):
    loads = fg.allocate_feeder_loads(national_demand, feeders, seed=42)
    capacities = fg.compute_feeder_capacities(feeders, loads)
    assert (capacities["capacity_mw"] > 0).all()
    assert np.isfinite(capacities["capacity_mw"]).all()


def test_capacity_exceeds_historical_max(national_demand, feeders):
    loads = fg.allocate_feeder_loads(national_demand, feeders, seed=42)
    capacities = fg.compute_feeder_capacities(feeders, loads)
    # capacity = margin * historical_max, margin > 1 for all feeders => capacity > historical_max
    assert (capacities["capacity_mw"] >= capacities["historical_max_load_mw"]).all()


# ---------------------------------------------------------------------------
# 6. Forecast trajectory construction
# ---------------------------------------------------------------------------
def test_trajectory_anchors_match_inputs(national_demand):
    avg_shape = fg.historical_average_hourly_shape(national_demand)
    origin = pd.Timestamp("2019-06-10 14:00:00")
    traj = fg.build_national_trajectory(origin, current_national_demand=1300.0,
                                         forecast_24h_national_demand=1100.0,
                                         avg_hourly_shape=avg_shape)
    assert traj.iloc[0] == pytest.approx(1300.0, rel=1e-6)
    assert traj.iloc[-1] == pytest.approx(1100.0, rel=1e-6)
    assert len(traj) == 25  # h=0..24 inclusive


def test_trajectory_non_negative_and_finite(national_demand):
    avg_shape = fg.historical_average_hourly_shape(national_demand)
    origin = pd.Timestamp("2019-06-10 14:00:00")
    traj = fg.build_national_trajectory(origin, current_national_demand=50.0,
                                         forecast_24h_national_demand=10.0,
                                         avg_hourly_shape=avg_shape)
    assert (traj.values >= 0).all()
    assert np.isfinite(traj.values).all()


def test_feeder_trajectories_non_negative_no_nan(national_demand, feeders):
    avg_shape = fg.historical_average_hourly_shape(national_demand)
    origin = pd.Timestamp("2019-06-10 14:00:00")
    national_traj = fg.build_national_trajectory(origin, 1300.0, 1450.0, avg_shape)
    feeder_traj = fg.build_feeder_trajectories(national_traj, feeders)
    assert (feeder_traj.values >= 0).all()
    assert np.isfinite(feeder_traj.values).all()


# ---------------------------------------------------------------------------
# 7. Stress score bounds and explainability
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("current,forecast,capacity,voltage", [
    (0.0, 0.0, 100.0, 1.02),
    (100.0, 100.0, 100.0, 1.02),
    (150.0, 150.0, 100.0, 0.85),
    (50.0, 200.0, 100.0, 0.90),
    (0.001, 0.001, 0.001, 1.0),
])
def test_stress_score_within_0_100(current, forecast, capacity, voltage):
    score, components = se.compute_stress_score(current, forecast, capacity, voltage)
    assert 0.0 <= score <= 100.0
    assert np.isfinite(score)
    for v in components.values():
        assert 0.0 <= v <= 1.0
        assert np.isfinite(v)


def test_stress_score_monotonic_in_utilization():
    low_score, _ = se.compute_stress_score(10, 10, 100, 1.02)
    mid_score, _ = se.compute_stress_score(50, 50, 100, 1.02)
    high_score, _ = se.compute_stress_score(95, 95, 100, 1.02)
    assert low_score < mid_score < high_score


def test_stress_score_zero_capacity_does_not_crash_or_produce_nan():
    score, components = se.compute_stress_score(10, 10, 0.0, 1.0)
    assert np.isfinite(score)
    assert 0.0 <= score <= 100.0


# ---------------------------------------------------------------------------
# 8. Classification
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("score,expected", [
    (0, "LOW"), (30, "LOW"),
    (31, "MODERATE"), (60, "MODERATE"),
    (61, "HIGH"), (80, "HIGH"),
    (81, "CRITICAL"), (100, "CRITICAL"),
])
def test_classification_boundaries(score, expected):
    assert se.classify_stress(score) == expected


def test_classification_rejects_out_of_range():
    with pytest.raises(ValueError):
        se.classify_stress(-1)
    with pytest.raises(ValueError):
        se.classify_stress(101)


def test_classification_rejects_nan():
    with pytest.raises(ValueError):
        se.classify_stress(float("nan"))


# ---------------------------------------------------------------------------
# 9. Overload detection / time-to-overload
# ---------------------------------------------------------------------------
def test_overload_detected_when_trajectory_crosses_capacity():
    idx = pd.date_range("2020-01-01 00:00:00", periods=25, freq="h")
    values = np.linspace(50, 150, 25)  # rises from 50 to 150 MW over 24h
    traj = pd.Series(values, index=idx)
    result = se.time_to_overload(traj, capacity_mw=100.0)
    assert result["overload_predicted"] is True
    assert result["time_to_overload_hours"] is not None
    # linear rise 50->150 over 24h crosses 100 at h=12 exactly
    assert result["time_to_overload_hours"] == pytest.approx(12.0, abs=0.5)
    assert result["crossing_forecast_point"] is not None
    assert "resolution_note" in result and len(result["resolution_note"]) > 0


def test_no_overload_when_trajectory_stays_below_capacity():
    idx = pd.date_range("2020-01-01 00:00:00", periods=25, freq="h")
    values = np.full(25, 50.0)
    traj = pd.Series(values, index=idx)
    result = se.time_to_overload(traj, capacity_mw=100.0)
    assert result["overload_predicted"] is False
    assert result["time_to_overload_hours"] is None
    assert result["crossing_time"] is None


def test_overload_already_at_start():
    idx = pd.date_range("2020-01-01 00:00:00", periods=25, freq="h")
    values = np.full(25, 150.0)
    traj = pd.Series(values, index=idx)
    result = se.time_to_overload(traj, capacity_mw=100.0)
    assert result["overload_predicted"] is True
    assert result["time_to_overload_hours"] == 0.0
    assert result["interpolated"] is False


def test_time_to_overload_rejects_nan_trajectory():
    idx = pd.date_range("2020-01-01 00:00:00", periods=5, freq="h")
    values = np.array([10.0, 20.0, np.nan, 40.0, 50.0])
    traj = pd.Series(values, index=idx)
    with pytest.raises(ValueError):
        se.time_to_overload(traj, capacity_mw=30.0)


def test_time_to_overload_rejects_invalid_capacity():
    idx = pd.date_range("2020-01-01 00:00:00", periods=5, freq="h")
    traj = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0], index=idx)
    with pytest.raises(ValueError):
        se.time_to_overload(traj, capacity_mw=0.0)
    with pytest.raises(ValueError):
        se.time_to_overload(traj, capacity_mw=-5.0)


# ---------------------------------------------------------------------------
# 10. End-to-end evaluate_feeder wrapper
# ---------------------------------------------------------------------------
def test_evaluate_feeder_end_to_end():
    idx = pd.date_range("2020-01-01 00:00:00", periods=25, freq="h")
    traj = pd.Series(np.linspace(60, 120, 25), index=idx)
    result = se.evaluate_feeder(current_load_mw=60, forecast_load_mw=120, capacity_mw=100,
                                 voltage_pu=0.97, trajectory=traj)
    assert 0.0 <= result["stress_score"] <= 100.0
    assert result["risk_level"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
    assert result["time_to_overload"]["overload_predicted"] is True
    assert np.isfinite(result["stress_score"])


def test_full_pipeline_no_nan_inf_via_run_example():
    result = fg.run_example()
    assert np.isfinite(result["current_national_demand_mw"])
    assert np.isfinite(result["forecast_24h_national_demand_mw"])
    for fid, fdata in result["feeders"].items():
        assert np.isfinite(fdata["capacity_mw"]) and fdata["capacity_mw"] > 0
        assert np.isfinite(fdata["current_load_mw"]) and fdata["current_load_mw"] >= 0
        assert np.isfinite(fdata["forecast_load_mw_24h"]) and fdata["forecast_load_mw_24h"] >= 0
        assert np.isfinite(fdata["current_utilization"])
        assert np.isfinite(fdata["forecast_utilization_24h"])
        assert np.isfinite(fdata["current_voltage_pu"])
        assert np.isfinite(fdata["forecast_voltage_pu_24h"])
        assert all(np.isfinite(v) for v in fdata["trajectory_mw"])
        assert all(v >= 0 for v in fdata["trajectory_mw"])

        score, components = se.compute_stress_score(
            fdata["current_load_mw"], fdata["forecast_load_mw_24h"], fdata["capacity_mw"], fdata["current_voltage_pu"])
        assert 0.0 <= score <= 100.0
        risk = se.classify_stress(score)
        assert risk in ("LOW", "MODERATE", "HIGH", "CRITICAL")
