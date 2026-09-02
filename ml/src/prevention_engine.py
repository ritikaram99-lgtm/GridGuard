"""
GridGuard AI - Prevention / Decision Engine.

*** THIS IS A DECISION-SUPPORT SIMULATION, NOT REAL GRID CONTROL, AND NOT
ANOTHER ML MODEL. *** It answers: "which feasible intervention should
GridGuard recommend to prevent or reduce the predicted grid risk?" by
ORCHESTRATING the existing Action Engine (candidate generation, resource
limits) and the existing Simulation Engine (before/after verification via
the existing, unmodified Stress Engine) -- it does not recreate forecasting,
stress calculations, utilization calculations, risk calculations, or
intervention constraints anywhere in this file.

    Stressed feeder
        v
    Action Engine       (ml/src/action_engine.py, unmodified)
        v               -- candidate interventions (resource limits, costs)
    Simulation Engine    (ml/src/simulation_engine.py, unmodified)
        v               -- applies each candidate, re-runs the Stress Engine
    Evaluate BEFORE vs AFTER
        v
    Rank feasible candidates (deterministic, documented)
        v
    Best recommendation
        v
    Prevention result

*** ALL EV/BATTERY/INDUSTRIAL RESOURCE ASSUMPTIONS REMAIN SYNTHETIC *** --
inherited unmodified from action_engine.py's RESOURCE_ASSUMPTIONS. Never
present these as real Panama grid resources.

Does NOT modify: any trained model, the feature pipeline, regime_detector.py,
robust_hourly_forecast.py, feeder_generator.py, stress_engine.py,
rolling_integration.py, action_engine.py, or simulation_engine.py.
"""
import os
import sys
from itertools import combinations

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import action_engine as ae        # existing, unmodified -- resource limits, candidate building blocks
import simulation_engine as sim   # existing, unmodified -- applies interventions, re-runs the Stress Engine

# Same non-overload safety-margin target already established and used in
# action_engine.py, reused here (not redefined) for the "required reduction"
# calculation used only to classify WHY a candidate failed (magnitude vs.
# duration limited) -- this is decision-support bookkeeping over already-
# computed Stress Engine outputs, not a recreation of the stress formula.
NON_OVERLOAD_TARGET_UTILIZATION = ae.NON_OVERLOAD_TARGET_UTILIZATION

PREVENTION_STATUSES = {
    "NO_ACTION_REQUIRED", "PREVENTED", "REDUCED_NOT_PREVENTED",
    "INSUFFICIENT_FLEXIBILITY", "DURATION_LIMITED",
}


# ---------------------------------------------------------------------------
# 1. Candidate generation -- delegates entirely to action_engine.py's
#    existing resource-limit definitions. Adds only a "NO_ACTION" candidate
#    label for uniform handling (no new limits/costs invented here).
# ---------------------------------------------------------------------------
def generate_candidate_interventions(capacity_mw: float) -> list:
    resources = ae.build_resources_for_capacity(capacity_mw)  # existing, unmodified
    names = list(resources.keys())
    candidates = [{"label": "NO_ACTION", "actions": [], "n_resources": 0, "cost": 0.0}]
    for r in range(1, len(names) + 1):
        for combo in combinations(names, r):
            actions = [{"resource": n, "mw": resources[n].mw, "duration_hours": resources[n].duration_hours}
                       for n in combo]
            cost = sum(resources[n].disruption_cost for n in combo)
            candidates.append({"label": "+".join(combo), "actions": actions, "n_resources": len(combo), "cost": cost})
    return candidates


# ---------------------------------------------------------------------------
# 2. Verification -- delegates entirely to simulation_engine.py's existing
#    simulate_scenario (no scenario adjustments applied here -- only the
#    proposed intervention), which itself calls the existing, unmodified
#    Stress Engine for every before/after metric.
# ---------------------------------------------------------------------------
def verify_candidate(feeder_id: str, feeder_type: str, capacity_mw: float, trajectory: pd.Series,
                      target_timestamp, candidate: dict) -> dict:
    return sim.simulate_scenario(
        feeder_id=feeder_id, feeder_type=feeder_type, capacity_mw=capacity_mw,
        baseline_trajectory=trajectory, target_timestamp=target_timestamp,
        proposed_actions=candidate["actions"] if candidate["actions"] else None,
    )


