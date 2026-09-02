"""
GridGuard AI - Synthetic feeder simulation layer.

*** IMPORTANT: ALL FEEDER-LEVEL DATA PRODUCED BY THIS MODULE IS SYNTHETIC. ***
The Panama Mendeley dataset (ml/data/raw/continuous dataset.csv) contains only
NATIONAL aggregate electricity demand -- it has no real feeder-, substation-,
or location-level measurements. Panama's real distribution feeder topology,
loads, capacities, and voltages are NOT known to this project and are NOT
used here. Every feeder id, name, location, capacity, load value, and voltage
value produced by this module is a documented simulation for the purpose of
building and testing the GridGuard risk-scoring pipeline end-to-end. None of
it should ever be presented, logged, or displayed as real Panama feeder
telemetry.

This module does not retrain or modify the existing XGBoost demand model or
its feature pipeline (ml/src/build_features.py, ml/src/train_xgboost.py) --
it only *consumes* the already-saved model's predictions and the raw national
demand series to derive synthetic feeder-level scenarios.

Pipeline position:
    Panama national demand
            -> existing XGBoost 24h-ahead forecast (unchanged, reused as-is)
            -> THIS MODULE: synthetic feeder simulator
            -> F01-F10 feeder states/forecasts
            -> ml/src/stress_engine.py (Grid Stress Engine)
"""
import os
import json
import pickle

import numpy as np
import pandas as pd

SEED = 42  # fixed seed for full reproducibility of all synthetic feeder data

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
PROC_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")

# ---------------------------------------------------------------------------
# Coverage factor: what fraction of Panama's NATIONAL demand these 10
# synthetic feeders are assumed to jointly represent. This is an arbitrary,
# documented, easily-changed engineering choice (a "pilot deployment" of 10
# monitored feeders out of the whole national grid) -- NOT derived from any
# real feeder count or real distribution topology.
# ---------------------------------------------------------------------------
COVERAGE_FACTOR = 0.05  # 5% of national demand, nominally, before hourly/day-type reweighting

# Reference point only, for generating plausible-looking synthetic
# coordinates near Panama. NOT real feeder locations.
PANAMA_REFERENCE = {"lat": 8.9824, "lon": -79.5199}

FEEDER_TYPES = ["RESIDENTIAL", "COMMERCIAL", "INDUSTRIAL", "MIXED", "EV_HEAVY"]

# ---------------------------------------------------------------------------
# Documented hourly load-shape behavior per feeder type (raw, relative units,
# hour index 0-23). These are illustrative, hand-authored shapes reflecting
# widely-documented qualitative demand behavior for each customer class
# (e.g. residential evening peak, commercial daytime peak) -- they are NOT
# fit to any measured Panama feeder data (none exists in this project).
# ---------------------------------------------------------------------------
_RAW_HOURLY_SHAPE = {
    "RESIDENTIAL": [0.55, 0.50, 0.48, 0.47, 0.50, 0.60, 0.80, 0.95,
                    0.85, 0.75, 0.70, 0.68, 0.70, 0.70, 0.72, 0.78,
                    0.95, 1.15, 1.40, 1.50, 1.45, 1.25, 0.95, 0.70],
    "COMMERCIAL":  [0.35, 0.32, 0.30, 0.30, 0.32, 0.38, 0.55, 0.75,
                    1.10, 1.35, 1.45, 1.50, 1.50, 1.50, 1.48, 1.42,
                    1.20, 0.90, 0.60, 0.50, 0.45, 0.42, 0.40, 0.37],
    "INDUSTRIAL":  [0.92, 0.90, 0.90, 0.90, 0.90, 0.92, 0.98, 1.05,
                    1.10, 1.12, 1.12, 1.10, 1.08, 1.10, 1.12, 1.12,
                    1.10, 1.05, 1.00, 0.98, 0.96, 0.95, 0.94, 0.93],
    "EV_HEAVY":    [1.00, 0.95, 0.90, 0.88, 0.85, 0.85, 0.80, 0.75,
                    0.70, 0.68, 0.65, 0.65, 0.68, 0.70, 0.72, 0.78,
                    0.90, 1.10, 1.35, 1.55, 1.60, 1.50, 1.30, 1.10],
}
# MIXED = average of RESIDENTIAL and COMMERCIAL (documented as an
# intermediate behavior between the two, per the task's design intent).
_RAW_HOURLY_SHAPE["MIXED"] = [
    (r + c) / 2 for r, c in zip(_RAW_HOURLY_SHAPE["RESIDENTIAL"], _RAW_HOURLY_SHAPE["COMMERCIAL"])
]


