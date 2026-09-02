"""
GridGuard AI - Validation tests for the Prevention/Decision Engine
(ml/src/prevention_engine.py).

Run with:
    python -m pytest ml/tests/test_prevention_engine.py -v
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import prevention_engine as pe
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


TRAJ_SAFE = traj_from_points([(0, 45), (12, 60), (24, 55)])
TRAJ_SMALL_OVERLOAD = traj_from_points([(0, 90), (2, 108), (4, 90), (24, 85)])
TRAJ_MULTIPLE_FEASIBLE = traj_from_points([(0, 92), (2, 109), (4, 92), (24, 88)])
TRAJ_LARGER_OVERLOAD = traj_from_points([(0, 95), (3, 130), (6, 95), (24, 90)])
TRAJ_INSUFFICIENT = traj_from_points([(0, 90), (2, 175), (4, 90), (24, 85)])
TRAJ_DURATION_LIMITED = traj_from_points([(0, 140), (3, 140), (6, 102), (24, 102)])
TRAJ_EQUAL_COST_TIE = traj_from_points([(0, 90), (2, 109), (4, 90), (24, 88)])  # small enough EV alone (cost 1.0) is NOT cheaper than Battery (0.5); used for cost/MW ordering check


# ---------------------------------------------------------------------------
# 1. Safe feeder -> NO_ACTION_REQUIRED
# ---------------------------------------------------------------------------
def test_safe_feeder_no_action_required():
    rec = pe.recommend_prevention("F01", "TEST", CAPACITY, TRAJ_SAFE)
    assert rec["prevention_status"] == "NO_ACTION_REQUIRED"
    assert rec["recommended_actions"] == []
    assert rec["total_reduction_mw"] == 0.0
    assert rec["overload_avoided"] is True
    assert rec["candidates_evaluated"] == 0


# ---------------------------------------------------------------------------
# 2. Single intervention successfully prevents overload
# ---------------------------------------------------------------------------
def test_single_intervention_prevents_overload():
    rec = pe.recommend_prevention("F01", "TEST", CAPACITY, TRAJ_SMALL_OVERLOAD)
    assert rec["prevention_status"] == "PREVENTED"
    assert rec["overload_avoided"] is True
    assert len(rec["recommended_actions"]) == 1
    assert rec["recommended_actions"][0]["resource"] == "BATTERY"  # cheapest sufficient


# ---------------------------------------------------------------------------
# 3. Multiple candidates -> cheapest successful option selected
# ---------------------------------------------------------------------------
def test_cheapest_successful_candidate_selected():
    rec = pe.recommend_prevention("F01", "TEST", CAPACITY, TRAJ_MULTIPLE_FEASIBLE)
    resolved_alternatives = [a for a in rec["alternatives"] if a["resolved"]]
    assert len(resolved_alternatives) > 1  # multiple feasible solutions exist
    min_cost = min(a["cost"] for a in resolved_alternatives)
    assert rec["intervention_cost"] == pytest.approx(min_cost)
    assert rec["prevention_status"] == "PREVENTED"


# ---------------------------------------------------------------------------
# 4. Equal-cost candidates -> lower MW selected
# ---------------------------------------------------------------------------
def test_equal_cost_candidates_prefer_lower_mw():
    """Directly test the ranking key's tie-breaking behavior: among
    synthetic candidates with equal cost, the one with lower total_reduction_mw
    must rank first."""
    cand_a = {"label": "A", "actions": [], "n_resources": 1, "cost": 1.0}
    cand_b = {"label": "B", "actions": [], "n_resources": 1, "cost": 1.0}
    result_a = {"overload_after": False, "final_risk": "LOW", "total_reduction_mw": 20.0}
    result_b = {"overload_after": False, "final_risk": "LOW", "total_reduction_mw": 10.0}
    key_a = pe._ranking_key(cand_a, result_a, overload_before=True)
    key_b = pe._ranking_key(cand_b, result_b, overload_before=True)
    assert key_b < key_a  # B (lower MW) ranks first


def test_fewer_interventions_preferred_when_otherwise_equivalent():
    cand_single = {"label": "BATTERY", "actions": [], "n_resources": 1, "cost": 1.0}
    cand_combo = {"label": "BATTERY+EV", "actions": [], "n_resources": 2, "cost": 1.0}
    result_same = {"overload_after": False, "final_risk": "LOW", "total_reduction_mw": 20.0}
    key_single = pe._ranking_key(cand_single, result_same, overload_before=True)
    key_combo = pe._ranking_key(cand_combo, result_same, overload_before=True)
    assert key_single < key_combo


# ---------------------------------------------------------------------------
# 5. Combination intervention selected when required
# ---------------------------------------------------------------------------
def test_combination_selected_when_required():
    rec = pe.recommend_prevention("F01", "TEST", CAPACITY, TRAJ_LARGER_OVERLOAD)
    assert rec["prevention_status"] == "PREVENTED"
    assert len(rec["recommended_actions"]) >= 2


# ---------------------------------------------------------------------------
# 6. Intervention reduces but does not prevent / 7. Insufficient flexibility
# ---------------------------------------------------------------------------
def test_insufficient_flexibility_reported_honestly():
    rec = pe.recommend_prevention("F01", "TEST", CAPACITY, TRAJ_INSUFFICIENT)
    assert rec["prevention_status"] == "INSUFFICIENT_FLEXIBILITY"
    assert rec["overload_avoided"] is False
    assert rec["max_feasible_reduction_mw"] < rec["required_reduction_mw"]
    assert rec["total_reduction_mw"] > 0  # still applies best-effort


# ---------------------------------------------------------------------------
# 8. Duration-limited case
# ---------------------------------------------------------------------------
def test_duration_limited_case():
    rec = pe.recommend_prevention("F01", "TEST", CAPACITY, TRAJ_DURATION_LIMITED)
    assert rec["prevention_status"] == "DURATION_LIMITED"
    assert rec["overload_avoided"] is False
    assert rec["max_feasible_reduction_mw"] >= rec["required_reduction_mw"] - 1e-6
    assert rec["projected_load_mw"] < rec["baseline_load_mw"] or rec["total_reduction_mw"] > 0


# ---------------------------------------------------------------------------
# 9. No false PREVENTED status
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("traj", [TRAJ_INSUFFICIENT, TRAJ_DURATION_LIMITED])
def test_never_falsely_claims_prevented(traj):
    rec = pe.recommend_prevention("F01", "TEST", CAPACITY, traj)
    assert rec["prevention_status"] != "PREVENTED"
    assert rec["overload_avoided"] is False
    # cross-check: the recalculated overload_after must actually be True when not prevented and baseline was overloaded
    if rec["overload_before"]:
        assert rec["overload_after"] is True


def test_prevented_status_only_when_stress_engine_confirms_no_overload():
    rec = pe.recommend_prevention("F01", "TEST", CAPACITY, TRAJ_SMALL_OVERLOAD)
    if rec["prevention_status"] == "PREVENTED":
        modified_check = ae.apply_actions_to_trajectory(
            TRAJ_SMALL_OVERLOAD,
            [ae.Action(a["resource"], a["applied_mw"], a["applied_duration_hours"], a["disruption_cost"])
             for a in rec["recommended_actions"]],
        )
        tto = se.time_to_overload(modified_check, CAPACITY)
        assert tto["overload_predicted"] is False


# ---------------------------------------------------------------------------
# 10. Stress/risk values come from Simulation/Stress Engine
# ---------------------------------------------------------------------------
def test_projected_values_match_stress_engine_directly():
    rec = pe.recommend_prevention("F01", "TEST", CAPACITY, TRAJ_LARGER_OVERLOAD)
    actions = [ae.Action(a["resource"], a["applied_mw"], a["applied_duration_hours"], a["disruption_cost"])
               for a in rec["recommended_actions"]]
    modified = ae.apply_actions_to_trajectory(TRAJ_LARGER_OVERLOAD, actions)
    expected = ae.evaluate_trajectory(modified, CAPACITY)
    assert rec["projected_stress_score"] == pytest.approx(expected["stress_score"], rel=1e-6)
    assert rec["projected_risk"] == expected["risk_level"]
    assert rec["overload_after"] == expected["overload_predicted"]


def test_baseline_values_match_stress_engine_directly():
    rec = pe.recommend_prevention("F01", "TEST", CAPACITY, TRAJ_SAFE)
    expected = ae.evaluate_trajectory(TRAJ_SAFE, CAPACITY)
    assert rec["baseline_stress_score"] == pytest.approx(expected["stress_score"], rel=1e-6)
    assert rec["baseline_risk"] == expected["risk_level"]


# ---------------------------------------------------------------------------
# 11. Deterministic results
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("traj", [TRAJ_SAFE, TRAJ_SMALL_OVERLOAD, TRAJ_LARGER_OVERLOAD,
                                    TRAJ_INSUFFICIENT, TRAJ_DURATION_LIMITED])
def test_deterministic(traj):
    r1 = pe.recommend_prevention("F01", "TEST", CAPACITY, traj)
    r2 = pe.recommend_prevention("F01", "TEST", CAPACITY, traj)
    assert r1["prevention_status"] == r2["prevention_status"]
    assert r1["recommended_actions"] == r2["recommended_actions"]
    assert r1["projected_stress_score"] == pytest.approx(r2["projected_stress_score"])


# ---------------------------------------------------------------------------
# 12. Invalid inputs handled correctly
# ---------------------------------------------------------------------------
def test_invalid_capacity_rejected():
    with pytest.raises(AssertionError):
        pe.recommend_prevention("F01", "TEST", -5.0, TRAJ_SAFE)


def test_negative_trajectory_rejected():
    idx = pd.date_range(START, periods=5, freq="h")
    bad = pd.Series([10, -5, 20, 30, 40], index=idx)
    with pytest.raises(AssertionError):
        pe.recommend_prevention("F01", "TEST", CAPACITY, bad)


def test_nan_trajectory_rejected():
    idx = pd.date_range(START, periods=5, freq="h")
    bad = pd.Series([10, np.nan, 20, 30, 40], index=idx)
    with pytest.raises(AssertionError):
        pe.recommend_prevention("F01", "TEST", CAPACITY, bad)


# ---------------------------------------------------------------------------
# Global sanity across all controlled trajectories
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("traj", [TRAJ_SAFE, TRAJ_SMALL_OVERLOAD, TRAJ_MULTIPLE_FEASIBLE, TRAJ_LARGER_OVERLOAD,
                                    TRAJ_INSUFFICIENT, TRAJ_DURATION_LIMITED])
def test_output_schema_and_bounds(traj):
    rec = pe.recommend_prevention("F01", "TEST", CAPACITY, traj)
    assert rec["prevention_status"] in pe.PREVENTION_STATUSES
    required_fields = ["feeder_id", "target_timestamp", "baseline_load_mw", "baseline_stress_score",
                        "baseline_risk", "baseline_time_to_overload", "recommended_actions",
                        "total_reduction_mw", "projected_load_mw", "projected_stress_score", "projected_risk",
                        "projected_time_to_overload", "overload_before", "overload_after", "overload_avoided",
                        "prevention_status", "intervention_cost", "reason"]
    for f in required_fields:
        assert f in rec
    assert 0.0 <= rec["projected_stress_score"] <= 100.0
    assert rec["projected_risk"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
    assert rec["projected_load_mw"] >= 0
