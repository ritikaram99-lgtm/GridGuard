"""
GridGuard AI - Controlled stress-engine scenario validation.

Follow-up to ml/reports/stress_engine_sanity.md Section 8: the natural 2020
historical rolling window never produced HIGH-band, CRITICAL, overload, or
voltage-stress-activated observations (utilization never exceeded ~89.5%).
This script DELIBERATELY CONSTRUCTS controlled scenarios -- elevated demand,
tight capacity, explicit overload trajectories, near-capacity utilization,
and extreme utilization for voltage-stress activation -- to check whether
those paths behave sensibly when they DO occur.

Uses the existing, UNMODIFIED feeder_generator.py and stress_engine.py only.
Does not retrain the model, touch the feature pipeline, or change any
formula/threshold/weight in stress_engine.py or feeder_generator.py.

*** ALL SCENARIOS BELOW ARE DELIBERATELY CONSTRUCTED SIMULATION INPUTS. ***
None of them are real Panama feeder events, historical overloads, or real
outage data. They exist only to verify the GridGuard pipeline's mechanics
behave correctly when dangerous conditions occur -- not to claim such
conditions were observed or are validated against reality.
"""
import os
import sys
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import feeder_generator as fg
import stress_engine as se

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
FIG_DIR = os.path.join(REPORTS_DIR, "figures", "stress_scenarios")
os.makedirs(FIG_DIR, exist_ok=True)

SEED = fg.SEED


def make_linear_trajectory(start_dt, current_mw, forecast_mw, n_hours=24):
    """Explicitly constructed hourly trajectory, linear from current_mw (h=0)
    to forecast_mw (h=n_hours). Used only for these controlled scenarios --
    NOT the same as feeder_generator's diurnal-shaped interpolation, and not
    claimed to be. A deliberately simple, transparent construction so the
    expected crossing point can be computed by hand and compared."""
    values = np.linspace(current_mw, forecast_mw, n_hours + 1)
    times = pd.date_range(start_dt, periods=n_hours + 1, freq="h")
    return pd.Series(values, index=times)


def evaluate_scenario(name, description, current_load_mw, forecast_load_mw, capacity_mw, trajectory=None):
    # voltage must be derived from utilization via the existing unmodified voltage model
    util_current = current_load_mw / capacity_mw
    voltage_pu = float(fg.simulate_voltage(np.array([util_current]), seed=SEED, add_noise=False)[0])
    score, components = se.compute_stress_score(current_load_mw, forecast_load_mw, capacity_mw, voltage_pu)
    risk = se.classify_stress(score)
    tto = se.time_to_overload(trajectory, capacity_mw) if trajectory is not None else None

    row = {
        "scenario": name,
        "description": description,
        "current_load_mw": current_load_mw,
        "capacity_mw": capacity_mw,
        "current_utilization": current_load_mw / capacity_mw,
        "forecast_load_mw": forecast_load_mw,
        "forecast_utilization": forecast_load_mw / capacity_mw,
        "trajectory_slope_component": components["trajectory_slope"],
        "voltage_pu": voltage_pu,
        "voltage_stress_component": components["voltage_stress"],
        "current_utilization_component": components["current_utilization"],
        "forecast_utilization_component": components["forecast_utilization"],
        "headroom_component": components["headroom"],
        "stress_score": score,
        "risk_level": risk,
        "overload_predicted": tto["overload_predicted"] if tto else None,
        "time_to_overload_hours": tto["time_to_overload_hours"] if tto else None,
        "resolution_note": tto["resolution_note"] if tto else None,
    }
    return row


# ---------------------------------------------------------------------------
# Baseline: a real feeder state from the existing, unmodified pipeline
# (feeder_generator.run_example's default origin = most recent available row).
# ---------------------------------------------------------------------------
print("Loading baseline real feeder state via feeder_generator.run_example() (unmodified)...")
baseline_example = fg.run_example()
feeders = fg.get_feeder_definitions()
feeder_ids = [f["id"] for f in feeders]
feeder_types = {f["id"]: f["type"] for f in feeders}

print(f"Baseline origin: {baseline_example['origin_datetime']}")
for fid in feeder_ids:
    fd = baseline_example["feeders"][fid]
    print(f"  {fid} ({fd['type']}): current={fd['current_load_mw']:.2f} MW / cap={fd['capacity_mw']:.2f} MW "
          f"({fd['current_utilization']*100:.1f}%)")