def _normalize_mean_one(values):
    arr = np.asarray(values, dtype=float)
    return arr / arr.mean()


# Normalized so each type's 24-hour shape has mean exactly 1.0 -- this is
# what makes the allocation math in `_combined_multiplier` below preserve the
# aggregate-vs-national relationship documented in the module docstring.
HOURLY_SHAPE = {t: _normalize_mean_one(v) for t, v in _RAW_HOURLY_SHAPE.items()}

# ---------------------------------------------------------------------------
# Weekday multiplier per type (documented, hand-chosen). The weekend
# multiplier is SOLVED (not chosen) so that the time-weighted weekly average
# of (weekday_mult, weekend_mult) is exactly 1.0:
#   (5/7) * weekday_mult + (2/7) * weekend_mult = 1.0
# This guarantees that, combined with the mean-one hourly shape above, the
# expected value of the combined (shape x day-type) multiplier is exactly
# 1.0 averaged over any full 7-day window -- see allocation methodology in
# ml/reports/feeder_simulation_report.md for the full derivation.
# ---------------------------------------------------------------------------
_WEEKDAY_MULT = {
    "RESIDENTIAL": 0.98,  # slightly lower on workdays (people out at jobs/school)
    "COMMERCIAL": 1.15,   # busier on workdays
    "INDUSTRIAL": 1.05,   # most industrial activity happens on workdays
    "MIXED": 1.05,
    "EV_HEAVY": 1.05,     # commuter charging adds a modest workday bump
}


def _solve_weekend_mult(weekday_mult):
    return (1.0 - (5.0 / 7.0) * weekday_mult) / (2.0 / 7.0)


DAYTYPE_MULT = {
    t: {"weekday": wd, "weekend": _solve_weekend_mult(wd)}
    for t, wd in _WEEKDAY_MULT.items()
}

