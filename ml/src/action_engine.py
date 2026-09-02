"""
GridGuard AI - Action / Optimization Engine.

*** THIS IS A DECISION-SUPPORT SIMULATION, NOT REAL GRID CONTROL. ***
Given a feeder's forecast trajectory (from the current, regime-aware genuine
hourly forecasting pipeline -- ml/src/rolling_integration.py) and the
existing, UNMODIFIED Grid Stress Engine's assessment of it, this module
answers: "what intervention could reduce the predicted stress or prevent an
overload?"

*** ALL FLEXIBLE RESOURCES (EV, BATTERY, INDUSTRIAL) ARE SYNTHETIC. ***
Their magnitudes, durations, and disruption costs are hand-chosen, documented
engineering assumptions, scaled off each feeder's synthetic capacity_mw --
NOT derived from real Panama EV fleets, battery installations, or industrial
demand-response contracts. See RESOURCE_ASSUMPTIONS below. Never present
these as real grid-control capabilities.

ARCHITECTURE RULE (unchanged from the prior Action Engine build): this
module does not replace or reimplement the stress formula. Every "baseline"
and "projected" (post-action) metric is produced by calling the existing,
unmodified stress_engine.py functions (compute_stress_score,
classify_stress, time_to_overload) -- never by assuming
"projected_load = load - action" solves the problem on its own.

Does not modify: any trained model, the feature pipeline, regime_detector.py,
robust_hourly_forecast.py, feeder_generator.py, stress_engine.py, or
rolling_integration.py.
"""
import os
import sys
from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import feeder_generator as fg  # existing, unmodified -- reused only for its voltage model
import stress_engine as se     # existing, unmodified -- sole source of truth for stress/risk

SEED = fg.SEED

# ---------------------------------------------------------------------------
# RESOURCE ASSUMPTIONS -- ALL SYNTHETIC, documented, easy to tune.
# Sized as a fraction of the feeder's own capacity_mw so the same assumptions
# generalize across feeders of different sizes. None of these numbers come
# from real Panama grid-flexibility data, real EV fleets, real battery
# installations, or real industrial demand-response contracts.
# ---------------------------------------------------------------------------
RESOURCE_ASSUMPTIONS = {
    "EV": {
        "max_shift_fraction_of_capacity": 0.15,  # max shiftable EV charging load, fraction of feeder capacity
        "max_shift_duration_hours": 4.0,          # max hours charging can be delayed
        "disruption_cost": 1.0,                   # arbitrary unit scale; low -- a delayed charge, not a denial
    },
    "BATTERY": {
        "energy_capacity_fraction_of_capacity_mwh": 1.0,  # battery energy capacity, as "hours of feeder capacity"
        "default_soc": 0.70,                              # assumed state of charge at decision time (synthetic default)
        "max_discharge_fraction_of_capacity": 0.20,        # max discharge power, fraction of feeder capacity
        "disruption_cost": 0.5,                            # lowest disruption: no customer impact
    },
    "INDUSTRIAL": {
        "max_reducible_fraction_of_capacity": 0.25,  # max curtailable flexible industrial load, fraction of capacity
        "max_duration_hours": 6.0,                    # max hours industrial load can be curtailed
        "disruption_cost": 3.0,                       # highest disruption: assumed real business impact
    },
}

# Engineering thresholds (not scientifically validated -- documented, tunable):
# when overload is NOT predicted but risk is HIGH/CRITICAL, the target for
# "how much reduction is worth pursuing" is bringing peak utilization back
# under this fraction of capacity (a conservative safety margin), rather than
# an undefined "reduce forever" objective.
NON_OVERLOAD_TARGET_UTILIZATION = 0.90


@dataclass(frozen=True)
class Action:
    """One deployed synthetic resource action: a constant MW reduction
    sustained for `duration_hours`, starting at the trajectory's first hour
    (dispatched as soon as the forecast-driven risk is known)."""
    resource: str
    mw: float
    duration_hours: float
    disruption_cost: float


