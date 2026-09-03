"""
GridGuard AI - Grid Stress Engine.

Deterministic, explainable, rule-based scoring over measurable feeder
quantities (utilization, forecast trajectory, voltage, headroom). This is
NOT a machine-learning model -- there is no training, no fitted parameters,
and no hidden state. Every weight and threshold below is a plain constant
that can be read, modified, and re-run directly.

Operates on synthetic feeder data produced by ml/src/feeder_generator.py.
See that module's docstring: all feeder loads/capacities/voltages consumed
here are SIMULATED, not real Panama feeder measurements.
"""
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Stress score weights. Must sum to 1.0 (enforced by assertion below). Easy
# to tune: change a value here and re-run -- no retraining involved anywhere
# in this module.
# ---------------------------------------------------------------------------
STRESS_WEIGHTS = {
    "current_utilization": 0.35,   # how loaded the feeder is right now
    "forecast_utilization": 0.30,  # how loaded it's predicted to be in 24h
    "trajectory_slope": 0.15,      # how fast it's moving toward capacity
    "voltage_stress": 0.10,        # how far simulated voltage has sagged
    "headroom": 0.10,              # how little spare capacity remains right now
}
assert abs(sum(STRESS_WEIGHTS.values()) - 1.0) < 1e-9, "STRESS_WEIGHTS must sum to 1.0"

# ---------------------------------------------------------------------------
# Classification thresholds (0-100 score).
#
# THESE ARE INITIAL ENGINEERING THRESHOLDS chosen for interpretability and
# demonstration purposes (even round-number bands). They are NOT derived from
# any field-validated grid-reliability study, utility outage data, or
# statistical calibration against real overload events -- none of that data
# exists in this project (see feeder_generator.py: all feeder data is
# synthetic). Before any operational use, these bands should be calibrated
# against real outage/overload history.
# ---------------------------------------------------------------------------
STRESS_THRESHOLDS = {
    "LOW": (0, 30),
    "MODERATE": (31, 60),
    "HIGH": (61, 80),
    "CRITICAL": (81, 100),
}

# Voltage-stress component parameters (see voltage_stress_component below).
VOLTAGE_STRESS_PARAMS = {
    "low_limit_pu": 0.95,       # at/above this, voltage contributes 0 stress
    "critical_limit_pu": 0.90,  # at/below this, voltage contributes full (1.0) stress
}


def _clip01(x):
    return float(np.clip(x, 0.0, 1.0))


def current_utilization_component(current_load_mw, capacity_mw):
    """0 at zero load, 1 at/above capacity."""
    if capacity_mw <= 0:
        return 0.0
    return _clip01(current_load_mw / capacity_mw)


def forecast_utilization_component(forecast_load_mw, capacity_mw):
    """Same as current_utilization_component, applied to the 24h-ahead
    forecast load instead of the current load."""
    if capacity_mw <= 0:
        return 0.0
    return _clip01(forecast_load_mw / capacity_mw)


def trajectory_slope_component(current_load_mw, forecast_load_mw, capacity_mw):
    """Normalized rate of movement toward capacity over the forecast
    horizon: (forecast - current) / capacity, clipped to [0, 1]. A load that
    is flat or falling contributes 0 (it does not reduce the score below what
    the utilization terms already say -- it simply adds no extra "rising
    risk" signal)."""
    if capacity_mw <= 0:
        return 0.0
    delta = (forecast_load_mw - current_load_mw) / capacity_mw
    return _clip01(delta)


def voltage_stress_component(voltage_pu, params=None):
    """0 at/above low_limit_pu (nominal), 1 at/below critical_limit_pu
    (severe sag), linear in between."""
    p = params or VOLTAGE_STRESS_PARAMS
    low, crit = p["low_limit_pu"], p["critical_limit_pu"]
    if voltage_pu >= low:
        return 0.0
    if voltage_pu <= crit:
        return 1.0
    return _clip01((low - voltage_pu) / (low - crit))


def headroom_component(current_load_mw, capacity_mw):
    """Inverted remaining headroom: headroom_ratio = (capacity - current) /
    capacity (0 = no headroom, 1 = fully empty feeder); component = 1 -
    headroom_ratio, so less headroom -> higher stress contribution."""
    if capacity_mw <= 0:
        return 1.0
    headroom_ratio = _clip01((capacity_mw - current_load_mw) / capacity_mw)
    return _clip01(1.0 - headroom_ratio)


def compute_stress_score(current_load_mw, forecast_load_mw, capacity_mw, voltage_pu, weights=None):
    """Returns (score in [0,100], components dict with each term's raw [0,1]
    value before weighting) so the score is always explainable: score =
    100 * sum(weight_k * component_k)."""
    w = weights or STRESS_WEIGHTS
    components = {
        "current_utilization": current_utilization_component(current_load_mw, capacity_mw),
        "forecast_utilization": forecast_utilization_component(forecast_load_mw, capacity_mw),
        "trajectory_slope": trajectory_slope_component(current_load_mw, forecast_load_mw, capacity_mw),
        "voltage_stress": voltage_stress_component(voltage_pu),
        "headroom": headroom_component(current_load_mw, capacity_mw),
    }
    score01 = sum(components[k] * w[k] for k in w)
    score = float(np.clip(score01 * 100.0, 0.0, 100.0))
    return score, components