# ---------------------------------------------------------------------------
# Feeder definitions: 10 synthetic feeders (F01-F10). Locations are
# SIMULATED/DEMO coordinates near Panama for map-display purposes only --
# they do not correspond to any real substation or feeder location.
# `relative_weight` sets each feeder's share of COVERAGE_FACTOR relative to
# the others (normalized in `get_feeder_definitions`, not an absolute MW
# value). `capacity_margin` is the headroom multiplier applied to each
# feeder's historical peak synthetic load to derive its capacity_mw (see
# `compute_feeder_capacities`). F10's margin is deliberately set low
# (1.05) as a documented engineering choice so at least one feeder exercises
# HIGH/CRITICAL stress scenarios in examples and tests -- this is a scenario
# design choice, not a data-fabrication of a real overloaded feeder.
# ---------------------------------------------------------------------------
FEEDER_DEFINITIONS = [
    {"id": "F01", "name": "Panama City Residential North", "type": "RESIDENTIAL",
     "location": {"lat": 9.05, "lon": -79.52}, "relative_weight": 1.2, "capacity_margin": 1.25},
    {"id": "F02", "name": "San Miguelito Residential", "type": "RESIDENTIAL",
     "location": {"lat": 9.03, "lon": -79.50}, "relative_weight": 1.0, "capacity_margin": 1.20},
    {"id": "F03", "name": "Panama City Commercial Core", "type": "COMMERCIAL",
     "location": {"lat": 8.98, "lon": -79.53}, "relative_weight": 1.4, "capacity_margin": 1.15},
    {"id": "F04", "name": "Costa del Este Business Park", "type": "COMMERCIAL",
     "location": {"lat": 9.00, "lon": -79.48}, "relative_weight": 1.1, "capacity_margin": 1.20},
    {"id": "F05", "name": "Colon Free Zone Industrial A", "type": "INDUSTRIAL",
     "location": {"lat": 9.36, "lon": -79.90}, "relative_weight": 1.8, "capacity_margin": 1.15},
    {"id": "F06", "name": "Panama Pacifico Industrial B", "type": "INDUSTRIAL",
     "location": {"lat": 8.92, "lon": -79.60}, "relative_weight": 1.6, "capacity_margin": 1.10},
    {"id": "F07", "name": "Arraijan Mixed Suburban", "type": "MIXED",
     "location": {"lat": 8.95, "lon": -79.66}, "relative_weight": 1.0, "capacity_margin": 1.25},
    {"id": "F08", "name": "La Chorrera Mixed Fringe", "type": "MIXED",
     "location": {"lat": 8.88, "lon": -79.78}, "relative_weight": 0.8, "capacity_margin": 1.30},
    {"id": "F09", "name": "Via Espana EV Corridor", "type": "EV_HEAVY",
     "location": {"lat": 8.99, "lon": -79.52}, "relative_weight": 0.6, "capacity_margin": 1.10},
    {"id": "F10", "name": "Tocumen EV Depot", "type": "EV_HEAVY",
     "location": {"lat": 9.07, "lon": -79.38}, "relative_weight": 0.4, "capacity_margin": 1.05},
]

for _f in FEEDER_DEFINITIONS:
    assert _f["type"] in FEEDER_TYPES
    _f["location"]["note"] = "SIMULATED coordinate for demo/mapping purposes only -- not a real feeder location."


def get_feeder_definitions():
    """Returns the 10 feeder definitions with `base_share` computed so that
    sum(base_share) == COVERAGE_FACTOR exactly, distributed proportionally
    to each feeder's `relative_weight`."""
    total_weight = sum(f["relative_weight"] for f in FEEDER_DEFINITIONS)
    feeders = []
    for f in FEEDER_DEFINITIONS:
        feeder = dict(f)
        feeder["base_share"] = COVERAGE_FACTOR * f["relative_weight"] / total_weight
        feeders.append(feeder)
    return feeders


def _combined_multiplier(feeder_type, dt_index):
    """shape(hour) x daytype(weekday/weekend); expected value 1.0 over any
    full 7-day window (see module docstring for derivation)."""
    hours = np.asarray(dt_index.hour)
    shape = HOURLY_SHAPE[feeder_type][hours]
    is_weekend = np.isin(np.asarray(dt_index.dayofweek), [5, 6])
    daytype = np.where(is_weekend, DAYTYPE_MULT[feeder_type]["weekend"], DAYTYPE_MULT[feeder_type]["weekday"])
    return shape * daytype