def build_resources_for_capacity(capacity_mw: float) -> dict:
    """Instantiate the three synthetic resources' concrete (MW, duration,
    cost) for one feeder's capacity_mw. See RESOURCE_ASSUMPTIONS."""
    ev = RESOURCE_ASSUMPTIONS["EV"]
    batt = RESOURCE_ASSUMPTIONS["BATTERY"]
    ind = RESOURCE_ASSUMPTIONS["INDUSTRIAL"]

    ev_action = Action("EV", ev["max_shift_fraction_of_capacity"] * capacity_mw,
                        ev["max_shift_duration_hours"], ev["disruption_cost"])

    batt_energy_mwh = batt["energy_capacity_fraction_of_capacity_mwh"] * capacity_mw
    batt_mw = batt["max_discharge_fraction_of_capacity"] * capacity_mw
    batt_available_energy = batt_energy_mwh * batt["default_soc"]
    batt_duration = min(batt_available_energy / batt_mw, 4.0) if batt_mw > 0 else 0.0
    batt_action = Action("BATTERY", batt_mw, batt_duration, batt["disruption_cost"])

    ind_action = Action("INDUSTRIAL", ind["max_reducible_fraction_of_capacity"] * capacity_mw,
                         ind["max_duration_hours"], ind["disruption_cost"])

    for a in (ev_action, batt_action, ind_action):
        assert a.mw >= 0 and np.isfinite(a.mw)
        assert a.duration_hours >= 0 and np.isfinite(a.duration_hours)
    return {"EV": ev_action, "BATTERY": batt_action, "INDUSTRIAL": ind_action}


def apply_actions_to_trajectory(trajectory: pd.Series, actions: list) -> pd.Series:
    """Returns a NEW trajectory (input untouched) with each action's MW
    reduction applied for its own duration window, starting at the first
    point. Loads are clipped at 0. Actions with different durations produce
    a step-down reduction profile as shorter-duration resources expire."""
    hours = np.array([(t - trajectory.index[0]).total_seconds() / 3600.0 for t in trajectory.index])
    reduction = np.zeros(len(trajectory))
    for a in actions:
        active = hours <= a.duration_hours + 1e-9
        reduction[active] += a.mw
    modified = np.clip(trajectory.values - reduction, 0.0, None)
    return pd.Series(modified, index=trajectory.index, name=trajectory.name)


# ---------------------------------------------------------------------------
# Scenario container: what the action engine consumes from the forecasting
# pipeline. Mirrors the columns available in rolling_integration.py's output
# (ml/data/rolling_feeder_results.csv) for one (origin, feeder) pair:
# feeder_id, feeder_type, capacity_mw, and the 24-point forecast trajectory
# (current load at h=0 + genuine hourly forecasts at h=1..24).
# ---------------------------------------------------------------------------
@dataclass
class FeederScenario:
    feeder_id: str
    feeder_type: str
    capacity_mw: float
    trajectory: pd.Series  # DatetimeIndex, h=0 (current) .. h=24 (forecast), MW


def evaluate_trajectory(trajectory: pd.Series, capacity_mw: float) -> dict:
    """Computes baseline/projected metrics for a trajectory using ONLY the
    existing, unmodified stress_engine.py (and feeder_generator.py's voltage
    model) -- never a reimplemented formula."""
    assert capacity_mw > 0 and np.isfinite(capacity_mw)
    assert np.isfinite(trajectory.values).all(), "Trajectory contains NaN/inf"
    assert (trajectory.values >= 0).all(), "Trajectory contains negative load"

    peak_load_mw = float(trajectory.max())
    peak_idx = int(np.argmax(trajectory.values))
    peak_timestamp = trajectory.index[peak_idx]
    peak_utilization = peak_load_mw / capacity_mw

    current_load = float(trajectory.iloc[0])
    forecast_load = float(trajectory.iloc[-1])
    util_current = current_load / capacity_mw
    voltage_pu = float(fg.simulate_voltage(np.array([util_current]), seed=SEED, add_noise=False)[0])

    score, components = se.compute_stress_score(current_load, forecast_load, capacity_mw, voltage_pu)
    risk_level = se.classify_stress(score)
    tto = se.time_to_overload(trajectory, capacity_mw)

    return {
        "peak_load_mw": peak_load_mw,
        "peak_timestamp": peak_timestamp,
        "peak_utilization": peak_utilization,
        "current_load_mw": current_load,
        "forecast_load_mw": forecast_load,
        "current_utilization": util_current,
        "forecast_utilization": forecast_load / capacity_mw,
        "voltage_pu": voltage_pu,
        "stress_score": score,
        "stress_components": components,
        "risk_level": risk_level,
        "overload_predicted": tto["overload_predicted"],
        "time_to_overload_hours": tto["time_to_overload_hours"],
        "resolution_note": tto["resolution_note"],
    }


