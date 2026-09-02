"""
GridGuard AI - What-If Scenario Simulation Engine.

*** THIS IS A DECISION-SUPPORT SIMULATION, NOT REAL GRID CONTROL, AND NOT A
NEWLY TRAINED ML MODEL. *** The temperature / EV-surge / solar-drop layer
below is a documented, deterministic SCENARIO MODEL -- a set of synthetic
sensitivity assumptions applied on top of the existing 24h genuine hourly
forecast -- not a regression fitted to real Panama feeder telemetry, and
NOT a new input path into the trained XGBoost models.

WHY A SCENARIO LAYER, NOT A MODEL INPUT: the direct XGBoost forecasting
models (ml/src/train_direct_hourly_xgboost.py) intentionally exclude
target-time weather (no real weather-forecast data exists in this project),
and have no EV-surge or solar-generation features at all -- those signals do
not exist anywhere in the Mendeley dataset. The three what-if sliders
(Ambient Temperature, EV Demand Surge %, Solar Generation Drop %) therefore
CANNOT be "fed into" the forecasting models. Instead, this module takes the
model's existing, unmodified 24h forecast as a baseline and applies
transparent, documented multiplicative/additive adjustments on top of it.

    Existing 24h forecast (unmodified, from rolling_integration.py /
                            direct_hourly_forecast.py)
        v
    Scenario parameters (ambient_temperature_c, ev_surge_pct, solar_drop_pct)
        v
    Apply scenario adjustments (this module, documented synthetic coefficients)
        v
    Modified 24h load trajectory
        v
    Existing, UNMODIFIED Stress Engine (via action_engine.evaluate_trajectory)
        v
    Scenario outcome (+ optional Action Engine intervention layered on top)

The Stress Engine remains the SOLE source of truth for stress score, risk
level, utilization, voltage, and time-to-overload -- never recreated or
approximated here.

Does NOT modify: any trained model, the feature pipeline, regime_detector.py,
robust_hourly_forecast.py, feeder_generator.py, stress_engine.py,
rolling_integration.py, or action_engine.py.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import action_engine as ae  # existing, unmodified -- reused for stress-engine evaluation + intervention application
import stress_engine as se  # existing, unmodified -- sole source of truth for stress/risk (used only via ae)

VALID_RESOURCES = {"EV", "BATTERY", "INDUSTRIAL"}

# ---------------------------------------------------------------------------
# SCENARIO SENSITIVITY ASSUMPTIONS -- ALL SYNTHETIC.
#
# These coefficients are hand-chosen, documented engineering assumptions for
# simulation purposes. They are NOT fitted or learned from real Panama
# feeder telemetry (no such per-feeder telemetry exists in this project --
# see feeder_generator.py). The temperature sign/rough-magnitude choice is
# loosely *motivated* by the positive correlation between temperature and
# national demand documented in the original dataset audit (~0.65 for
# same-hour demand), but the specific coefficient below was NOT fitted via
# regression -- it is a chosen-for-plausibility scenario parameter, and must
# not be presented as a learned or validated value.
# ---------------------------------------------------------------------------
SCENARIO_ASSUMPTIONS = {
    "temperature": {
        "reference_temp_c": 27.0,          # a round, documented reference ambient temperature
        "pct_load_change_per_degree": 2.0,  # synthetic: +2% total feeder load per +1 degC above reference (cooling-load effect)
        "applies_uniformly_across_hours": True,
    },
    "ev_surge": {
        # synthetic: fraction of a feeder's load treated as "EV-surge-sensitive",
        # by feeder type -- EV_HEAVY feeders are assumed fully sensitive,
        # other types partially or not at all. Not derived from any real EV
        # penetration study.
        "feeder_type_sensitivity": {
            "EV_HEAVY": 1.00, "MIXED": 0.40, "RESIDENTIAL": 0.20,
            "COMMERCIAL": 0.05, "INDUSTRIAL": 0.00,
        },
        "applies_uniformly_across_hours": True,
    },
    "solar_drop": {
        "penetration_fraction_of_capacity": 0.10,  # synthetic: assumed behind-the-meter solar capacity = 10% of feeder capacity_mw
        "daylight_start_hour": 7,
        "daylight_end_hour": 18,
        # a simple half-sine shape peaking at solar noon (~12.5h), zero outside daylight hours -- a
        # documented simplification of a real solar generation profile, not measured irradiance data.
    },
}


def _daylight_shape(hour: int) -> float:
    """Synthetic solar-generation-availability shape: 0 outside daylight
    hours, a half-sine peaking at solar noon within them."""
    s = SCENARIO_ASSUMPTIONS["solar_drop"]
    start, end = s["daylight_start_hour"], s["daylight_end_hour"]
    if hour < start or hour > end:
        return 0.0
    span = end - start
    return float(np.sin(np.pi * (hour - start) / span))


# ---------------------------------------------------------------------------
# Scenario adjustment: baseline forecast -> scenario-modified trajectory,
# with an EXACT per-variable MW attribution (temperature/EV/solar effects
# are combined so that their sum equals the total change exactly).
# ---------------------------------------------------------------------------
def apply_scenario_adjustments(baseline_trajectory: pd.Series, capacity_mw: float, feeder_type: str,
                                 ambient_temperature_c: float = None, ev_surge_pct: float = 0.0,
                                 solar_drop_pct: float = 0.0) -> dict:
    """
    Returns a dict with:
      scenario_trajectory: the modified 24h(+1) load trajectory
      temperature_effect_mw, ev_surge_effect_mw, solar_drop_effect_mw: per-hour
        pd.Series of the MW contribution of each scenario variable (sum to
        the total change exactly)
      scenario_parameters: the input parameters actually used (after
        validation), for transparency in the output
    """
    assert np.isfinite(baseline_trajectory.values).all(), "Baseline trajectory contains NaN/inf"
    assert (baseline_trajectory.values >= 0).all(), "Baseline trajectory contains negative load"

    n = len(baseline_trajectory)
    hours = np.array([t.hour for t in baseline_trajectory.index])

    # --- Temperature effect (multiplicative on baseline load, uniform across hours) ---
    t_cfg = SCENARIO_ASSUMPTIONS["temperature"]
    if ambient_temperature_c is not None:
        if not np.isfinite(ambient_temperature_c):
            raise ValueError(f"ambient_temperature_c must be finite, got {ambient_temperature_c}")
        temp_delta = ambient_temperature_c - t_cfg["reference_temp_c"]
        temp_multiplier = 1.0 + (t_cfg["pct_load_change_per_degree"] / 100.0) * temp_delta
        temperature_effect_mw = baseline_trajectory.values * (temp_multiplier - 1.0)
    else:
        temperature_effect_mw = np.zeros(n)

    # --- EV surge effect (proportional to baseline load, feeder-type-weighted) ---
    ev_cfg = SCENARIO_ASSUMPTIONS["ev_surge"]
    if not np.isfinite(ev_surge_pct):
        raise ValueError(f"ev_surge_pct must be finite, got {ev_surge_pct}")
    ev_sensitivity = ev_cfg["feeder_type_sensitivity"].get(feeder_type, 0.0)
    ev_surge_effect_mw = baseline_trajectory.values * (ev_surge_pct / 100.0) * ev_sensitivity

    # --- Solar drop effect (additive, daylight-hours-only, capacity-scaled) ---
    solar_cfg = SCENARIO_ASSUMPTIONS["solar_drop"]
    if not np.isfinite(solar_drop_pct):
        raise ValueError(f"solar_drop_pct must be finite, got {solar_drop_pct}")
    daylight_weights = np.array([_daylight_shape(h) for h in hours])
    solar_drop_effect_mw = (solar_drop_pct / 100.0) * solar_cfg["penetration_fraction_of_capacity"] * capacity_mw * daylight_weights

    total_effect_mw = temperature_effect_mw + ev_surge_effect_mw + solar_drop_effect_mw
    scenario_values = np.clip(baseline_trajectory.values + total_effect_mw, 0.0, None)
    scenario_trajectory = pd.Series(scenario_values, index=baseline_trajectory.index, name="scenario_trajectory")

    return {
        "scenario_trajectory": scenario_trajectory,
        "temperature_effect_mw": pd.Series(temperature_effect_mw, index=baseline_trajectory.index),
        "ev_surge_effect_mw": pd.Series(ev_surge_effect_mw, index=baseline_trajectory.index),
        "solar_drop_effect_mw": pd.Series(solar_drop_effect_mw, index=baseline_trajectory.index),
        "scenario_parameters": {
            "ambient_temperature_c": ambient_temperature_c,
            "ev_surge_pct": ev_surge_pct,
            "solar_drop_pct": solar_drop_pct,
            "feeder_type_ev_sensitivity_used": ev_sensitivity,
        },
    }


# ---------------------------------------------------------------------------
# Intervention application (Action Engine compatibility) -- reuses
# action_engine.py's existing resource-limit definitions and trajectory
# application logic UNMODIFIED, so both engines share one synthetic-
# assumption source of truth. See action_engine.py's RESOURCE_ASSUMPTIONS.
# ---------------------------------------------------------------------------
def _classify_and_clip_action(proposed: dict, resources: dict) -> dict:
    resource_name = proposed.get("resource")
    requested_mw = proposed.get("mw")
    requested_duration = proposed.get("duration_hours")

    if resource_name not in VALID_RESOURCES:
        return {"resource": resource_name, "valid": False, "reason": f"Unknown resource type '{resource_name}'",
                "requested_mw": requested_mw, "requested_duration_hours": requested_duration,
                "applied_mw": 0.0, "applied_duration_hours": 0.0, "clipped": False}
    if requested_mw is None or requested_mw <= 0 or not np.isfinite(requested_mw):
        return {"resource": resource_name, "valid": False, "reason": f"Invalid mw value: {requested_mw}",
                "requested_mw": requested_mw, "requested_duration_hours": requested_duration,
                "applied_mw": 0.0, "applied_duration_hours": 0.0, "clipped": False}

    limit = resources[resource_name]
    if requested_duration is None:
        requested_duration = limit.duration_hours
    if requested_duration <= 0 or not np.isfinite(requested_duration):
        return {"resource": resource_name, "valid": False, "reason": f"Invalid duration_hours value: {requested_duration}",
                "requested_mw": requested_mw, "requested_duration_hours": requested_duration,
                "applied_mw": 0.0, "applied_duration_hours": 0.0, "clipped": False}

    applied_mw = min(requested_mw, limit.mw)
    applied_duration = min(requested_duration, limit.duration_hours)
    clipped = (applied_mw < requested_mw - 1e-9) or (applied_duration < requested_duration - 1e-9)
    return {
        "resource": resource_name, "valid": True, "reason": None,
        "requested_mw": requested_mw, "requested_duration_hours": requested_duration,
        "applied_mw": applied_mw, "applied_duration_hours": applied_duration,
        "clipped": clipped, "disruption_cost": limit.disruption_cost,
        "resource_max_mw": limit.mw, "resource_max_duration_hours": limit.duration_hours,
    }


def determine_feasibility(proposed_actions: list, capacity_mw: float) -> tuple:
    """"feasible" / "partially_feasible" / "infeasible" -- see action_engine.py's
    RESOURCE_ASSUMPTIONS for the underlying (unmodified, reused) limits."""
    resources = ae.build_resources_for_capacity(capacity_mw)  # existing, unmodified
    details = [_classify_and_clip_action(p, resources) for p in (proposed_actions or [])]
    valid_details = [d for d in details if d["valid"]]
    if len(valid_details) == 0:
        return ("infeasible" if proposed_actions else "not_applicable"), details
    if any(d["clipped"] for d in valid_details):
        return "partially_feasible", details
    return "feasible", details


def apply_intervention(trajectory: pd.Series, proposed_actions: list, capacity_mw: float) -> dict:
    feasibility_status, action_details = determine_feasibility(proposed_actions, capacity_mw)
    applied_actions = [
        ae.Action(resource=d["resource"], mw=d["applied_mw"], duration_hours=d["applied_duration_hours"],
                   disruption_cost=d["disruption_cost"])
        for d in action_details if d["valid"] and d["applied_mw"] > 0
    ]
    if applied_actions:
        modified = ae.apply_actions_to_trajectory(trajectory, applied_actions)  # existing, unmodified
    else:
        modified = trajectory.copy()

    assert (modified.values <= trajectory.values + 1e-9).all(), "Intervention must never increase load"
    assert (modified.values >= 0).all(), "Intervention must never produce negative load"

    return {
        "modified_trajectory": modified,
        "feasibility_status": feasibility_status,
        "actions_applied": action_details,
        "total_reduction_mw": sum(d["applied_mw"] for d in action_details if d["valid"]),
    }


# ---------------------------------------------------------------------------
# Trajectory construction helper (single-baseline-value convenience path)
# ---------------------------------------------------------------------------
def build_flat_trajectory(target_timestamp, baseline_forecast_mw: float, current_load_mw: float = None,
                           horizon_hours: int = 24) -> pd.Series:
    """When only a single baseline MW value is available (not a full 24h
    forecast trajectory), builds a flat trajectory holding that level for
    the full window. *** DOCUMENTED APPROXIMATION for ad-hoc single-point
    what-if queries only *** -- prefer supplying a real trajectory from
    rolling_integration.py's output for accurate time-to-overload results."""
    target_timestamp = pd.Timestamp(target_timestamp)
    if current_load_mw is None:
        current_load_mw = baseline_forecast_mw
    origin = target_timestamp - pd.Timedelta(hours=horizon_hours)
    index = pd.date_range(origin, periods=horizon_hours + 1, freq="h")
    values = np.full(horizon_hours + 1, baseline_forecast_mw, dtype=float)
    values[0] = current_load_mw
    return pd.Series(values, index=index, name="flat_baseline_trajectory")


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------
def simulate_scenario(feeder_id: str, feeder_type: str, capacity_mw: float,
                       baseline_trajectory: pd.Series = None, target_timestamp=None,
                       baseline_forecast_mw: float = None, current_load_mw: float = None,
                       ambient_temperature_c: float = None, ev_surge_pct: float = 0.0,
                       solar_drop_pct: float = 0.0, proposed_actions: list = None) -> dict:
    """
    Full flow:
        existing 24h forecast -> scenario adjustments -> existing Stress Engine
        -> (optional) Action Engine intervention on top -> existing Stress Engine again

    Provide EITHER `baseline_trajectory` (a real 24h(+1)-point forecast, e.g.
    from rolling_integration.py's output) OR `baseline_forecast_mw` (+
    `target_timestamp`, optional `current_load_mw`) for the flat-trajectory
    approximation. See build_flat_trajectory's docstring for that tradeoff.
    """
    assert capacity_mw > 0 and np.isfinite(capacity_mw), "capacity_mw must be positive and finite"

    if baseline_trajectory is None:
        assert baseline_forecast_mw is not None and target_timestamp is not None, \
            "Must supply either `baseline_trajectory` or (`baseline_forecast_mw` + `target_timestamp`)"
        baseline_trajectory = build_flat_trajectory(target_timestamp, baseline_forecast_mw, current_load_mw)
        trajectory_is_approximated = True
    else:
        trajectory_is_approximated = False
        assert np.isfinite(baseline_trajectory.values).all(), "Baseline trajectory contains NaN/inf"
        assert (baseline_trajectory.values >= 0).all(), "Baseline trajectory contains negative load"

    # 1. BASELINE -- existing, unmodified stress engine
    baseline_eval = ae.evaluate_trajectory(baseline_trajectory, capacity_mw)

    # 2. Apply scenario adjustments (this module; documented synthetic coefficients)
    scenario = apply_scenario_adjustments(baseline_trajectory, capacity_mw, feeder_type,
                                            ambient_temperature_c, ev_surge_pct, solar_drop_pct)
    scenario_trajectory = scenario["scenario_trajectory"]

    # 3. Re-run the existing, unmodified stress engine on the scenario trajectory
    scenario_eval = ae.evaluate_trajectory(scenario_trajectory, capacity_mw)

    # 4. Optional: apply an Action Engine intervention ON TOP of the scenario trajectory
    intervention_result = None
    post_intervention_eval = None
    final_trajectory = scenario_trajectory
    if proposed_actions:
        intervention_result = apply_intervention(scenario_trajectory, proposed_actions, capacity_mw)
        final_trajectory = intervention_result["modified_trajectory"]
        post_intervention_eval = ae.evaluate_trajectory(final_trajectory, capacity_mw)  # existing, unmodified

    def _load_at(traj, eval_metrics):
        ts = pd.Timestamp(target_timestamp) if target_timestamp is not None else eval_metrics["peak_timestamp"]
        return float(traj.loc[ts]) if ts in traj.index else eval_metrics["peak_load_mw"], ts

    baseline_load_mw, target_ts = _load_at(baseline_trajectory, baseline_eval)
    scenario_load_mw, _ = _load_at(scenario_trajectory, scenario_eval)
    final_load_mw, _ = _load_at(final_trajectory, post_intervention_eval or scenario_eval)

    overload_before = baseline_eval["overload_predicted"]
    overload_after_scenario = scenario_eval["overload_predicted"]
    overload_after_intervention = post_intervention_eval["overload_predicted"] if post_intervention_eval else None
    final_overload = overload_after_intervention if post_intervention_eval else overload_after_scenario
    overload_avoided = bool(overload_after_scenario and post_intervention_eval and not overload_after_intervention)

    result = {
        "feeder_id": feeder_id,
        "feeder_type": feeder_type,
        "capacity_mw": capacity_mw,
        "target_timestamp": str(target_ts),
        "trajectory_is_approximated": trajectory_is_approximated,

        "scenario_parameters": scenario["scenario_parameters"],

        # ---- baseline (existing forecast, no scenario, no intervention) ----
        "baseline_peak_load_mw": baseline_eval["peak_load_mw"],
        "baseline_load_mw_at_target": baseline_load_mw,
        "baseline_utilization": baseline_eval["peak_utilization"],
        "baseline_stress_score": baseline_eval["stress_score"],
        "baseline_risk": baseline_eval["risk_level"],
        "baseline_time_to_overload": baseline_eval["time_to_overload_hours"],
        "overload_before": overload_before,

        # ---- scenario outcome (forecast + temperature/EV/solar adjustments) ----
        "scenario_peak_load_mw": scenario_eval["peak_load_mw"],
        "scenario_load_mw_at_target": scenario_load_mw,
        "scenario_utilization": scenario_eval["peak_utilization"],
        "scenario_stress_score": scenario_eval["stress_score"],
        "scenario_risk": scenario_eval["risk_level"],
        "scenario_time_to_overload": scenario_eval["time_to_overload_hours"],
        "overload_after_scenario": overload_after_scenario,

        # ---- per-variable load-change attribution (exact, sums to total change) ----
        "load_change_mw": {
            "temperature": float(scenario["temperature_effect_mw"].loc[target_ts]) if target_ts in scenario["temperature_effect_mw"].index else float(scenario["temperature_effect_mw"].iloc[-1]),
            "ev_surge": float(scenario["ev_surge_effect_mw"].loc[target_ts]) if target_ts in scenario["ev_surge_effect_mw"].index else float(scenario["ev_surge_effect_mw"].iloc[-1]),
            "solar_drop": float(scenario["solar_drop_effect_mw"].loc[target_ts]) if target_ts in scenario["solar_drop_effect_mw"].index else float(scenario["solar_drop_effect_mw"].iloc[-1]),
            "total": scenario_load_mw - baseline_load_mw,
        },

        # ---- post-intervention outcome (if a proposed action was supplied) ----
        "intervention_applied": proposed_actions is not None and len(proposed_actions) > 0,
        "feasibility_status": intervention_result["feasibility_status"] if intervention_result else "not_applicable",
        "actions_applied": intervention_result["actions_applied"] if intervention_result else [],
        "total_reduction_mw": intervention_result["total_reduction_mw"] if intervention_result else 0.0,
        "final_peak_load_mw": (post_intervention_eval or scenario_eval)["peak_load_mw"],
        "final_load_mw_at_target": final_load_mw,
        "final_utilization": (post_intervention_eval or scenario_eval)["peak_utilization"],
        "final_stress_score": (post_intervention_eval or scenario_eval)["stress_score"],
        "final_risk": (post_intervention_eval or scenario_eval)["risk_level"],
        "final_time_to_overload": (post_intervention_eval or scenario_eval)["time_to_overload_hours"],
        "overload_after": final_overload,
        "overload_avoided": overload_avoided,

        "resolution_note": scenario_eval["resolution_note"],
    }
    return result


if __name__ == "__main__":
    # Minimal smoke example. See evaluate_simulation_engine.py for the full
    # controlled scenario suite.
    idx = pd.date_range("2020-01-15 00:00:00", periods=25, freq="h")
    baseline = pd.Series(np.concatenate([[70], 70 + 20 * np.sin(np.linspace(0, 2 * np.pi, 24))]), index=idx)
    baseline = baseline.clip(lower=10)

    result = simulate_scenario(
        feeder_id="F_DEMO", feeder_type="EV_HEAVY", capacity_mw=100.0,
        baseline_trajectory=baseline,
        ambient_temperature_c=34.0, ev_surge_pct=30.0, solar_drop_pct=50.0,
        proposed_actions=[{"resource": "BATTERY", "mw": 15.0, "duration_hours": 3.0}],
    )
    print(f"baseline_risk={result['baseline_risk']} -> scenario_risk={result['scenario_risk']} -> "
          f"final_risk={result['final_risk']}")
    print(f"overload_before={result['overload_before']}, overload_after_scenario={result['overload_after_scenario']}, "
          f"overload_after={result['overload_after']}, overload_avoided={result['overload_avoided']}")
    print(f"load_change_mw={result['load_change_mw']}")