# ---------------------------------------------------------------------------
# National-to-feeder allocation
# ---------------------------------------------------------------------------
def allocate_feeder_loads(national_demand: pd.Series, feeders=None, seed=SEED,
                           noise_sigma=0.05, noise_cap=0.20, add_noise=True) -> pd.DataFrame:
    """
    Allocates national demand to each feeder as:

        raw_i(t) = national_demand(t) * base_share_i * shape_i(hour(t)) * daytype_i(is_weekend(t))
        feeder_load_i(t) = max(raw_i(t) * (1 + eps_i(t)), 0)

    where eps_i(t) ~ clipped Normal(0, noise_sigma) is bounded, reproducible,
    per-feeder noise (independent RNG stream per feeder, seeded from `seed`).
    Feeder load is therefore always non-negative (national_demand >= 0,
    base_share >= 0, shape/daytype > 0, and (1+eps) is clipped to
    [1-noise_cap, 1+noise_cap] > 0 for noise_cap < 1) and depends on national
    demand, hour of day, day of week, feeder type/profile, and bounded random
    variation -- never generated independently of the national signal.

    Set add_noise=False to get the deterministic *expected* allocation (used
    for forward-looking forecast trajectories, where injecting fresh random
    noise into a forecast would be misleading).
    """
    if feeders is None:
        feeders = get_feeder_definitions()
    dt_index = national_demand.index
    records = {}
    for i, f in enumerate(feeders):
        mult = _combined_multiplier(f["type"], dt_index)
        raw = national_demand.values * f["base_share"] * mult
        if add_noise:
            feeder_rng = np.random.default_rng(seed + i + 1)  # distinct stream per feeder, reproducible
            eps = np.clip(feeder_rng.normal(0.0, noise_sigma, size=len(dt_index)), -noise_cap, noise_cap)
            load = raw * (1.0 + eps)
        else:
            load = raw
        records[f["id"]] = np.clip(load, 0.0, None)
    return pd.DataFrame(records, index=dt_index)


def compute_feeder_capacities(feeders, historical_feeder_loads: pd.DataFrame) -> pd.DataFrame:
    """capacity_mw_i = capacity_margin_i * max(historical synthetic load_i).
    Uses the full historical allocation (see module docstring: this is the
    synthetic series, not a real measured feeder history) as the reference
    period for sizing each feeder's nominal capacity."""
    rows = []
    for f in feeders:
        hist_max = float(historical_feeder_loads[f["id"]].max())
        capacity = hist_max * f["capacity_margin"]
        rows.append({
            "id": f["id"], "name": f["name"], "type": f["type"], "location": f["location"],
            "base_share": f["base_share"], "capacity_margin": f["capacity_margin"],
            "historical_max_load_mw": hist_max, "capacity_mw": capacity,
        })
    return pd.DataFrame(rows).set_index("id")


# ---------------------------------------------------------------------------
# Forecast trajectory construction
#
# IMPORTANT LIMITATION: the saved XGBoost model (ml/models/demand_xgboost.pkl)
# was trained and evaluated for a SINGLE fixed 24-hour-ahead horizon (see
# ml/reports/model_evaluation.md). It produces exactly ONE forecast point per
# origin timestamp -- it does NOT produce a per-hour trajectory for hours
# 1..23. The functions below build an ENGINEERED, hourly-resolution
# trajectory between the real current value (h=0) and the single real model
# forecast (h=24), using the historical average diurnal demand shape purely
# as an interpolation curve so the trajectory looks like a plausible intraday
# path. This is clearly an approximation for simulation/visualization
# purposes, not independent model output at each intermediate hour, and must
# never be described as "the model forecasts hour-by-hour."
# ---------------------------------------------------------------------------
def historical_average_hourly_shape(national_demand: pd.Series) -> np.ndarray:
    """Mean nat_demand by hour-of-day (length-24 array, index 0-23), computed
    from the full raw historical series. Used only as an interpolation shape,
    see caveat above."""
    return national_demand.groupby(national_demand.index.hour).mean().reindex(range(24)).values