all_rows = []

# ===========================================================================
# A-D: demand elevation scenarios, ALL 10 feeders
# National/feeder demand multiplied by 1.00 / 1.10 / 1.20 / 1.30, capacity
# held fixed at each feeder's real (unmodified feeder_generator) capacity.
# ===========================================================================
print("\n" + "=" * 80)
print("Scenarios A-D: demand elevation (all 10 feeders)")
print("=" * 80)

DEMAND_MULTIPLIERS = {"A_NORMAL": 1.00, "B_ELEVATED_+10%": 1.10, "C_ELEVATED_+20%": 1.20, "D_ELEVATED_+30%": 1.30}

elevation_rows = []
for fid in feeder_ids:
    fd = baseline_example["feeders"][fid]
    cap = fd["capacity_mw"]
    base_current = fd["current_load_mw"]
    base_forecast = fd["forecast_load_mw_24h"]
    for label, mult in DEMAND_MULTIPLIERS.items():
        current = base_current * mult
        forecast = base_forecast * mult
        traj = make_linear_trajectory(baseline_example["origin_datetime"], current, forecast)
        row = evaluate_scenario(f"{label}", f"Feeder {fid} demand x{mult:.2f} (capacity fixed)",
                                 current, forecast, cap, trajectory=traj)
        row["feeder_id"] = fid
        row["feeder_type"] = feeder_types[fid]
        row["multiplier"] = mult
        elevation_rows.append(row)
        all_rows.append(row)

elevation_df = pd.DataFrame(elevation_rows)
print(elevation_df[["feeder_id", "scenario", "current_utilization", "stress_score", "risk_level", "overload_predicted"]]
      .to_string(index=False))

# Verify: increasing demand increases stress, per feeder, monotonically across A->D
monotonic_ok = True
for fid in feeder_ids:
    sub = elevation_df[elevation_df["feeder_id"] == fid].sort_values("multiplier")
    diffs = np.diff(sub["stress_score"].values)
    if not np.all(diffs >= -1e-9):
        monotonic_ok = False
        print(f"  VIOLATION: {fid} stress score not monotonic non-decreasing across demand elevation!")
print(f"\nIncreasing demand increases (never decreases) stress score, per feeder: {monotonic_ok}")

high_occurred = (elevation_df["risk_level"] == "HIGH").any()
critical_occurred = (elevation_df["risk_level"] == "CRITICAL").any()
overload_occurred_elevation = (elevation_df["overload_predicted"] == True).any()
print(f"HIGH occurred in elevation scenarios: {high_occurred}")
print(f"CRITICAL occurred in elevation scenarios: {critical_occurred}")
print(f"Overload predicted in elevation scenarios: {overload_occurred_elevation}")

# ===========================================================================
# E: TIGHT_CAPACITY -- load fixed at baseline, capacity deliberately reduced
# ===========================================================================
print("\n" + "=" * 80)
print("Scenario E: TIGHT_CAPACITY (representative feeder F10, load fixed)")
print("=" * 80)

REP_FEEDER = "F10"  # tightest real capacity_margin (1.05) among the 10 -- see feeder_simulation_report.md
rep = baseline_example["feeders"][REP_FEEDER]
base_current_rep = rep["current_load_mw"]
base_forecast_rep = rep["forecast_load_mw_24h"]
real_capacity_rep = rep["capacity_mw"]

tight_capacity = base_current_rep * 1.05  # deliberately only 5% headroom above the CURRENT load, regardless of feeder_generator's own capacity
traj_e = make_linear_trajectory(baseline_example["origin_datetime"], base_current_rep, base_forecast_rep)
row_e = evaluate_scenario("E_TIGHT_CAPACITY", f"Feeder {REP_FEEDER}: load fixed at baseline, capacity artificially reduced to 1.05x current load",
                           base_current_rep, base_forecast_rep, tight_capacity, trajectory=traj_e)
