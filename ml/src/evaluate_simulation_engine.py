"""
GridGuard AI - Controlled scenario evaluation for the What-If Simulation
Engine (ml/src/simulation_engine.py).

*** ALL SCENARIOS BELOW ARE DELIBERATELY CONSTRUCTED SIMULATION INPUTS. ***
A round reference capacity_mw=100.0 is used (hand-verifiable, same
convention as the other controlled-scenario scripts in this project).

Does not modify simulation_engine.py, action_engine.py, or stress_engine.py.
"""
import os
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import simulation_engine as sim

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
FIG_DIR = os.path.join(REPORTS_DIR, "figures", "simulation_engine")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(FIG_DIR, exist_ok=True)

CAPACITY = 100.0
START = pd.Timestamp("2020-01-15 00:00:00")


def make_baseline(peak=80.0):
    """A moderate, sub-capacity baseline diurnal-shaped trajectory -- the
    'existing 24h forecast' every scenario below starts from."""
    idx = pd.date_range(START, periods=25, freq="h")
    hours = np.arange(25)
    values = 0.55 * peak + 0.45 * peak * np.sin(np.pi * (hours - 6) / 24) ** 2
    values = np.clip(values, 5, None)
    values[np.argmax(values)] = peak
    return pd.Series(values, index=idx)


BASELINE = make_baseline(peak=80.0)


def make_early_peak_baseline(peak=80.0):
    """A baseline whose peak occurs early (h=2), so that resources dispatched
    starting at h=0 (all with durations >=3.5h) can actually reach it -- used
    for the intervention scenarios below, where the point is to test whether
    deployed flexibility can reach the moment of stress, not to test the
    duration-vs-magnitude limitation (already documented separately in
    action_engine_report.md and the earlier stress-scenario work)."""
    idx = pd.date_range(START, periods=25, freq="h")
    hours = np.arange(25)
    values = 0.5 * peak + 0.5 * peak * np.exp(-((hours - 2) ** 2) / 8.0)
    values = np.clip(values, 5, None)
    values[2] = peak
    return pd.Series(values, index=idx)


EARLY_PEAK_BASELINE = make_early_peak_baseline(peak=80.0)

SCENARIOS = {
    "NOMINAL": {
        "params": {"ambient_temperature_c": 27.0, "ev_surge_pct": 0.0, "solar_drop_pct": 0.0},
        "actions": None,
        "purpose": "Reference conditions (temperature at the documented reference, no surge, no solar drop) -- verifies the scenario layer is a true no-op at nominal parameters.",
    },
    "HIGH_TEMPERATURE": {
        "params": {"ambient_temperature_c": 38.0, "ev_surge_pct": 0.0, "solar_drop_pct": 0.0},
        "actions": None,
        "purpose": "Heat wave scenario -- isolates the temperature sensitivity effect.",
    },
    "HIGH_EV_SURGE": {
        "params": {"ambient_temperature_c": 27.0, "ev_surge_pct": 70.0, "solar_drop_pct": 0.0},
        "actions": None,
        "purpose": "Large EV charging surge -- isolates the EV sensitivity effect (feeder type EV_HEAVY, full sensitivity).",
    },
    "LOW_SOLAR": {
        "params": {"ambient_temperature_c": 27.0, "ev_surge_pct": 0.0, "solar_drop_pct": 85.0},
        "actions": None,
        "purpose": "Cloudy-day / low solar generation scenario -- isolates the solar-drop effect (daytime-only).",
    },
    "COMBINED_ADVERSE": {
        "params": {"ambient_temperature_c": 38.0, "ev_surge_pct": 55.0, "solar_drop_pct": 75.0},
        "actions": None,
        "purpose": "Worst-case combination of all three adverse conditions simultaneously.",
    },
    "ADVERSE_PLUS_SUCCESSFUL_INTERVENTION": {
        "params": {"ambient_temperature_c": 38.0, "ev_surge_pct": 55.0, "solar_drop_pct": 75.0},
        "actions": [{"resource": "EV", "mw": 15.0, "duration_hours": 4.0},
                     {"resource": "BATTERY", "mw": 20.0, "duration_hours": 3.5},
                     {"resource": "INDUSTRIAL", "mw": 25.0, "duration_hours": 6.0}],
        "baseline": "early_peak",
        "purpose": "Same worst-case adverse scenario, applied to a trajectory whose peak falls early (h=2, within every resource's duration window), with all three synthetic resources fully deployed -- tests whether a maximal, well-timed intervention can resolve it.",
    },
    "ADVERSE_PLUS_INSUFFICIENT_INTERVENTION": {
        "params": {"ambient_temperature_c": 42.0, "ev_surge_pct": 90.0, "solar_drop_pct": 100.0},
        "actions": [{"resource": "BATTERY", "mw": 20.0, "duration_hours": 3.5}],
        "baseline": "early_peak",
        "purpose": "An even more extreme adverse scenario (same early-peaking trajectory) with only a single, small resource deployed -- tests honest insufficient-flexibility reporting when the intervention CAN reach the peak but isn't large enough.",
    },
}