def build_national_trajectory(origin_dt, current_national_demand, forecast_24h_national_demand,
                               avg_hourly_shape, n_hours=24):
    """
    Returns an hourly pd.Series (h=0..n_hours, length n_hours+1) that:
      - equals `current_national_demand` exactly at h=0 (a real observed value)
      - equals `forecast_24h_national_demand` exactly at h=n_hours=24 (the
        real, single XGBoost forecast point)
      - follows the historical average diurnal shape in between.

    Because n_hours=24 (the model's fixed horizon), h=0 and h=24 fall on the
    SAME hour-of-day, so this reduces to a clean shape-preserving blend:
    scale(h) moves linearly from (current / shape_at_origin_hour) to
    (forecast / shape_at_origin_hour) as h goes 0 -> 24.

    See module docstring: intermediate points (h=1..23) are an engineered
    interpolation, not independent model predictions.
    """
    origin_hour = origin_dt.hour

    def shape_at(h):
        return avg_hourly_shape[(origin_hour + h) % 24]

    shape0 = shape_at(0)
    values, timestamps = [], []
    for h in range(0, n_hours + 1):
        frac = h / n_hours
        scale = (1 - frac) * (current_national_demand / shape0) + frac * (forecast_24h_national_demand / shape0)
        values.append(max(shape_at(h) * scale, 0.0))
        timestamps.append(origin_dt + pd.Timedelta(hours=h))
    return pd.Series(values, index=pd.DatetimeIndex(timestamps, name="datetime"), name="national_demand_trajectory")


def build_feeder_trajectories(national_trajectory: pd.Series, feeders) -> pd.DataFrame:
    """Deterministic (noise-free) allocation of the national trajectory to
    each feeder, using the same allocation formula as `allocate_feeder_loads`
    with add_noise=False -- appropriate for a forward-looking expected
    trajectory rather than a historical/actual value."""
    return allocate_feeder_loads(national_trajectory, feeders, add_noise=False)


# ---------------------------------------------------------------------------
# Voltage simulation
#
# NOT measured or physically simulated (no power-flow model). A simplified,
# explicitly documented linear approximation: voltage sags roughly linearly
# with utilization above a "no-drop" threshold, loosely inspired by the
# qualitative behavior of real distribution feeders under load, with small
# bounded random noise. This is illustrative only.
# ---------------------------------------------------------------------------
VOLTAGE_MODEL = {
    "nominal_pu": 1.02,      # per-unit voltage at zero/low load
    "no_drop_utilization": 0.5,  # utilization below which no drop is modeled
    "drop_coefficient": 0.10,    # pu drop per unit of utilization above no_drop_utilization
    "noise_std_pu": 0.003,
    "min_pu": 0.85,
    "max_pu": 1.05,
}


def simulate_voltage(utilization: np.ndarray, seed=SEED, add_noise=True) -> np.ndarray:
    """voltage_pu = nominal - drop_coefficient * max(utilization - no_drop_utilization, 0) + noise,
    clipped to [min_pu, max_pu]. See VOLTAGE_MODEL for parameters. NOT real/measured voltage."""
    util = np.clip(np.asarray(utilization, dtype=float), 0.0, None)
    excess = np.clip(util - VOLTAGE_MODEL["no_drop_utilization"], 0.0, None)
    voltage = VOLTAGE_MODEL["nominal_pu"] - VOLTAGE_MODEL["drop_coefficient"] * excess
    if add_noise:
        rng = np.random.default_rng(seed + 9999)
        voltage = voltage + rng.normal(0.0, VOLTAGE_MODEL["noise_std_pu"], size=voltage.shape)
    return np.clip(voltage, VOLTAGE_MODEL["min_pu"], VOLTAGE_MODEL["max_pu"])


# ---------------------------------------------------------------------------
# End-to-end example: national demand -> existing XGBoost forecast ->
# synthetic feeders -> forecast trajectories -> utilization/voltage.
# Does not retrain or alter the model in any way; loads it read-only.
# ---------------------------------------------------------------------------
def load_national_demand_series() -> pd.Series:
    df = pd.read_csv(os.path.join(RAW_DIR, "continuous dataset.csv"))
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").set_index("datetime")
    return df["nat_demand"]


def load_saved_model_and_features():
    with open(os.path.join(MODELS_DIR, "model_metadata.json"), encoding="utf-8") as f:
        model_meta = json.load(f)
    with open(os.path.join(MODELS_DIR, "demand_xgboost.pkl"), "rb") as f:
        model = pickle.load(f)
    assert list(model.get_booster().feature_names) == model_meta["feature_list"], \
        "Loaded model's feature names do not match model_metadata.json"
    features_full = pd.read_csv(os.path.join(PROC_DIR, "features_full.csv"))
    features_full["origin_datetime"] = pd.to_datetime(features_full["origin_datetime"])
    return model, model_meta, features_full