row_e["feeder_id"] = REP_FEEDER
row_e["feeder_type"] = feeder_types[REP_FEEDER]
all_rows.append(row_e)
print(f"Load fixed at {base_current_rep:.2f} MW; capacity changed from real {real_capacity_rep:.2f} MW -> {tight_capacity:.2f} MW")
print(f"Result: utilization={row_e['current_utilization']:.3f}, score={row_e['stress_score']:.2f}, risk={row_e['risk_level']}")

# ===========================================================================
# F: OVERLOAD -- explicit forecast trajectory that crosses capacity
# ===========================================================================
print("\n" + "=" * 80)
print("Scenario F: OVERLOAD (representative feeder F10)")
print("=" * 80)

overload_current = real_capacity_rep * 0.60
overload_forecast = real_capacity_rep * 1.40
traj_f = make_linear_trajectory(baseline_example["origin_datetime"], overload_current, overload_forecast)
row_f = evaluate_scenario("F_OVERLOAD", f"Feeder {REP_FEEDER}: explicit linear trajectory 0.60x capacity -> 1.40x capacity over 24h",
                           overload_current, overload_forecast, real_capacity_rep, trajectory=traj_f)
row_f["feeder_id"] = REP_FEEDER
row_f["feeder_type"] = feeder_types[REP_FEEDER]
all_rows.append(row_f)

# Expected crossing point (algebraic, since the trajectory is exactly linear):
# value(h) = overload_current + (overload_forecast - overload_current) * h/24 = capacity
# => h = 24 * (capacity - overload_current) / (overload_forecast - overload_current)
expected_crossing_h = 24 * (real_capacity_rep - overload_current) / (overload_forecast - overload_current)
actual_crossing_h = row_f["time_to_overload_hours"]
print(f"Trajectory: {overload_current:.2f} MW -> {overload_forecast:.2f} MW over 24h, capacity={real_capacity_rep:.2f} MW")
print(f"Expected crossing (algebraic): h={expected_crossing_h:.4f}")
print(f"Function-reported time_to_overload_hours: {actual_crossing_h:.4f}")
print(f"Match within 0.01h: {abs(expected_crossing_h - actual_crossing_h) < 0.01}")
print(f"overload_predicted: {row_f['overload_predicted']}, risk_level: {row_f['risk_level']}, score: {row_f['stress_score']:.2f}")

# ===========================================================================
# G: HIGH_UTILIZATION -- feeder constructed near (but not over) capacity
# ===========================================================================
print("\n" + "=" * 80)
print("Scenario G: HIGH_UTILIZATION (representative feeder F10)")
print("=" * 80)

near_cap_current = real_capacity_rep * 0.97
near_cap_forecast = real_capacity_rep * 0.99
traj_g = make_linear_trajectory(baseline_example["origin_datetime"], near_cap_current, near_cap_forecast)
row_g = evaluate_scenario("G_HIGH_UTILIZATION", f"Feeder {REP_FEEDER}: current=0.97x capacity, forecast=0.99x capacity (near, not over)",
                           near_cap_current, near_cap_forecast, real_capacity_rep, trajectory=traj_g)
row_g["feeder_id"] = REP_FEEDER
row_g["feeder_type"] = feeder_types[REP_FEEDER]
all_rows.append(row_g)
print(f"Result: utilization={row_g['current_utilization']:.3f}, score={row_g['stress_score']:.2f}, risk={row_g['risk_level']}, "
      f"overload_predicted={row_g['overload_predicted']}")

# ===========================================================================
# H: VOLTAGE_STRESS -- extreme utilization to push the (unmodified) voltage
# model past its 0.95pu activation threshold. Two sub-cases: partial and
# saturated activation.
# ===========================================================================
print("\n" + "=" * 80)
print("Scenario H: VOLTAGE_STRESS (representative feeder F10)")
print("=" * 80)