def generate_candidates(capacity_mw: float) -> list:
    """All 7 non-empty combinations of the 3 synthetic resources. Each
    resource's own MW/duration/SOC constraints are already respected by
    construction (build_resources_for_capacity), so every combination is
    structurally feasible -- no combination is excluded here."""
    resources = build_resources_for_capacity(capacity_mw)
    names = list(resources.keys())
    candidates = []
    for r in range(1, len(names) + 1):
        for combo in combinations(names, r):
            candidates.append({"label": "+".join(combo), "actions": [resources[n] for n in combo]})
    return candidates


def evaluate_candidate(trajectory: pd.Series, capacity_mw: float, candidate: dict) -> dict:
    modified = apply_actions_to_trajectory(trajectory, candidate["actions"])
    metrics = evaluate_trajectory(modified, capacity_mw)
    return {
        "label": candidate["label"],
        "actions": [{"resource": a.resource, "mw": a.mw, "duration_hours": a.duration_hours,
                     "disruption_cost": a.disruption_cost} for a in candidate["actions"]],
        "total_reduction_mw": sum(a.mw for a in candidate["actions"]),
        "total_disruption_cost": sum(a.disruption_cost for a in candidate["actions"]),
        "projected_peak_load_mw": metrics["peak_load_mw"],
        "projected_utilization": metrics["peak_utilization"],
        "projected_stress_score": metrics["stress_score"],
        "projected_risk_level": metrics["risk_level"],
        "overload_predicted": metrics["overload_predicted"],
        "time_to_overload_hours": metrics["time_to_overload_hours"],
        "modified_trajectory": modified,
    }


# ---------------------------------------------------------------------------
# Selection objective (deterministic):
#   1. PRIMARY:   resolve the trigger -- prevent overload if one was
#                 predicted, else bring peak utilization back under the
#                 NON_OVERLOAD_TARGET_UTILIZATION safety margin
#   2. SECONDARY: minimize total disruption/cost
#   3. TERTIARY:  minimize total MW reduction deployed (no unnecessary intervention)
# ---------------------------------------------------------------------------
def _resolves_trigger(evaluated: dict, baseline_overload: bool) -> bool:
    if baseline_overload:
        return not evaluated["overload_predicted"]
    return evaluated["projected_utilization"] <= NON_OVERLOAD_TARGET_UTILIZATION


def _ranking_key(evaluated: dict, baseline_overload: bool):
    return (
        0 if _resolves_trigger(evaluated, baseline_overload) else 1,
        evaluated["total_disruption_cost"],
        evaluated["total_reduction_mw"],
    )