def run_all(feeder_type="EV_HEAVY"):
    rows = []
    detail = {}
    for name, spec in SCENARIOS.items():
        baseline_traj = EARLY_PEAK_BASELINE if spec.get("baseline") == "early_peak" else BASELINE
        target_ts = baseline_traj.index[baseline_traj.values.argmax()]
        result = sim.simulate_scenario(
            feeder_id=f"SCENARIO_{name}", feeder_type=feeder_type, capacity_mw=CAPACITY,
            baseline_trajectory=baseline_traj, target_timestamp=target_ts,
            proposed_actions=spec["actions"], **spec["params"],
        )
        detail[name] = {"purpose": spec["purpose"], "result": result}
        rows.append({
            "scenario": name,
            "baseline_peak_mw": result["baseline_peak_load_mw"],
            "scenario_peak_mw": result["scenario_peak_load_mw"],
            "final_peak_mw": result["final_peak_load_mw"],
            "baseline_utilization": result["baseline_utilization"],
            "scenario_utilization": result["scenario_utilization"],
            "final_utilization": result["final_utilization"],
            "baseline_stress": result["baseline_stress_score"],
            "scenario_stress": result["scenario_stress_score"],
            "final_stress": result["final_stress_score"],
            "baseline_risk": result["baseline_risk"],
            "scenario_risk": result["scenario_risk"],
            "final_risk": result["final_risk"],
            "baseline_tto": result["baseline_time_to_overload"],
            "scenario_tto": result["scenario_time_to_overload"],
            "final_tto": result["final_time_to_overload"],
            "overload_before": result["overload_before"],
            "overload_after_scenario": result["overload_after_scenario"],
            "overload_after": result["overload_after"],
            "overload_avoided": result["overload_avoided"],
            "feasibility_status": result["feasibility_status"],
            "total_reduction_mw": result["total_reduction_mw"],
        })
    return pd.DataFrame(rows), detail


def validate(df, detail):
    print("=" * 100)
    print("CONTROLLED SCENARIO VALIDATION")
    print("=" * 100)

    r = detail["NOMINAL"]["result"]
    assert abs(r["scenario_peak_load_mw"] - r["baseline_peak_load_mw"]) < 1e-6
    print("NOMINAL: scenario == baseline (true no-op) -- PASS")

    r = detail["HIGH_TEMPERATURE"]["result"]
    assert r["scenario_peak_load_mw"] > r["baseline_peak_load_mw"]
    assert abs(r["load_change_mw"]["ev_surge"]) < 1e-6 and abs(r["load_change_mw"]["solar_drop"]) < 1e-6
    print("HIGH_TEMPERATURE: load increases, isolated to the temperature term -- PASS")

    r = detail["HIGH_EV_SURGE"]["result"]
    assert r["scenario_peak_load_mw"] > r["baseline_peak_load_mw"]
    assert abs(r["load_change_mw"]["temperature"]) < 1e-6
    print("HIGH_EV_SURGE: load increases, isolated to the EV term -- PASS")

    r = detail["LOW_SOLAR"]["result"]
    assert r["scenario_peak_load_mw"] >= r["baseline_peak_load_mw"]
    print("LOW_SOLAR: load does not decrease -- PASS")

    r = detail["COMBINED_ADVERSE"]["result"]
    assert r["scenario_peak_load_mw"] > detail["HIGH_TEMPERATURE"]["result"]["scenario_peak_load_mw"]
    print("COMBINED_ADVERSE: exceeds any single adverse factor alone -- PASS")

    r = detail["ADVERSE_PLUS_SUCCESSFUL_INTERVENTION"]["result"]
    assert r["final_peak_load_mw"] < r["scenario_peak_load_mw"]  # early-peak trajectory, resources reach it
    print(f"ADVERSE_PLUS_SUCCESSFUL_INTERVENTION: peak reduced ({r['scenario_peak_load_mw']:.1f} -> "
          f"{r['final_peak_load_mw']:.1f}), overload_after_scenario={r['overload_after_scenario']}, "
          f"overload_after={r['overload_after']}, overload_avoided={r['overload_avoided']}")

    r = detail["ADVERSE_PLUS_INSUFFICIENT_INTERVENTION"]["result"]
    assert r["total_reduction_mw"] > 0  # something is applied even though it's not enough
    assert r["overload_avoided"] is False
    print(f"ADVERSE_PLUS_INSUFFICIENT_INTERVENTION: peak {r['scenario_peak_load_mw']:.1f} -> "
          f"{r['final_peak_load_mw']:.1f} (reduction={r['total_reduction_mw']:.1f} MW) but "
          f"overload_avoided={r['overload_avoided']} -- reported honestly")

    print("\nALL SCENARIO ASSERTIONS PASSED")