voltage_scenarios = {
    "H1_VOLTAGE_STRESS_PARTIAL": 1.30,  # utilization 130% -> partial voltage sag below 0.95pu threshold
    "H2_VOLTAGE_STRESS_SATURATED": 1.70,  # utilization 170% -> full voltage_stress=1.0 (at/below 0.90pu critical limit)
}
for label, mult in voltage_scenarios.items():
    v_current = real_capacity_rep * mult
    v_forecast = real_capacity_rep * mult
    traj_h = make_linear_trajectory(baseline_example["origin_datetime"], v_current, v_forecast)
    row_h = evaluate_scenario(label, f"Feeder {REP_FEEDER}: load held constant at {mult:.2f}x capacity (deliberately >100%) to activate voltage model",
                               v_current, v_forecast, real_capacity_rep, trajectory=traj_h)
    row_h["feeder_id"] = REP_FEEDER
    row_h["feeder_type"] = feeder_types[REP_FEEDER]
    all_rows.append(row_h)
    print(f"{label}: utilization={row_h['current_utilization']:.3f} (raw, pre-clip {mult:.2f}), "
          f"voltage_pu={row_h['voltage_pu']:.4f}, voltage_stress_component={row_h['voltage_stress_component']:.4f}, "
          f"score={row_h['stress_score']:.2f}, risk={row_h['risk_level']}")

voltage_stress_activated = any(r["voltage_stress_component"] > 0 for r in all_rows if r["scenario"].startswith("H"))
print(f"\nVoltage stress component activates (>0) in at least one H scenario: {voltage_stress_activated}")

# ===========================================================================
# Section 3: three controlled time-to-overload trajectories
# ===========================================================================
print("\n" + "=" * 80)
print("Section 3: controlled time-to-overload trajectories (representative capacity = F10's real capacity)")
print("=" * 80)

cap_ref = real_capacity_rep
start_dt = baseline_example["origin_datetime"]

# 1. Never crosses capacity
traj_never = make_linear_trajectory(start_dt, cap_ref * 0.40, cap_ref * 0.55)  # stays well below capacity throughout
tto_never = se.time_to_overload(traj_never, cap_ref)
print(f"1. NEVER_CROSSES (0.40x -> 0.55x capacity): overload_predicted={tto_never['overload_predicted']}, "
      f"time_to_overload_hours={tto_never['time_to_overload_hours']}")
assert tto_never["overload_predicted"] is False
assert tto_never["time_to_overload_hours"] is None

# 2. Crosses capacity exactly halfway through the horizon (by construction: 0.5x -> 1.5x capacity, linear, crosses at h=12)
traj_half = make_linear_trajectory(start_dt, cap_ref * 0.50, cap_ref * 1.50)
tto_half = se.time_to_overload(traj_half, cap_ref)
expected_half_h = 24 * (cap_ref - cap_ref * 0.50) / (cap_ref * 1.50 - cap_ref * 0.50)  # = 12.0 algebraically
print(f"2. CROSSES_HALFWAY (0.50x -> 1.50x capacity): overload_predicted={tto_half['overload_predicted']}, "
      f"time_to_overload_hours={tto_half['time_to_overload_hours']:.4f} (expected {expected_half_h:.4f})")
assert tto_half["overload_predicted"] is True
assert abs(tto_half["time_to_overload_hours"] - expected_half_h) < 0.01
assert abs(tto_half["time_to_overload_hours"] - 12.0) < 0.01

# 3. Starts already above capacity
traj_already = make_linear_trajectory(start_dt, cap_ref * 1.10, cap_ref * 1.30)
tto_already = se.time_to_overload(traj_already, cap_ref)
print(f"3. ALREADY_OVER (1.10x -> 1.30x capacity, over from h=0): overload_predicted={tto_already['overload_predicted']}, "
      f"time_to_overload_hours={tto_already['time_to_overload_hours']}, interpolated={tto_already['interpolated']}")
assert tto_already["overload_predicted"] is True
assert tto_already["time_to_overload_hours"] == 0.0
assert tto_already["interpolated"] is False

tto_section3 = {
    "never_crosses": tto_never, "crosses_halfway": tto_half, "already_over": tto_already,
    "expected_halfway_crossing_h": expected_half_h,
}

# ===========================================================================
# Assemble full results table, run global validation checks
# ===========================================================================
results_df = pd.DataFrame(all_rows)
results_df.to_csv(os.path.join(REPORTS_DIR, "..", "data", "stress_scenario_results.csv"), index=False)

print("\n" + "=" * 80)
print("2. Global validation checks across ALL scenarios")
print("=" * 80)

numeric_check_cols = ["stress_score", "current_utilization", "forecast_utilization", "voltage_pu"]
finite_ok = np.isfinite(results_df[numeric_check_cols].values).all()
print(f"No NaN/inf in stress_score/utilization/voltage across all {len(results_df)} scenario rows: {finite_ok}")