def _resolves(verified: dict, overload_before: bool) -> bool:
    if overload_before:
        return bool(verified["overload_after"] is False)
    return verified["final_risk"] in ("LOW", "MODERATE")


def _ranking_key(candidate: dict, verified: dict, overload_before: bool):
    """
    Deterministic priority (per task spec):
      1. Successfully resolves the risk
      2. Lowest intervention cost
      3. Lowest total MW deployed
      4. Fewer simultaneous interventions
    """
    return (
        0 if _resolves(verified, overload_before) else 1,
        candidate["cost"],
        verified["total_reduction_mw"],
        candidate["n_resources"],
    )


# ---------------------------------------------------------------------------
# 3. Top-level orchestrator
# ---------------------------------------------------------------------------
def recommend_prevention(feeder_id: str, feeder_type: str, capacity_mw: float,
                          trajectory: pd.Series, target_timestamp=None) -> dict:
    """
    Orchestrates Action Engine candidate generation + Simulation Engine
    verification to select the best feasible intervention, or reports
    honestly when none fully resolves the predicted risk.
    """
    assert capacity_mw > 0 and np.isfinite(capacity_mw), "capacity_mw must be positive and finite"
    assert np.isfinite(trajectory.values).all(), "Trajectory contains NaN/inf"
    assert (trajectory.values >= 0).all(), "Trajectory contains negative load"

    # Baseline, via the existing Simulation Engine with no action and no scenario effect.
    baseline_result = sim.simulate_scenario(
        feeder_id=feeder_id, feeder_type=feeder_type, capacity_mw=capacity_mw,
        baseline_trajectory=trajectory, target_timestamp=target_timestamp,
    )
    overload_before = baseline_result["overload_before"]
    baseline_risk = baseline_result["baseline_risk"]
    target_ts = baseline_result["target_timestamp"]

    base_output = {
        "feeder_id": feeder_id,
        "target_timestamp": target_ts,
        "baseline_load_mw": baseline_result["baseline_load_mw_at_target"],
        "baseline_stress_score": baseline_result["baseline_stress_score"],
        "baseline_risk": baseline_risk,
        "baseline_time_to_overload": baseline_result["baseline_time_to_overload"],
        "overload_before": overload_before,
    }

    is_safe = (not overload_before) and baseline_risk in ("LOW", "MODERATE")
    if is_safe:
        base_output.update({
            "recommended_actions": [],
            "total_reduction_mw": 0.0,
            "projected_load_mw": base_output["baseline_load_mw"],
            "projected_stress_score": base_output["baseline_stress_score"],
            "projected_risk": baseline_risk,
            "projected_time_to_overload": base_output["baseline_time_to_overload"],
            "overload_after": overload_before,
            "overload_avoided": not overload_before,
            "prevention_status": "NO_ACTION_REQUIRED",
            "intervention_cost": 0.0,
            "reason": (f"Feeder {feeder_id} is not predicted to overload and baseline risk ({baseline_risk}) "
                        f"is LOW/MODERATE -- no intervention recommended."),
        })
        base_output["candidates_evaluated"] = 0
        base_output["alternatives"] = []
        return base_output

    # 1-2. Generate candidates (Action Engine) and verify each (Simulation Engine)
    candidates = generate_candidate_interventions(capacity_mw)
    non_null_candidates = [c for c in candidates if c["label"] != "NO_ACTION"]
    verified = [
        {"candidate": c, "result": verify_candidate(feeder_id, feeder_type, capacity_mw, trajectory, target_ts, c)}
        for c in non_null_candidates
    ]
    for v in verified:
        r = v["result"]
        assert np.isfinite(r["final_stress_score"]) and 0.0 <= r["final_stress_score"] <= 100.0
        assert r["final_peak_load_mw"] >= 0

    # 3. Rank deterministically
    ranked = sorted(verified, key=lambda v: _ranking_key(v["candidate"], v["result"], overload_before))
    best = ranked[0]
    best_candidate, best_result = best["candidate"], best["result"]
    resolved = _resolves(best_result, overload_before)

    # Bookkeeping to classify WHY a failed candidate failed (not a stress recalculation):
    required_reduction_mw = (
        max(baseline_result["baseline_peak_load_mw"] - capacity_mw, 0.0) if overload_before
        else max(baseline_result["baseline_peak_load_mw"] - NON_OVERLOAD_TARGET_UTILIZATION * capacity_mw, 0.0)
    )
    max_feasible_reduction_mw = max(v["result"]["total_reduction_mw"] for v in verified)

    if resolved:
        prevention_status = "PREVENTED"
        reason = (f"{'Overload' if overload_before else 'Elevated risk'} predicted for feeder {feeder_id} at "
                  f"{target_ts}; intervention '{best_candidate['label']}' resolves it "
                  f"(verified via Simulation Engine + Stress Engine) at the lowest cost "
                  f"({best_candidate['cost']:.1f}) among all {len(non_null_candidates)} candidates tested.")
    else:
        if max_feasible_reduction_mw < required_reduction_mw - 1e-6:
            prevention_status = "INSUFFICIENT_FLEXIBILITY"
            remaining = required_reduction_mw - max_feasible_reduction_mw
            reason = (f"Required reduction (~{required_reduction_mw:.2f} MW) exceeds the maximum available "
                      f"synthetic flexibility ({max_feasible_reduction_mw:.2f} MW, all resources combined) -- "
                      f"prevention is NOT achievable with current resources. Best-effort intervention shown; "
                      f"~{remaining:.2f} MW of risk cannot be addressed.")
        elif best_result["total_reduction_mw"] > 0:
            prevention_status = "DURATION_LIMITED"
            reason = (f"Available synthetic flexibility ({max_feasible_reduction_mw:.2f} MW) is numerically "
                      f"sufficient to cover the required ~{required_reduction_mw:.2f} MW reduction, but no "
                      f"candidate's resource duration(s) reach the moment of peak risk at feeder {feeder_id} -- "
                      f"prevention is NOT achieved despite deploying the best-effort intervention "
                      f"('{best_candidate['label']}').")
        else:
            prevention_status = "REDUCED_NOT_PREVENTED"
            reason = (f"No candidate intervention fully resolved the predicted risk at feeder {feeder_id}; "
                      f"best-effort intervention shown reduces load but does not prevent the outcome.")

    base_output.update({
        "recommended_actions": best_result["actions_applied"],
        "total_reduction_mw": best_result["total_reduction_mw"],
        "projected_load_mw": best_result["final_load_mw_at_target"],
        "projected_stress_score": best_result["final_stress_score"],
        "projected_risk": best_result["final_risk"],
        "projected_time_to_overload": best_result["final_time_to_overload"],
        "overload_after": best_result["overload_after"],
        "overload_avoided": bool(overload_before and not best_result["overload_after"]),
        "prevention_status": prevention_status,
        "intervention_cost": best_candidate["cost"],
        "reason": reason,
        "required_reduction_mw": required_reduction_mw,
        "max_feasible_reduction_mw": max_feasible_reduction_mw,
    })
    base_output["candidates_evaluated"] = len(non_null_candidates)
    base_output["alternatives"] = [
        {"label": v["candidate"]["label"], "cost": v["candidate"]["cost"],
         "total_reduction_mw": v["result"]["total_reduction_mw"],
         "projected_risk": v["result"]["final_risk"], "overload_after": v["result"]["overload_after"],
         "resolved": _resolves(v["result"], overload_before)}
        for v in ranked
    ]
    return base_output


if __name__ == "__main__":
    idx = pd.date_range("2020-01-01 00:00:00", periods=25, freq="h")
    traj = pd.Series(np.linspace(90, 140, 25), index=idx)
    result = recommend_prevention("F_DEMO", "EV_HEAVY", 100.0, traj)
    print(f"status={result['prevention_status']}, actions={[a['resource'] for a in result['recommended_actions']]}, "
          f"overload_avoided={result['overload_avoided']}")
    print(result["reason"])
