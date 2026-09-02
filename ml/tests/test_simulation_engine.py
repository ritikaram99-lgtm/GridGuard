"""
GridGuard AI - Validation tests for the What-If Scenario Simulation Engine
(ml/src/simulation_engine.py).

Run with:
    python -m pytest ml/tests/test_simulation_engine.py -v
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import simulation_engine as sim
import action_engine as ae
import stress_engine as se

CAPACITY = 100.0
START = pd.Timestamp("2020-01-15 00:00:00")


def make_baseline(peak=90.0, feeder_type="EV_HEAVY"):
    idx = pd.date_range(START, periods=25, freq="h")
    hours = np.arange(25)
    # a smooth diurnal-ish shape, peak roughly mid-trajectory, always positive
    values = 0.6 * peak + 0.4 * peak * np.sin(np.pi * hours / 24) ** 2
    values[np.argmax(values)] = peak  # ensure exact requested peak is hit
    return pd.Series(values, index=idx, name="baseline")


# ---------------------------------------------------------------------------
# 1. Baseline scenario (no adjustments) produces unchanged baseline
# ---------------------------------------------------------------------------
def test_zero_scenario_params_leave_trajectory_unchanged():
    baseline = make_baseline()
    result = sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY, baseline_trajectory=baseline,
                                     ambient_temperature_c=None, ev_surge_pct=0.0, solar_drop_pct=0.0)
    assert result["scenario_peak_load_mw"] == pytest.approx(result["baseline_peak_load_mw"])
    assert result["scenario_stress_score"] == pytest.approx(result["baseline_stress_score"])
    assert result["scenario_risk"] == result["baseline_risk"]
    assert result["load_change_mw"]["total"] == pytest.approx(0.0, abs=1e-6)


def test_reference_temperature_produces_zero_temperature_effect():
    baseline = make_baseline()
    result = sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY, baseline_trajectory=baseline,
                                     ambient_temperature_c=27.0)  # exactly the documented reference temp
    assert result["load_change_mw"]["temperature"] == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 2. Temperature changes affect scenario output
# ---------------------------------------------------------------------------
def test_higher_temperature_increases_load():
    baseline = make_baseline()
    cool = sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY, baseline_trajectory=baseline, ambient_temperature_c=27.0)
    hot = sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY, baseline_trajectory=baseline, ambient_temperature_c=37.0)
    assert hot["scenario_peak_load_mw"] > cool["scenario_peak_load_mw"]
    assert hot["load_change_mw"]["temperature"] > 0


def test_lower_temperature_decreases_load():
    baseline = make_baseline()
    cool = sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY, baseline_trajectory=baseline, ambient_temperature_c=17.0)
    assert cool["load_change_mw"]["temperature"] < 0
    assert cool["scenario_peak_load_mw"] < cool["baseline_peak_load_mw"]


# ---------------------------------------------------------------------------
# 3. EV surge changes scenario output
# ---------------------------------------------------------------------------
def test_ev_surge_increases_load_for_ev_heavy_feeder():
    baseline = make_baseline()
    no_surge = sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY, baseline_trajectory=baseline, ev_surge_pct=0.0)
    surge = sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY, baseline_trajectory=baseline, ev_surge_pct=50.0)
    assert surge["scenario_peak_load_mw"] > no_surge["scenario_peak_load_mw"]
    assert surge["load_change_mw"]["ev_surge"] > 0


def test_ev_surge_has_no_effect_on_industrial_feeder():
    baseline = make_baseline()
    result = sim.simulate_scenario("F01", "INDUSTRIAL", CAPACITY, baseline_trajectory=baseline, ev_surge_pct=50.0)
    assert result["load_change_mw"]["ev_surge"] == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 4. Solar drop changes scenario output
# ---------------------------------------------------------------------------
def test_solar_drop_increases_daytime_load():
    idx = pd.date_range(pd.Timestamp("2020-01-15 00:00:00"), periods=25, freq="h")
    flat = pd.Series(np.full(25, 70.0), index=idx)
    noon = pd.Timestamp("2020-01-15 12:00:00")
    no_drop = sim.simulate_scenario("F01", "MIXED", CAPACITY, baseline_trajectory=flat, target_timestamp=noon, solar_drop_pct=0.0)
    drop = sim.simulate_scenario("F01", "MIXED", CAPACITY, baseline_trajectory=flat, target_timestamp=noon, solar_drop_pct=80.0)
    assert drop["scenario_load_mw_at_target"] > no_drop["scenario_load_mw_at_target"]
    assert drop["load_change_mw"]["solar_drop"] > 0


def test_solar_drop_has_no_effect_at_midnight():
    idx = pd.date_range(pd.Timestamp("2020-01-15 00:00:00"), periods=25, freq="h")
    flat = pd.Series(np.full(25, 70.0), index=idx)
    midnight = pd.Timestamp("2020-01-15 00:00:00")
    result = sim.simulate_scenario("F01", "MIXED", CAPACITY, baseline_trajectory=flat, target_timestamp=midnight, solar_drop_pct=80.0)
    assert result["load_change_mw"]["solar_drop"] == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 5. Combined scenario
# ---------------------------------------------------------------------------
def test_combined_scenario_sums_individual_effects_exactly():
    baseline = make_baseline()
    result = sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY, baseline_trajectory=baseline,
                                     ambient_temperature_c=35.0, ev_surge_pct=25.0, solar_drop_pct=40.0)
    lc = result["load_change_mw"]
    assert lc["total"] == pytest.approx(lc["temperature"] + lc["ev_surge"] + lc["solar_drop"], abs=1e-6)


# ---------------------------------------------------------------------------
# 6. Intervention reduces load
# ---------------------------------------------------------------------------
def test_intervention_reduces_load():
    baseline = make_baseline(peak=120.0)
    result = sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY, baseline_trajectory=baseline,
                                     proposed_actions=[{"resource": "BATTERY", "mw": 15.0, "duration_hours": 3.0}])
    assert result["intervention_applied"] is True
    assert result["final_peak_load_mw"] <= result["scenario_peak_load_mw"]
    assert result["total_reduction_mw"] > 0


# ---------------------------------------------------------------------------
# 7. Scenario + intervention combined pipeline
# ---------------------------------------------------------------------------
def test_scenario_plus_intervention_full_pipeline():
    baseline = make_baseline(peak=90.0)
    result = sim.simulate_scenario(
        "F01", "EV_HEAVY", CAPACITY, baseline_trajectory=baseline,
        ambient_temperature_c=36.0, ev_surge_pct=40.0, solar_drop_pct=30.0,
        proposed_actions=[{"resource": "BATTERY", "mw": 20.0, "duration_hours": 3.0},
                            {"resource": "INDUSTRIAL", "mw": 25.0, "duration_hours": 6.0}],
    )
    # ordering: baseline <= scenario (adverse scenario should raise or hold load), final <= scenario (intervention reduces)
    assert result["scenario_peak_load_mw"] >= result["baseline_peak_load_mw"] - 1e-6
    assert result["final_peak_load_mw"] <= result["scenario_peak_load_mw"] + 1e-6
    assert result["feasibility_status"] in ("feasible", "partially_feasible")


# ---------------------------------------------------------------------------
# 8. Stress is recalculated through the real Stress Engine
# ---------------------------------------------------------------------------
def test_stress_scores_match_stress_engine_directly():
    baseline = make_baseline(peak=110.0)
    result = sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY, baseline_trajectory=baseline,
                                     ambient_temperature_c=32.0)
    scenario_eval = ae.evaluate_trajectory(
        sim.apply_scenario_adjustments(baseline, CAPACITY, "EV_HEAVY", ambient_temperature_c=32.0)["scenario_trajectory"],
        CAPACITY,
    )
    assert result["scenario_stress_score"] == pytest.approx(scenario_eval["stress_score"])
    assert result["scenario_risk"] == scenario_eval["risk_level"]
    assert result["scenario_risk"] == se.classify_stress(result["scenario_stress_score"])


# ---------------------------------------------------------------------------
# 9. Overload status is correct
# ---------------------------------------------------------------------------
def test_overload_status_consistent_with_time_to_overload():
    baseline = make_baseline(peak=150.0)  # deliberately well over capacity
    result = sim.simulate_scenario("F01", "INDUSTRIAL", CAPACITY, baseline_trajectory=baseline)
    assert result["overload_before"] is True
    assert (result["baseline_time_to_overload"] is not None) == result["overload_before"]


def test_overload_avoided_only_when_intervention_actually_resolves_it():
    baseline = make_baseline(peak=108.0)
    result = sim.simulate_scenario(
        "F01", "MIXED", CAPACITY, baseline_trajectory=baseline,
        proposed_actions=[{"resource": "BATTERY", "mw": 20.0, "duration_hours": 4.0},
                            {"resource": "INDUSTRIAL", "mw": 25.0, "duration_hours": 6.0},
                            {"resource": "EV", "mw": 15.0, "duration_hours": 4.0}],
    )
    if result["overload_after_scenario"] and not result["overload_after"]:
        assert result["overload_avoided"] is True
    else:
        assert result["overload_avoided"] is False


# ---------------------------------------------------------------------------
# 10. No negative load
# ---------------------------------------------------------------------------
def test_extreme_negative_temperature_never_produces_negative_load():
    baseline = make_baseline(peak=50.0)
    result = sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY, baseline_trajectory=baseline,
                                     ambient_temperature_c=-50.0, ev_surge_pct=-90.0)
    scenario_traj = sim.apply_scenario_adjustments(baseline, CAPACITY, "EV_HEAVY",
                                                      ambient_temperature_c=-50.0, ev_surge_pct=-90.0)["scenario_trajectory"]
    assert (scenario_traj.values >= 0).all()


def test_intervention_never_produces_negative_load():
    baseline = make_baseline(peak=30.0)
    result = sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY, baseline_trajectory=baseline,
                                     proposed_actions=[{"resource": "INDUSTRIAL", "mw": 25.0, "duration_hours": 6.0}])
    assert result["final_peak_load_mw"] >= 0


# ---------------------------------------------------------------------------
# 11. Deterministic results
# ---------------------------------------------------------------------------
def test_deterministic():
    baseline = make_baseline(peak=100.0)
    kwargs = dict(feeder_id="F01", feeder_type="EV_HEAVY", capacity_mw=CAPACITY, baseline_trajectory=baseline,
                  ambient_temperature_c=33.0, ev_surge_pct=20.0, solar_drop_pct=25.0,
                  proposed_actions=[{"resource": "BATTERY", "mw": 15.0, "duration_hours": 3.0}])
    r1 = sim.simulate_scenario(**kwargs)
    r2 = sim.simulate_scenario(**kwargs)
    assert r1["final_peak_load_mw"] == pytest.approx(r2["final_peak_load_mw"])
    assert r1["final_risk"] == r2["final_risk"]
    assert r1["actions_applied"] == r2["actions_applied"]


# ---------------------------------------------------------------------------
# 12. Invalid inputs rejected
# ---------------------------------------------------------------------------
def test_invalid_capacity_rejected():
    baseline = make_baseline()
    with pytest.raises(AssertionError):
        sim.simulate_scenario("F01", "EV_HEAVY", -10.0, baseline_trajectory=baseline)


def test_nan_temperature_rejected():
    baseline = make_baseline()
    with pytest.raises(ValueError):
        sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY, baseline_trajectory=baseline,
                                ambient_temperature_c=float("nan"))


def test_negative_trajectory_rejected():
    idx = pd.date_range(START, periods=25, freq="h")
    bad = pd.Series(np.concatenate([[10], np.full(24, -5.0)]), index=idx)
    with pytest.raises(AssertionError):
        sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY, baseline_trajectory=bad)


def test_missing_baseline_input_rejected():
    with pytest.raises(AssertionError):
        sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY)  # neither trajectory nor scalar baseline given


def test_unknown_resource_in_intervention_is_infeasible():
    baseline = make_baseline(peak=120.0)
    result = sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY, baseline_trajectory=baseline,
                                     proposed_actions=[{"resource": "SOLAR_PANEL", "mw": 10.0}])
    assert result["feasibility_status"] == "infeasible"
    assert result["total_reduction_mw"] == 0.0


def test_action_exceeding_resource_limit_is_partially_feasible():
    baseline = make_baseline(peak=120.0)
    result = sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY, baseline_trajectory=baseline,
                                     proposed_actions=[{"resource": "EV", "mw": 500.0, "duration_hours": 100.0}])
    assert result["feasibility_status"] == "partially_feasible"
    applied = result["actions_applied"][0]
    assert applied["applied_mw"] == pytest.approx(0.15 * CAPACITY)  # clipped to EV's max


# ---------------------------------------------------------------------------
# Global sanity: no NaN/inf, bounded stress scores across representative cases
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("temp,ev,solar", [(None, 0, 0), (40, 0, 0), (0, 60, 0), (0, 0, 90), (38, 45, 70)])
def test_no_nan_inf_bounded_stress(temp, ev, solar):
    baseline = make_baseline(peak=95.0)
    result = sim.simulate_scenario("F01", "EV_HEAVY", CAPACITY, baseline_trajectory=baseline,
                                     ambient_temperature_c=temp, ev_surge_pct=ev, solar_drop_pct=solar)
    assert np.isfinite(result["scenario_stress_score"])
    assert 0.0 <= result["scenario_stress_score"] <= 100.0
    assert result["scenario_risk"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
