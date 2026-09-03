"""
GridGuard AI - Controlled action-engine validation scenarios.

*** ALL SCENARIOS BELOW ARE CONTROLLED SIMULATION INPUTS. ***
None are real Panama feeder events or historical data. They exist solely to
validate ml/src/action_engine.py's decision logic across the cases it must
handle correctly: no-action-needed, single-action-sufficient,
combination-required, insufficient-flexibility, multiple-feasible-solutions,
and reduces-but-does-not-eliminate.

Uses a round reference capacity_mw=100.0 (not any specific feeder's real
capacity) so the numbers are easy to verify by hand, in the same spirit as
ml/src/stress_scenario_analysis.py's controlled trajectories. Does not
modify action_engine.py, stress_engine.py, or feeder_generator.py.
"""
import os
import sys
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(__file__))
import action_engine as ae

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
FIG_DIR = os.path.join(REPORTS_DIR, "figures", "action_engine")
os.makedirs(FIG_DIR, exist_ok=True)

CAPACITY = 100.0  # round reference capacity for controlled scenarios -- SIMULATED, not a real feeder's capacity
START = pd.Timestamp("2020-01-01 00:00:00")


def traj_from_points(points, n_hours=24):
    """Explicit controlled trajectory: linear interpolation through
    (hour, MW) control points, at each of h=0..n_hours. Deliberately simple
    and hand-verifiable, like stress_scenario_analysis.py's trajectories."""
    hrs = [p[0] for p in points]
    vals = [p[1] for p in points]
    h = np.arange(n_hours + 1)
    v = np.interp(h, hrs, vals)
    idx = pd.date_range(START, periods=n_hours + 1, freq="h")
    return pd.Series(v, index=idx)


SCENARIOS = {
    "A_SAFE": {
        "points": [(0, 50), (12, 70), (24, 60)],
        "purpose": "Feeder stays well under capacity throughout -- verifies action_required=False and no unnecessary intervention.",
    },
    "B_SMALL_OVERLOAD": {
        "points": [(0, 90), (2, 118), (4, 90), (24, 85)],
        "purpose": "Small, short overshoot -- verifies exactly one resource (the cheapest sufficient one) is recommended, not a needless combination.",
    },
    "C_LARGER_OVERLOAD": {
        "points": [(0, 95), (3, 130), (6, 95), (24, 90)],
        "purpose": "Larger overshoot exceeding any single resource's MW capacity -- verifies a combination is correctly required and the cheapest sufficient combination is chosen.",
    },
    "D_EXCEEDS_ALL_FLEXIBILITY": {
        "points": [(0, 90), (2, 175), (4, 90), (24, 85)],
        "purpose": "Overshoot exceeding even all three resources combined (max 60 MW) -- verifies the engine correctly reports insufficient flexibility rather than pretending success.",
    },
    "E_MULTIPLE_FEASIBLE_SOLUTIONS": {
        "points": [(0, 92), (2, 109), (4, 92), (24, 88)],
        "purpose": "Overshoot small enough that EV, Battery, AND Industrial would each individually suffice -- verifies the engine picks the lowest-disruption option (Battery) rather than any other sufficient one.",
    },
    "F_REDUCES_BUT_NOT_ELIMINATES": {
        "points": [(0, 140), (3, 140), (6, 102), (24, 102)],
        "purpose": "Sustained overload that outlasts every resource's maximum duration -- verifies the engine reports overload_prevented=False and shows a genuinely reduced (not unchanged) peak, distinguishing a DURATION-limited failure from Scenario D's MAGNITUDE-limited failure.",
    },
}


def run_all_scenarios():
    results = []
    trajectories = {}
    for name, spec in SCENARIOS.items():
        traj = traj_from_points(spec["points"])
        trajectories[name] = traj
        rec = ae.recommend_action(traj, CAPACITY, feeder_id=f"CONTROLLED_SCENARIO_{name}", feeder_type="SIMULATED_TEST")
        results.append({"scenario": name, "purpose": spec["purpose"], "trajectory": traj, "result": rec})
    return results, trajectories


def print_scenario_summary(results):
    print("=" * 100)
    print("CONTROLLED SIMULATION SCENARIOS -- action_engine.py validation (capacity_mw = 100.0, SYNTHETIC)")
    print("=" * 100)
    for r in results:
        name = r["scenario"]
        base = r["result"]["baseline"]
        rec = r["result"]["recommendation"]
        print(f"\n--- {name} ---")
        print(f"Purpose: {r['purpose']}")
        print(f"Baseline: peak={base['peak_load_mw']:.2f} MW, utilization={base['peak_utilization']:.2%}, "
              f"stress={base['stress_score']:.2f}, risk={base['risk_level']}, overload_predicted={base['overload_predicted']}")
        if not rec["action_required"]:
            print(f"Recommendation: action_required=False ({rec['reason']})")
        else:
            print(f"Recommendation: action={rec['action_label']}, cost={rec['total_disruption_cost']}, "
                  f"reduction={rec['total_reduction_mw']:.2f} MW, resulting_peak={rec['resulting_peak_load_mw']:.2f} MW, "
                  f"resulting_stress={rec['resulting_stress_score']:.2f}, resulting_risk={rec['resulting_risk_level']}, "
                  f"overload_prevented={rec['overload_prevented']}")
            if not rec["overload_prevented"]:
                print(f"    INSUFFICIENT FLEXIBILITY: required={rec['required_reduction_mw']:.2f} MW, "
                      f"max_feasible={rec['max_feasible_reduction_mw']:.2f} MW, remaining={rec['remaining_overload_mw']:.2f} MW")


