"""
GridGuard AI - Validation tests for the Action/Optimization Engine
(ml/src/action_engine.py), refreshed for the current regime-aware genuine
hourly forecasting pipeline.

Run with:
    python -m pytest ml/tests/test_action_engine.py -v
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import action_engine as ae
import stress_engine as se

CAPACITY = 100.0
START = pd.Timestamp("2020-01-01 00:00:00")


def traj_from_points(points, n_hours=24):
    hrs = [p[0] for p in points]
    vals = [p[1] for p in points]
    h = np.arange(n_hours + 1)
    v = np.interp(h, hrs, vals)
    idx = pd.date_range(START, periods=n_hours + 1, freq="h")
    return pd.Series(v, index=idx)


def make_scenario(points, feeder_id="TEST", feeder_type="TEST", capacity=CAPACITY):
    traj = traj_from_points(points)
    return ae.FeederScenario(feeder_id=feeder_id, feeder_type=feeder_type, capacity_mw=capacity, trajectory=traj)


TRAJ_SAFE = [(0, 45), (12, 60), (24, 55)]
TRAJ_SMALL_OVERLOAD = [(0, 90), (2, 108), (4, 90), (24, 85)]
TRAJ_LARGER_OVERLOAD = [(0, 95), (3, 130), (6, 95), (24, 90)]
TRAJ_INSUFFICIENT = [(0, 90), (2, 175), (4, 90), (24, 85)]
TRAJ_MULTIPLE_FEASIBLE = [(0, 92), (2, 109), (4, 92), (24, 88)]
TRAJ_DURATION_LIMITED = [(0, 140), (3, 140), (6, 102), (24, 102)]


# ---------------------------------------------------------------------------
# 1. No action for low stress
# ---------------------------------------------------------------------------
def test_no_action_for_safe_feeder():
    rec = ae.recommend_action(make_scenario(TRAJ_SAFE))
    assert rec["action_required"] is False
    assert rec["recommended_actions"] == []
    assert rec["total_reduction_mw"] == 0.0
    assert rec["overload_avoided"] is True


# ---------------------------------------------------------------------------
# 2. High-risk / overload scenarios
# ---------------------------------------------------------------------------
def test_overload_scenario_triggers_action():
    rec = ae.recommend_action(make_scenario(TRAJ_LARGER_OVERLOAD))
    assert rec["baseline_overload_predicted"] is True
    assert rec["action_required"] is True


def test_high_risk_without_overload_still_triggers_action():
    rec = ae.recommend_action(make_scenario([(0, 88), (24, 92)]))
    assert rec["baseline_overload_predicted"] is False
    assert rec["baseline_risk_level"] in ("HIGH", "CRITICAL")
    assert rec["action_required"] is True


# ---------------------------------------------------------------------------
# 3. EV-only, Battery-only, Industrial-only, combined interventions
# ---------------------------------------------------------------------------
def test_single_resource_sufficient_for_small_overload():
    rec = ae.recommend_action(make_scenario(TRAJ_SMALL_OVERLOAD))
    assert rec["overload_avoided"] is True
    assert len(rec["recommended_actions"]) == 1
    assert rec["recommended_actions"][0]["resource"] == "BATTERY"  # cheapest sufficient option


def test_combination_required_for_larger_overload():
    rec = ae.recommend_action(make_scenario(TRAJ_LARGER_OVERLOAD))
    assert rec["overload_avoided"] is True
    assert len(rec["recommended_actions"]) >= 2


def test_each_individual_resource_type_can_be_isolated():
    """Verify EV, BATTERY, and INDUSTRIAL can each individually resolve a
    scenario sized specifically within their own (and only their own)
    capacity, by directly evaluating single-resource candidates."""
    resources = ae.build_resources_for_capacity(CAPACITY)
    traj = traj_from_points(TRAJ_SMALL_OVERLOAD)
    for name in ["EV", "BATTERY", "INDUSTRIAL"]:
        candidate = {"label": name, "actions": [resources[name]]}
        evaluated = ae.evaluate_candidate(traj, CAPACITY, candidate)
        assert np.isfinite(evaluated["projected_stress_score"])
        assert evaluated["total_reduction_mw"] == pytest.approx(resources[name].mw)


# ---------------------------------------------------------------------------
# 4. Insufficient flexibility
# ---------------------------------------------------------------------------
def test_insufficient_flexibility_reported_honestly():
    rec = ae.recommend_action(make_scenario(TRAJ_INSUFFICIENT))
    assert rec["action_required"] is True
    assert rec["overload_avoided"] is False
    assert rec["remaining_overload_mw"] > 0
    assert rec["required_reduction_mw"] > rec["max_feasible_reduction_mw"]
    assert "insufficient" in rec["reason"].lower() or "cannot" in rec["reason"].lower()


def test_duration_limited_case_reduces_peak_but_does_not_avoid_overload():
    rec = ae.recommend_action(make_scenario(TRAJ_DURATION_LIMITED))
    assert rec["overload_avoided"] is False
    assert rec["projected_load_mw"] < rec["baseline_forecast_mw"]


# ---------------------------------------------------------------------------
# 5. Constraints respected
# ---------------------------------------------------------------------------
def test_resource_constraints_never_violated():
    resources = ae.build_resources_for_capacity(CAPACITY)
    assert resources["EV"].mw == pytest.approx(0.15 * CAPACITY)
    assert resources["EV"].duration_hours <= 4.0
    assert resources["BATTERY"].mw == pytest.approx(0.20 * CAPACITY)
    assert resources["BATTERY"].duration_hours <= 4.0
    assert resources["INDUSTRIAL"].mw == pytest.approx(0.25 * CAPACITY)
    assert resources["INDUSTRIAL"].duration_hours <= 6.0

    candidates = ae.generate_candidates(CAPACITY)
    assert len(candidates) == 7
    max_possible = sum(a.mw for a in resources.values())
    for c in candidates:
        assert sum(a.mw for a in c["actions"]) <= max_possible + 1e-9


# ---------------------------------------------------------------------------
# 6. Projected load/utilization correct (cross-checked against stress_engine directly)
# ---------------------------------------------------------------------------
def test_projected_metrics_match_stress_engine_directly():
    scenario = make_scenario(TRAJ_LARGER_OVERLOAD)
    rec = ae.recommend_action(scenario)
    resources = ae.build_resources_for_capacity(CAPACITY)
    actions = [resources[a["resource"]] for a in rec["recommended_actions"]]
    modified = ae.apply_actions_to_trajectory(scenario.trajectory, actions)
    expected_peak = float(modified.max())
    assert rec["projected_load_mw"] == pytest.approx(expected_peak, rel=1e-6)

    expected_tto = se.time_to_overload(modified, CAPACITY)
    assert rec["overload_avoided"] == (not expected_tto["overload_predicted"])


def test_projected_utilization_equals_projected_load_over_capacity():
    rec = ae.recommend_action(make_scenario(TRAJ_LARGER_OVERLOAD))
    assert rec["projected_utilization"] == pytest.approx(rec["projected_load_mw"] / rec["capacity_mw"])


# ---------------------------------------------------------------------------
# 7. No negative load
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("points", [TRAJ_SAFE, TRAJ_SMALL_OVERLOAD, TRAJ_LARGER_OVERLOAD,
                                      TRAJ_INSUFFICIENT, TRAJ_MULTIPLE_FEASIBLE, TRAJ_DURATION_LIMITED])
def test_action_never_produces_negative_load(points):
    traj = traj_from_points(points)
    candidates = ae.generate_candidates(CAPACITY)
    for c in candidates:
        modified = ae.apply_actions_to_trajectory(traj, c["actions"])
        assert (modified.values >= 0).all()


def test_action_never_increases_load():
    traj = traj_from_points(TRAJ_LARGER_OVERLOAD)
    candidates = ae.generate_candidates(CAPACITY)
    for c in candidates:
        modified = ae.apply_actions_to_trajectory(traj, c["actions"])
        assert (modified.values <= traj.values + 1e-9).all()


# ---------------------------------------------------------------------------
# 8. Deterministic results
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("points", [TRAJ_SAFE, TRAJ_SMALL_OVERLOAD, TRAJ_LARGER_OVERLOAD,
                                      TRAJ_INSUFFICIENT, TRAJ_MULTIPLE_FEASIBLE, TRAJ_DURATION_LIMITED])
def test_deterministic(points):
    scenario1 = make_scenario(points)
    scenario2 = make_scenario(points)
    rec1 = ae.recommend_action(scenario1)
    rec2 = ae.recommend_action(scenario2)
    assert rec1["action_required"] == rec2["action_required"]
    assert rec1["recommended_actions"] == rec2["recommended_actions"]
    assert rec1["projected_load_mw"] == pytest.approx(rec2["projected_load_mw"])
    assert rec1["overload_avoided"] == rec2["overload_avoided"]


def test_lower_disruption_solution_preferred_when_multiple_feasible():
    rec = ae.recommend_action(make_scenario(TRAJ_MULTIPLE_FEASIBLE))
    sufficient = [a for a in rec["alternatives"] if not a["overload_predicted"]]
    assert len(sufficient) > 1
    min_cost = min(a["total_disruption_cost"] for a in sufficient)
    assert rec["intervention_cost"] == pytest.approx(min_cost)


# ---------------------------------------------------------------------------
# Global sanity: no NaN/inf, bounded stress scores, required output fields present
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("points", [TRAJ_SAFE, TRAJ_SMALL_OVERLOAD, TRAJ_LARGER_OVERLOAD,
                                      TRAJ_INSUFFICIENT, TRAJ_MULTIPLE_FEASIBLE, TRAJ_DURATION_LIMITED])
def test_no_nan_inf_and_required_fields_present(points):
    rec = ae.recommend_action(make_scenario(points))
    required_fields = ["feeder_id", "target_timestamp", "baseline_forecast_mw", "capacity_mw",
                        "baseline_utilization", "baseline_risk_level", "recommended_actions",
                        "total_reduction_mw", "projected_load_mw", "projected_utilization",
                        "projected_risk_level", "overload_avoided", "intervention_cost", "reason"]
    for field in required_fields:
        assert field in rec

    numeric_fields = ["baseline_forecast_mw", "capacity_mw", "baseline_utilization", "total_reduction_mw",
                       "projected_load_mw", "projected_utilization", "intervention_cost"]
    for field in numeric_fields:
        assert np.isfinite(rec[field])
    assert rec["projected_risk_level"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")


def test_evaluate_trajectory_rejects_negative_load():
    idx = pd.date_range(START, periods=3, freq="h")
    bad_traj = pd.Series([10.0, -5.0, 20.0], index=idx)
    with pytest.raises(AssertionError):
        ae.evaluate_trajectory(bad_traj, CAPACITY)