bounded_ok = results_df["stress_score"].between(0, 100).all()
print(f"stress_score bounded [0,100] across all scenarios: {bounded_ok}")

high_ever = (results_df["risk_level"] == "HIGH").any()
critical_ever = (results_df["risk_level"] == "CRITICAL").any()
overload_ever = (results_df["overload_predicted"] == True).any()
print(f"HIGH occurs somewhere in these scenarios: {high_ever}")
print(f"CRITICAL occurs somewhere in these scenarios: {critical_ever}")
print(f"Overload detection activates somewhere in these scenarios: {overload_ever}")
print(f"Voltage stress activates somewhere in these scenarios: {voltage_stress_activated}")

assert finite_ok, "Non-finite values found in scenario results!"
assert bounded_ok, "stress_score out of [0,100] bounds found!"

print("\nFull scenario table:")
print(results_df[["scenario", "feeder_id", "current_utilization", "forecast_utilization",
                   "voltage_pu", "voltage_stress_component", "stress_score", "risk_level",
                   "overload_predicted", "time_to_overload_hours"]].to_string(index=False))

# ===========================================================================
# Plots
# ===========================================================================
print("\nGenerating plots...")

# Demand elevation: stress score by feeder across A-D
fig, ax = plt.subplots(figsize=(10, 6))
for fid in feeder_ids:
    sub = elevation_df[elevation_df["feeder_id"] == fid].sort_values("multiplier")
    ax.plot(sub["multiplier"], sub["stress_score"], marker="o", label=fid)
for edge, lbl in [(30, "LOW/MODERATE"), (60, "MODERATE/HIGH"), (80, "HIGH/CRITICAL")]:
    ax.axhline(edge, color="gray", linestyle="--", alpha=0.4)
ax.set_xlabel("Demand multiplier")
ax.set_ylabel("Stress score")
ax.set_title("Scenarios A-D: Stress Score vs. Demand Multiplier, by Feeder\n(SIMULATED scenario inputs, not real feeder events)")
ax.legend(ncol=2, fontsize=8)
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "demand_elevation_stress_by_feeder.png"), dpi=120)
plt.close(fig)

# Voltage scenarios: utilization vs voltage_pu and voltage_stress_component
util_sweep = np.linspace(0, 2.0, 200)
voltage_sweep = fg.simulate_voltage(util_sweep, seed=SEED, add_noise=False)
voltage_stress_sweep = [se.voltage_stress_component(v) for v in voltage_sweep]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
ax1.plot(util_sweep, voltage_sweep)
ax1.axhline(se.VOLTAGE_STRESS_PARAMS["low_limit_pu"], color="orange", linestyle="--", label="low_limit (0.95pu)")
ax1.axhline(se.VOLTAGE_STRESS_PARAMS["critical_limit_pu"], color="red", linestyle="--", label="critical_limit (0.90pu)")
for label, mult in voltage_scenarios.items():
    ax1.axvline(mult, color="green", linestyle=":", alpha=0.7)
ax1.set_xlabel("Utilization (load / capacity)")
ax1.set_ylabel("Simulated voltage (pu)")
ax1.set_title("Voltage Model: Utilization -> Voltage")
ax1.legend(fontsize=8)

ax2.plot(util_sweep, voltage_stress_sweep, color="darkred")
for label, mult in voltage_scenarios.items():
    ax2.axvline(mult, color="green", linestyle=":", alpha=0.7)
ax2.set_xlabel("Utilization (load / capacity)")
ax2.set_ylabel("voltage_stress component [0,1]")
ax2.set_title("Voltage Stress Component Activation (H1, H2 scenarios marked)")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "voltage_stress_activation.png"), dpi=120)
plt.close(fig)

# Overload trajectory plot (scenario F)
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(traj_f.index, traj_f.values, marker="o", markersize=3, label="Scenario F trajectory (constructed)")
ax.axhline(real_capacity_rep, color="red", linestyle="--", label=f"Capacity ({real_capacity_rep:.2f} MW)")
if row_f["overload_predicted"]:
    crossing_dt = pd.Timestamp(start_dt) + pd.Timedelta(hours=actual_crossing_h)
    ax.axvline(crossing_dt, color="purple", linestyle=":", label=f"Detected crossing (h={actual_crossing_h:.2f})")