def _fallback_ranking_key(evaluated: dict):
    """Used only when no candidate resolves the trigger: prefer the lowest
    resulting utilization (closest to safe), tie-broken by lower cost."""
    return (evaluated["projected_utilization"], evaluated["total_disruption_cost"])


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------
def recommend_action(scenario: FeederScenario) -> dict:
    """
    Decision logic:
      1. Determine required MW reduction (from the trajectory's peak vs.
         capacity, or vs. the safety-margin target if not yet overloaded).
      2. Determine available flexibility (the 3 synthetic resources, sized
         to this feeder's capacity).
      3. Select the lowest-cost, then smallest, combination that resolves
         the trigger.
      4. Resource limits are respected by construction.
      5. If no combination is sufficient, report that explicitly -- never
         claim success that wasn't achieved.
    """
    baseline = evaluate_trajectory(scenario.trajectory, scenario.capacity_mw)
    is_safe = (not baseline["overload_predicted"]) and baseline["risk_level"] in ("LOW", "MODERATE")

    result = {
        "feeder_id": scenario.feeder_id,
        "feeder_type": scenario.feeder_type,
        "target_timestamp": str(baseline["peak_timestamp"]),
        "baseline_forecast_mw": baseline["peak_load_mw"],
        "capacity_mw": scenario.capacity_mw,
        "baseline_utilization": baseline["peak_utilization"],
        "baseline_risk_level": baseline["risk_level"],
        "baseline_stress_score": baseline["stress_score"],
        "baseline_overload_predicted": baseline["overload_predicted"],
        "baseline_time_to_overload_hours": baseline["time_to_overload_hours"],
    }

    if is_safe:
        result.update({
            "action_required": False,
            "recommended_actions": [],
            "total_reduction_mw": 0.0,
            "projected_load_mw": baseline["peak_load_mw"],
            "projected_utilization": baseline["peak_utilization"],
            "projected_risk_level": baseline["risk_level"],
            "overload_avoided": not baseline["overload_predicted"],
            "intervention_cost": 0.0,
            "reason": (f"Feeder {scenario.feeder_id} is not predicted to overload and risk level "
                        f"({baseline['risk_level']}) is LOW/MODERATE -- no intervention recommended."),
        })
        result["alternatives"] = []
        return result

    # 1-2. required reduction + available flexibility
    required_reduction_mw = (
        max(baseline["peak_load_mw"] - scenario.capacity_mw, 0.0) if baseline["overload_predicted"]
        else max(baseline["peak_load_mw"] - NON_OVERLOAD_TARGET_UTILIZATION * scenario.capacity_mw, 0.0)
    )

    candidates = generate_candidates(scenario.capacity_mw)
    evaluated = [evaluate_candidate(scenario.trajectory, scenario.capacity_mw, c) for c in candidates]

    for e in evaluated:
        assert np.isfinite(e["projected_stress_score"])
        assert 0.0 <= e["projected_stress_score"] <= 100.0
        assert e["projected_peak_load_mw"] >= 0
        assert (e["modified_trajectory"].values <= scenario.trajectory.values + 1e-9).all(), \
            f"Candidate {e['label']} increased load at some hour -- must never happen"

    # 3. select lowest-cost, then smallest, combination that resolves the trigger
    ranked = sorted(evaluated, key=lambda e: _ranking_key(e, baseline["overload_predicted"]))
    any_resolves = any(_resolves_trigger(e, baseline["overload_predicted"]) for e in evaluated)
    best = ranked[0]

    max_feasible_reduction_mw = max(e["total_reduction_mw"] for e in evaluated)

    if any_resolves:
        overload_avoided = not best["overload_predicted"] if baseline["overload_predicted"] else True
        reason = (f"{'Overload' if baseline['overload_predicted'] else 'Elevated risk'} predicted for feeder "
                  f"{scenario.feeder_id} at {baseline['peak_timestamp']}; action '{best['label']}' resolves it "
                  f"at the lowest available disruption cost ({best['total_disruption_cost']:.1f}) among all "
                  f"feasible combinations tested.")
        result.update({
            "action_required": True,
            "recommended_actions": best["actions"],
            "total_reduction_mw": best["total_reduction_mw"],
            "projected_load_mw": best["projected_peak_load_mw"],
            "projected_utilization": best["projected_utilization"],
            "projected_risk_level": best["projected_risk_level"],
            "overload_avoided": overload_avoided,
            "intervention_cost": best["total_disruption_cost"],
            "reason": reason,
        })
    else:
        # 5. insufficient flexibility -- report honestly, never claim success
        fallback_ranked = sorted(evaluated, key=_fallback_ranking_key)
        best_effort = fallback_ranked[0]
        remaining_mw = max(required_reduction_mw - max_feasible_reduction_mw, 0.0)
        reason = (f"Overload predicted for feeder {scenario.feeder_id} at {baseline['peak_timestamp']} requires "
                  f"~{required_reduction_mw:.2f} MW reduction, but the available synthetic flexible resources "
                  f"(EV+Battery+Industrial, fully deployed) provide at most {max_feasible_reduction_mw:.2f} MW -- "
                  f"insufficient to fully prevent the overload. Best-effort action shown; "
                  f"~{remaining_mw:.2f} MW of overload cannot be prevented with available flexibility.")
        result.update({
            "action_required": True,
            "recommended_actions": best_effort["actions"],
            "total_reduction_mw": best_effort["total_reduction_mw"],
            "projected_load_mw": best_effort["projected_peak_load_mw"],
            "projected_utilization": best_effort["projected_utilization"],
            "projected_risk_level": best_effort["projected_risk_level"],
            "overload_avoided": False,
            "intervention_cost": best_effort["total_disruption_cost"],
            "required_reduction_mw": required_reduction_mw,
            "max_feasible_reduction_mw": max_feasible_reduction_mw,
            "remaining_overload_mw": remaining_mw,
            "reason": reason,
        })

    result["alternatives"] = [{k: v for k, v in e.items() if k != "modified_trajectory"} for e in ranked]
    return result