def make_plots(df, detail):
    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(df))
    width = 0.25
    ax.bar(x - width, df["baseline_peak_mw"], width, label="Baseline (existing forecast)")
    ax.bar(x, df["scenario_peak_mw"], width, label="After scenario adjustment")
    ax.bar(x + width, df["final_peak_mw"], width, label="After scenario + intervention")
    ax.axhline(CAPACITY, color="red", linestyle="--", label=f"Capacity ({CAPACITY:.0f} MW)")
    ax.set_xticks(x)
    ax.set_xticklabels(df["scenario"], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Peak load (MW)")
    ax.set_title("Peak Load: Baseline -> Scenario -> Post-Intervention\n(CONTROLLED SIMULATION -- not real feeder events)")
    ax.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "peak_load_stages.png"), dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(x - width / 2, df["baseline_stress"], width, label="Baseline stress")
    ax.bar(x + width / 2, df["final_stress"], width, label="Final stress")
    for edge in [30, 60, 80]:
        ax.axhline(edge, color="gray", linestyle="--", alpha=0.4)
    ax.set_xticks(x)
    ax.set_xticklabels(df["scenario"], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Stress score")
    ax.set_title("Stress Score: Baseline vs. Final (After Scenario + Intervention)\n(CONTROLLED SIMULATION)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "stress_before_after.png"), dpi=120)
    plt.close(fig)

    # attribution breakdown for COMBINED_ADVERSE
    r = detail["COMBINED_ADVERSE"]["result"]
    lc = r["load_change_mw"]
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = ["temperature", "ev_surge", "solar_drop"]
    vals = [lc[k] for k in labels]
    ax.bar(labels, vals, color=["orangered", "steelblue", "goldenrod"])
    ax.set_ylabel("Load change (MW)")
    ax.set_title("Per-Variable Load Change Attribution — COMBINED_ADVERSE Scenario\n(CONTROLLED SIMULATION)")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "attribution_combined_adverse.png"), dpi=120)
    plt.close(fig)

    print(f"Saved 3 plots under: {FIG_DIR}")


if __name__ == "__main__":
    df, detail = run_all()
    pd.set_option("display.width", 200)
    print(df.to_string(index=False))
    validate(df, detail)
    make_plots(df, detail)

    summary = {
        "n_scenarios": len(df),
        "n_baseline_overload": int(df["overload_before"].sum()),
        "n_overload_after_scenario": int(df["overload_after_scenario"].sum()),
        "n_overload_avoided_by_intervention": int(df["overload_avoided"].sum()),
        "feasibility_counts": df["feasibility_status"].value_counts().to_dict(),
        "scenario_results": df.to_dict(orient="records"),
    }
    df.to_csv(os.path.join(DATA_DIR, "simulation_engine_evaluation_results.csv"), index=False)
    with open(os.path.join(REPORTS_DIR, "simulation_engine_evaluation_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\nScenarios with baseline overload: {summary['n_baseline_overload']}")
    print(f"Scenarios with overload after scenario adjustment: {summary['n_overload_after_scenario']}")
    print(f"Scenarios where intervention avoided overload: {summary['n_overload_avoided_by_intervention']}")
    print(f"Feasibility counts: {summary['feasibility_counts']}")
    print("Saved: ml/data/simulation_engine_evaluation_results.csv")
    print("Saved: ml/reports/simulation_engine_evaluation_summary.json")
    print("\nDONE.")