def run_example(origin_datetime_str=None, seed=SEED):
    """Builds one end-to-end example: picks a forecast origin from the
    existing processed feature table, gets the real current value and the
    real saved-model 24h-ahead forecast, builds the engineered national
    trajectory, allocates it to the 10 synthetic feeders, and computes
    utilization + simulated voltage for each. Returns a plain dict (JSON-
    serializable) describing the full result."""
    national_demand = load_national_demand_series()
    model, model_meta, features_full = load_saved_model_and_features()
    feature_cols = model_meta["feature_list"]

    if origin_datetime_str is None:
        row = features_full.iloc[-1]
    else:
        target_dt = pd.Timestamp(origin_datetime_str)
        row = features_full.loc[features_full["origin_datetime"] == target_dt].iloc[0]

    origin_dt = row["origin_datetime"]
    current_national_demand = float(row["lag_0h_nat_demand"])
    X_row = row[feature_cols].to_frame().T.astype(float)
    forecast_24h_national_demand = float(model.predict(X_row)[0])

    avg_hourly_shape = historical_average_hourly_shape(national_demand)
    national_traj = build_national_trajectory(origin_dt, current_national_demand,
                                                forecast_24h_national_demand, avg_hourly_shape)

    feeders = get_feeder_definitions()
    historical_feeder_loads = allocate_feeder_loads(national_demand, feeders, seed=seed, add_noise=True)
    capacities = compute_feeder_capacities(feeders, historical_feeder_loads)

    feeder_traj = build_feeder_trajectories(national_traj, feeders)

    result = {
        "SYNTHETIC_DATA_WARNING": "All feeder-level values below are SIMULATED, not real Panama feeder measurements.",
        "origin_datetime": str(origin_dt),
        "current_national_demand_mw": current_national_demand,
        "forecast_24h_national_demand_mw": forecast_24h_national_demand,
        "coverage_factor": COVERAGE_FACTOR,
        "seed": seed,
        "feeders": {},
    }
    for f in feeders:
        fid = f["id"]
        cap = float(capacities.loc[fid, "capacity_mw"])
        traj = feeder_traj[fid]
        current_load = float(traj.iloc[0])
        forecast_load = float(traj.iloc[-1])
        utilization_traj = (traj / cap).clip(upper=None)
        voltage_traj = simulate_voltage(utilization_traj.values, seed=seed, add_noise=False)
        result["feeders"][fid] = {
            "name": f["name"], "type": f["type"], "location": f["location"],
            "capacity_mw": cap,
            "current_load_mw": current_load,
            "forecast_load_mw_24h": forecast_load,
            "current_utilization": float(current_load / cap),
            "forecast_utilization_24h": float(forecast_load / cap),
            "current_voltage_pu": float(voltage_traj[0]),
            "forecast_voltage_pu_24h": float(voltage_traj[-1]),
            "trajectory_mw": [float(v) for v in traj.values],
            "trajectory_timestamps": [str(t) for t in traj.index],
        }
    return result


if __name__ == "__main__":
    example = run_example()
    out_path = os.path.join(REPORTS_DIR, "feeder_example_output.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(example, f, indent=2, default=str)
    print(f"Saved example feeder output: {out_path}")
    for fid, fdata in example["feeders"].items():
        print(f"{fid} ({fdata['type']}): current={fdata['current_load_mw']:.2f} MW "
              f"({fdata['current_utilization']*100:.1f}% of {fdata['capacity_mw']:.2f} MW), "
              f"24h forecast={fdata['forecast_load_mw_24h']:.2f} MW "
              f"({fdata['forecast_utilization_24h']*100:.1f}%)")