def validate_scenarios(results):
    print("\n" + "=" * 100)
    print("SCENARIO-LEVEL ASSERTIONS")
    print("=" * 100)
    by_name = {r["scenario"]: r for r in results}

    assert by_name["A_SAFE"]["result"]["recommendation"]["action_required"] is False
    print("A_SAFE: action_required is False -- PASS")

    rec_b = by_name["B_SMALL_OVERLOAD"]["result"]["recommendation"]
    assert rec_b["overload_prevented"] is True
    assert "+" not in rec_b["action_label"]  # single resource, no combination needed
    print(f"B_SMALL_OVERLOAD: single action ({rec_b['action_label']}) prevents overload -- PASS")

    rec_c = by_name["C_LARGER_OVERLOAD"]["result"]["recommendation"]
    assert rec_c["overload_prevented"] is True
    assert "+" in rec_c["action_label"]  # combination required
    print(f"C_LARGER_OVERLOAD: combination action ({rec_c['action_label']}) prevents overload -- PASS")

    rec_d = by_name["D_EXCEEDS_ALL_FLEXIBILITY"]["result"]["recommendation"]
    assert rec_d["overload_prevented"] is False
    assert rec_d["remaining_overload_mw"] > 0
    print(f"D_EXCEEDS_ALL_FLEXIBILITY: correctly reports overload_prevented=False, "
          f"remaining_overload={rec_d['remaining_overload_mw']:.2f} MW -- PASS")

    rec_e = by_name["E_MULTIPLE_FEASIBLE_SOLUTIONS"]["result"]["recommendation"]
    alternatives_e = by_name["E_MULTIPLE_FEASIBLE_SOLUTIONS"]["result"]["alternatives"]
    n_sufficient = sum(1 for a in alternatives_e if not a["overload_predicted"])
    assert n_sufficient > 1, "Scenario E must have multiple individually-sufficient candidates to be meaningful"
    assert rec_e["action_label"] == "BATTERY", f"Expected cheapest option BATTERY, got {rec_e['action_label']}"
    print(f"E_MULTIPLE_FEASIBLE_SOLUTIONS: {n_sufficient} candidates sufficient, "
          f"lowest-disruption ({rec_e['action_label']}) selected -- PASS")

    rec_f = by_name["F_REDUCES_BUT_NOT_ELIMINATES"]["result"]["recommendation"]
    base_f = by_name["F_REDUCES_BUT_NOT_ELIMINATES"]["result"]["baseline"]
    assert rec_f["overload_prevented"] is False
    assert rec_f["resulting_peak_load_mw"] < base_f["peak_load_mw"], "Peak must be reduced even though overload persists"
    print(f"F_REDUCES_BUT_NOT_ELIMINATES: peak reduced {base_f['peak_load_mw']:.2f} -> "
          f"{rec_f['resulting_peak_load_mw']:.2f} MW, overload_prevented=False -- PASS")

    print("\nALL SCENARIO ASSERTIONS PASSED")