# ---------------------------------------------------------------------------
# Optional: build a FeederScenario directly from rolling_integration.py's
# output CSV (ml/data/rolling_feeder_results.csv), for one (origin, feeder)
# pair. Read-only; does not modify that file or rolling_integration.py.
# ---------------------------------------------------------------------------
def load_scenario_from_rolling_results(csv_path: str, origin_datetime, feeder_id: str,
                                        chunksize: int = 240_000) -> FeederScenario:
    origin_datetime = pd.Timestamp(origin_datetime)
    rows = None
    for chunk in pd.read_csv(csv_path, chunksize=chunksize, parse_dates=["origin_datetime", "forecast_datetime"]):
        match = chunk[(chunk["origin_datetime"] == origin_datetime) & (chunk["feeder_id"] == feeder_id)]
        if len(match) > 0:
            rows = match if rows is None else pd.concat([rows, match])
        if rows is not None and len(rows) == 24:
            break
    if rows is None or len(rows) != 24:
        raise ValueError(f"Could not find exactly 24 rows for origin={origin_datetime}, feeder={feeder_id} in {csv_path}")

    rows = rows.sort_values("forecast_horizon")
    capacity_mw = float(rows["capacity_mw"].iloc[0])
    feeder_type = rows["feeder_type"].iloc[0]
    current_load = float(rows["load_mw"].iloc[0])

    index = pd.DatetimeIndex([origin_datetime] + list(rows["forecast_datetime"]))
    values = np.concatenate([[current_load], rows["forecast_mw"].values])
    trajectory = pd.Series(values, index=index, name=f"{feeder_id}_trajectory")

    return FeederScenario(feeder_id=feeder_id, feeder_type=feeder_type, capacity_mw=capacity_mw, trajectory=trajectory)


if __name__ == "__main__":
    # Minimal smoke example using a deliberately constructed (documented
    # synthetic) trajectory -- see evaluate_action_engine.py for the full
    # controlled scenario suite.
    idx = pd.date_range("2020-01-01 00:00:00", periods=25, freq="h")
    traj = pd.Series(np.linspace(60, 120, 25), index=idx)
    scenario = FeederScenario(feeder_id="F_DEMO", feeder_type="EV_HEAVY", capacity_mw=100.0, trajectory=traj)
    rec = recommend_action(scenario)
    print(f"action_required={rec['action_required']}, actions={[a['resource'] for a in rec['recommended_actions']]}, "
          f"overload_avoided={rec['overload_avoided']}, reason={rec['reason']}")