def classify_stress(score):
    """Maps a 0-100 score to LOW/MODERATE/HIGH/CRITICAL per STRESS_THRESHOLDS."""
    if not np.isfinite(score):
        raise ValueError(f"Stress score must be finite, got {score}")
    if score < 0 or score > 100:
        raise ValueError(f"Stress score must be in [0, 100], got {score}")
    if score <= STRESS_THRESHOLDS["LOW"][1]:
        return "LOW"
    if score <= STRESS_THRESHOLDS["MODERATE"][1]:
        return "MODERATE"
    if score <= STRESS_THRESHOLDS["HIGH"][1]:
        return "HIGH"
    return "CRITICAL"


# ---------------------------------------------------------------------------
# Time-to-overload
# ---------------------------------------------------------------------------
def time_to_overload(trajectory: pd.Series, capacity_mw):
    """
    Examines an hourly forecast trajectory (pd.Series indexed by timestamp,
    values in MW, as produced by feeder_generator.build_feeder_trajectories)
    and determines when predicted load first reaches/crosses capacity_mw.

    RESOLUTION LIMITATION: the underlying national demand trajectory is only
    available at hourly resolution (see feeder_generator.py docstring on
    build_national_trajectory) -- the trained model itself only produces one
    24h-ahead point per origin. The linear interpolation performed here
    between adjacent hourly points gives an hour-level ESTIMATE of the
    crossing time, not a minute-level or sub-hourly-accurate prediction. Do
    not present `crossing_time` as more precise than +/- ~1 hour.

    Returns a dict with:
      overload_predicted: bool
      time_to_overload_hours: float or None (hours from trajectory start to interpolated crossing)
      crossing_time: pd.Timestamp or None (interpolated)
      crossing_forecast_point: dict or None (the first hourly point at/over capacity)
      interpolated: bool
      resolution_note: str (always present, explains the hourly-resolution caveat)
    """
    resolution_note = ("Crossing time is linearly interpolated between adjacent hourly "
                        "trajectory points; the underlying national demand model only "
                        "produces hourly-resolution values, so this is an hour-level "
                        "estimate, not a sub-hourly-accurate prediction.")

    if len(trajectory) == 0:
        raise ValueError("trajectory must have at least one point")

    values = trajectory.values.astype(float)
    times = trajectory.index

    if not np.all(np.isfinite(values)):
        raise ValueError("trajectory contains NaN/inf values")
    if capacity_mw <= 0 or not np.isfinite(capacity_mw):
        raise ValueError(f"capacity_mw must be a positive finite number, got {capacity_mw}")

    over = values >= capacity_mw
    if not over.any():
        return {
            "overload_predicted": False,
            "time_to_overload_hours": None,
            "crossing_time": None,
            "crossing_forecast_point": None,
            "interpolated": False,
            "resolution_note": resolution_note,
        }

    first_idx = int(np.argmax(over))  # index of first True

    if first_idx == 0:
        # Already at/over capacity at the start of the trajectory.
        crossing_time = times[0]
        hours_to = 0.0
        interpolated = False
    else:
        t0, t1 = times[first_idx - 1], times[first_idx]
        v0, v1 = values[first_idx - 1], values[first_idx]
        if v1 == v0:
            frac = 0.0
        else:
            frac = (capacity_mw - v0) / (v1 - v0)
            frac = float(np.clip(frac, 0.0, 1.0))
        crossing_time = t0 + (t1 - t0) * frac
        hours_to = (crossing_time - times[0]).total_seconds() / 3600.0
        interpolated = True

    return {
        "overload_predicted": True,
        "time_to_overload_hours": float(hours_to),
        "crossing_time": crossing_time,
        "crossing_forecast_point": {
            "timestamp": str(times[first_idx]),
            "value_mw": float(values[first_idx]),
        },
        "interpolated": interpolated,
        "resolution_note": resolution_note,
    }


def evaluate_feeder(current_load_mw, forecast_load_mw, capacity_mw, voltage_pu,
                     trajectory: pd.Series = None, weights=None):
    """Convenience wrapper: computes stress score, classification, and
    (if a trajectory is supplied) time-to-overload for one feeder snapshot."""
    for name, val in [("current_load_mw", current_load_mw), ("forecast_load_mw", forecast_load_mw),
                       ("capacity_mw", capacity_mw), ("voltage_pu", voltage_pu)]:
        if not np.isfinite(val):
            raise ValueError(f"{name} must be finite, got {val}")

    score, components = compute_stress_score(current_load_mw, forecast_load_mw, capacity_mw, voltage_pu, weights)
    risk_level = classify_stress(score)
    result = {
        "stress_score": score,
        "risk_level": risk_level,
        "components": components,
        "weights_used": weights or STRESS_WEIGHTS,
    }
    if trajectory is not None:
        result["time_to_overload"] = time_to_overload(trajectory, capacity_mw)
    return result