def make_plots(results):
    names = list(SCENARIOS.keys())

    # 1. Before vs after peak load
    before_peaks = [r["result"]["baseline"]["peak_load_mw"] for r in results]
    after_peaks = [r["result"]["recommendation"].get("resulting_peak_load_mw", r["result"]["baseline"]["peak_load_mw"]) for r in results]
    fig, ax = plt.subplots(figsize=(11, 6))
    x = np.arange(len(names))
    width = 0.35
    ax.bar(x - width / 2, before_peaks, width, label="Before (baseline)")
    ax.bar(x + width / 2, after_peaks, width, label="After (recommended action)")
    ax.axhline(CAPACITY, color="red", linestyle="--", label=f"Capacity ({CAPACITY:.0f} MW)")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Peak load (MW)")
    ax.set_title("Before vs. After: Peak Load\n(CONTROLLED SIMULATION SCENARIOS -- not real feeder events)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "before_after_peak_load.png"), dpi=120)
    plt.close(fig)

    # 2. Before vs after stress score
    before_stress = [r["result"]["baseline"]["stress_score"] for r in results]
    after_stress = [r["result"]["recommendation"].get("resulting_stress_score", r["result"]["baseline"]["stress_score"]) for r in results]
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.bar(x - width / 2, before_stress, width, label="Before (baseline)")
    ax.bar(x + width / 2, after_stress, width, label="After (recommended action)")
    for edge in [30, 60, 80]:
        ax.axhline(edge, color="gray", linestyle="--", alpha=0.4)
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Stress score")
    ax.set_title("Before vs. After: Stress Score\n(CONTROLLED SIMULATION SCENARIOS -- not real feeder events)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "before_after_stress_score.png"), dpi=120)
    plt.close(fig)

    # 3. Candidate action comparison (Scenario C, illustrating all 7 candidates)
    by_name = {r["scenario"]: r for r in results}
    alts_c = by_name["C_LARGER_OVERLOAD"]["result"]["alternatives"]
    labels_c = [a["label"] for a in alts_c]
    scores_c = [a["resulting_stress_score"] for a in alts_c]
    colors_c = ["green" if not a["overload_predicted"] else "red" for a in alts_c]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(labels_c, scores_c, color=colors_c)
    ax.set_xlabel("Resulting stress score")
    ax.set_title("Candidate Action Comparison — Scenario C_LARGER_OVERLOAD\n"
                 "(green = overload prevented, red = overload persists; CONTROLLED SIMULATION)")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "candidate_action_comparison.png"), dpi=120)
    plt.close(fig)

    # 4. Required reduction vs available flexibility (all scenarios with action_required)
    req_rows = []
    for r in results:
        rec = r["result"]["recommendation"]
        if rec["action_required"]:
            base = r["result"]["baseline"]
            required = max(base["peak_load_mw"] - CAPACITY, 0.0)
            max_feasible = max(a["total_reduction_mw"] for a in r["result"]["alternatives"])
            req_rows.append((r["scenario"], required, max_feasible))
    fig, ax = plt.subplots(figsize=(10, 6))
    xs = np.arange(len(req_rows))
    ax.bar(xs - width / 2, [x[1] for x in req_rows], width, label="Required reduction (MW)")
    ax.bar(xs + width / 2, [x[2] for x in req_rows], width, label="Max feasible reduction (MW)")
    ax.set_xticks(xs)
    ax.set_xticklabels([x[0] for x in req_rows], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("MW")
    ax.set_title("Required Reduction vs. Available Flexibility\n(CONTROLLED SIMULATION SCENARIOS)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "required_vs_available_flexibility.png"), dpi=120)
    plt.close(fig)

    # 5. Action-selection comparison (Scenario E: multiple feasible, shows why BATTERY wins)
    alts_e = by_name["E_MULTIPLE_FEASIBLE_SOLUTIONS"]["result"]["alternatives"]
    labels_e = [a["label"] for a in alts_e]
    costs_e = [a["total_disruption_cost"] for a in alts_e]
    colors_e = ["green" if not a["overload_predicted"] else "red" for a in alts_e]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(labels_e, costs_e, color=colors_e)
    ax.set_xlabel("Total disruption cost (lower = preferred)")
    ax.set_title("Action-Selection Comparison — Scenario E_MULTIPLE_FEASIBLE_SOLUTIONS\n"
                 "(green = sufficient to prevent overload; lowest-cost green bar is selected; CONTROLLED SIMULATION)")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "action_selection_comparison.png"), dpi=120)
    plt.close(fig)

    print(f"\nSaved 5 plots under: {FIG_DIR}")


if __name__ == "__main__":
    results, trajectories = run_all_scenarios()
    print_scenario_summary(results)
    validate_scenarios(results)
    make_plots(results)

    # Save a flat summary table + full JSON
    rows = []
    for r in results:
        rec = r["result"]["recommendation"]
        base = r["result"]["baseline"]
        rows.append({
            "scenario": r["scenario"],
            "purpose": r["purpose"],
            "baseline_peak_mw": base["peak_load_mw"],
            "baseline_stress_score": base["stress_score"],
            "baseline_risk_level": base["risk_level"],
            "baseline_overload_predicted": base["overload_predicted"],
            "action_required": rec["action_required"],
            "action_label": rec.get("action_label"),
            "overload_prevented": rec.get("overload_prevented"),
            "resulting_peak_mw": rec.get("resulting_peak_load_mw"),
            "resulting_stress_score": rec.get("resulting_stress_score"),
            "resulting_risk_level": rec.get("resulting_risk_level"),
        })
    summary_df = pd.DataFrame(rows)
    summary_df.to_csv(os.path.join(REPORTS_DIR, "..", "data", "action_engine_scenario_results.csv"), index=False)
    print(f"\nSaved: ml/data/action_engine_scenario_results.csv")

    json_out = {
        r["scenario"]: {
            "purpose": r["purpose"],
            "baseline": r["result"]["baseline"],
            "recommendation": r["result"]["recommendation"],
            "n_alternatives": len(r["result"]["alternatives"]),
        }
        for r in results
    }
    with open(os.path.join(REPORTS_DIR, "action_engine_scenarios_raw.json"), "w", encoding="utf-8") as f:
        json.dump(json_out, f, indent=2, default=str)
    print(f"Saved: ml/reports/action_engine_scenarios_raw.json")
    print("\nDONE.")