ax.set_title(f"Scenario F: OVERLOAD — Constructed Trajectory Crossing Capacity\n(SIMULATED input, feeder {REP_FEEDER})")
ax.set_ylabel("Load (MW)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "overload_trajectory_scenario_f.png"), dpi=120)
plt.close(fig)

# Section 3: three time-to-overload trajectories overlay
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(traj_never.index, traj_never.values, marker="o", markersize=3, label="1. Never crosses")
ax.plot(traj_half.index, traj_half.values, marker="o", markersize=3, label="2. Crosses halfway (h=12)")
ax.plot(traj_already.index, traj_already.values, marker="o", markersize=3, label="3. Already over at h=0")
ax.axhline(cap_ref, color="red", linestyle="--", label=f"Capacity ({cap_ref:.2f} MW)")
ax.set_title("Section 3: Three Controlled Time-to-Overload Trajectories\n(SIMULATED, constructed for validation only)")
ax.set_ylabel("Load (MW)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "time_to_overload_scenarios.png"), dpi=120)
plt.close(fig)

# Full scenario summary bar chart (stress score + risk color)
risk_colors = {"LOW": "green", "MODERATE": "gold", "HIGH": "orange", "CRITICAL": "red"}
fig, ax = plt.subplots(figsize=(12, 6))
plot_df = results_df.drop_duplicates(subset=["scenario"]).sort_values("stress_score")
colors = [risk_colors[r] for r in plot_df["risk_level"]]
ax.barh(plot_df["scenario"], plot_df["stress_score"], color=colors)
for edge in [30, 60, 80]:
    ax.axvline(edge, color="gray", linestyle="--", alpha=0.5)
ax.set_xlabel("Stress score")
ax.set_title("All Scenarios: Stress Score and Risk Level\n(SIMULATED scenario inputs, not real feeder events)")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "all_scenarios_summary.png"), dpi=120)
plt.close(fig)

# ===========================================================================
# Save summary JSON
# ===========================================================================
summary = {
    "baseline_origin": baseline_example["origin_datetime"],
    "representative_feeder": REP_FEEDER,
    "elevation_scenarios": elevation_df.drop(columns=["resolution_note"]).to_dict(orient="records"),
    "monotonic_across_elevation": bool(monotonic_ok),
    "high_occurred_in_elevation": bool(high_occurred),
    "critical_occurred_in_elevation": bool(critical_occurred),
    "overload_occurred_in_elevation": bool(overload_occurred_elevation),
    "scenario_E_tight_capacity": {k: v for k, v in row_e.items() if k != "resolution_note"},
    "scenario_F_overload": {k: v for k, v in row_f.items() if k != "resolution_note"},
    "scenario_F_expected_vs_actual_crossing_h": {"expected": float(expected_crossing_h), "actual": float(actual_crossing_h)},
    "scenario_G_high_utilization": {k: v for k, v in row_g.items() if k != "resolution_note"},
    "voltage_stress_activated": bool(voltage_stress_activated),
    "time_to_overload_section3": {
        "never_crosses": {k: str(v) if isinstance(v, pd.Timestamp) else v for k, v in tto_never.items()},
        "crosses_halfway": {k: str(v) if isinstance(v, pd.Timestamp) else v for k, v in tto_half.items()},
        "already_over": {k: str(v) if isinstance(v, pd.Timestamp) else v for k, v in tto_already.items()},
        "expected_halfway_crossing_h": float(expected_half_h),
    },
    "global_checks": {
        "no_nan_inf": bool(finite_ok),
        "bounded_0_100": bool(bounded_ok),
        "high_occurs_somewhere": bool(high_ever),
        "critical_occurs_somewhere": bool(critical_ever),
        "overload_activates_somewhere": bool(overload_ever),
        "voltage_stress_activates_somewhere": bool(voltage_stress_activated),
    },
}
with open(os.path.join(REPORTS_DIR, "stress_scenario_analysis_raw.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, default=str)

print(f"\nSaved: {os.path.join(REPORTS_DIR, 'stress_scenario_analysis_raw.json')}")
print(f"Saved plots under: {FIG_DIR}")
print("\nDONE.")
