"""
GridGuard AI - Controlled + representative-real-data evaluation for the
Prevention/Decision Engine (ml/src/prevention_engine.py).

*** THE CONTROLLED SCENARIOS BELOW ARE DELIBERATELY CONSTRUCTED SIMULATION
INPUTS. *** A round reference capacity_mw=100.0 is used (hand-verifiable,
same convention as the other controlled-scenario scripts in this project).
The final section separately loads ONE real representative origin/feeder
from the existing rolling_integration.py output -- clearly labeled as such.

Does not modify prevention_engine.py, action_engine.py, simulation_engine.py,
or stress_engine.py.
"""
import os
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import prevention_engine as pe
import action_engine as ae

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
FIG_DIR = os.path.join(REPORTS_DIR, "figures", "prevention_engine")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(FIG_DIR, exist_ok=True)

CAPACITY = 100.0
START = pd.Timestamp("2020-01-01 00:00:00")


def traj_from_points(points, n_hours=24):
    hrs = [p[0] for p in points]
    vals = [p[1] for p in points]
    h = np.arange(n_hours + 1)
    v = np.interp(h, hrs, vals)
    idx = pd.date_range(START, periods=n_hours + 1, freq="h")
    return pd.Series(v, index=idx)


SCENARIOS = {
    "SAFE": {"points": [(0, 45), (12, 60), (24, 55)], "purpose": "Feeder stays well under capacity -- verifies NO_ACTION_REQUIRED."},
    "SMALL_OVERLOAD": {"points": [(0, 90), (2, 108), (4, 90), (24, 85)], "purpose": "Small overshoot -- one cheap resource should prevent it."},
    "MULTIPLE_FEASIBLE": {"points": [(0, 92), (2, 109), (4, 92), (24, 88)], "purpose": "All three resources individually sufficient -- verifies cheapest is chosen."},
    "LARGER_OVERLOAD": {"points": [(0, 95), (3, 130), (6, 95), (24, 90)], "purpose": "Overshoot requiring a combination of resources."},
    "INSUFFICIENT_FLEXIBILITY": {"points": [(0, 90), (2, 175), (4, 90), (24, 85)], "purpose": "Overshoot exceeds even all three resources combined."},
    "DURATION_LIMITED": {"points": [(0, 140), (3, 140), (6, 102), (24, 102)], "purpose": "Sustained overload outlasting every resource's max duration."},
    "HIGH_RISK_NO_OVERLOAD": {"points": [(0, 88), (24, 92)], "purpose": "Elevated risk without a technical overload -- still triggers a recommendation."},
}


def run_controlled():
    rows = []
    detail = {}
    for name, spec in SCENARIOS.items():
        traj = traj_from_points(spec["points"])
        rec = pe.recommend_prevention(f"SCENARIO_{name}", "TEST", CAPACITY, traj)
        detail[name] = {"purpose": spec["purpose"], "recommendation": rec}
        rows.append({
            "scenario": name,
            "baseline_load_mw": rec["baseline_load_mw"],
            "baseline_risk": rec["baseline_risk"],
            "overload_before": rec["overload_before"],
            "prevention_status": rec["prevention_status"],
            "actions": "+".join(a["resource"] for a in rec["recommended_actions"]) if rec["recommended_actions"] else "NONE",
            "intervention_cost": rec["intervention_cost"],
            "total_reduction_mw": rec["total_reduction_mw"],
            "projected_load_mw": rec["projected_load_mw"],
            "projected_risk": rec["projected_risk"],
            "overload_avoided": rec["overload_avoided"],
            "candidates_evaluated": rec["candidates_evaluated"],
        })
    return pd.DataFrame(rows), detail


def validate(df, detail):
    print("=" * 100)
    print("CONTROLLED SCENARIO VALIDATION")
    print("=" * 100)

    assert detail["SAFE"]["recommendation"]["prevention_status"] == "NO_ACTION_REQUIRED"
    print("SAFE -> NO_ACTION_REQUIRED -- PASS")

    r = detail["SMALL_OVERLOAD"]["recommendation"]
    assert r["prevention_status"] == "PREVENTED" and len(r["recommended_actions"]) == 1
    print(f"SMALL_OVERLOAD -> PREVENTED via single resource ({r['recommended_actions'][0]['resource']}) -- PASS")

    r = detail["MULTIPLE_FEASIBLE"]["recommendation"]
    assert r["prevention_status"] == "PREVENTED"
    resolved = [a for a in r["alternatives"] if a["resolved"]]
    assert len(resolved) > 1
    print(f"MULTIPLE_FEASIBLE -> PREVENTED, cheapest of {len(resolved)} feasible options selected -- PASS")

    r = detail["LARGER_OVERLOAD"]["recommendation"]
    assert r["prevention_status"] == "PREVENTED" and len(r["recommended_actions"]) >= 2
    print(f"LARGER_OVERLOAD -> PREVENTED via combination ({r['recommended_actions']}) -- PASS")

    r = detail["INSUFFICIENT_FLEXIBILITY"]["recommendation"]
    assert r["prevention_status"] == "INSUFFICIENT_FLEXIBILITY" and r["overload_avoided"] is False
    print("INSUFFICIENT_FLEXIBILITY -> honestly reported -- PASS")

    r = detail["DURATION_LIMITED"]["recommendation"]
    assert r["prevention_status"] == "DURATION_LIMITED" and r["overload_avoided"] is False
    print("DURATION_LIMITED -> honestly reported, distinct from INSUFFICIENT_FLEXIBILITY -- PASS")

    r = detail["HIGH_RISK_NO_OVERLOAD"]["recommendation"]
    assert r["overload_before"] is False
    assert r["prevention_status"] != "NO_ACTION_REQUIRED"
    print(f"HIGH_RISK_NO_OVERLOAD -> status={r['prevention_status']} (action still recommended despite no overload) -- PASS")

    print("\nALL CONTROLLED SCENARIO ASSERTIONS PASSED")


def run_real_data_example():
    """Runs the Prevention Engine against ONE representative real origin/
    feeder from the existing rolling_integration.py output -- the highest-
    stress observation identified in earlier stages (feeder F10,
    2020-01-20 20:00). Read-only; does not modify rolling_feeder_results.csv."""
    csv_path = os.path.join(DATA_DIR, "rolling_feeder_results.csv")
    if not os.path.exists(csv_path):
        print(f"\n[real-data example skipped: {csv_path} not found]")
        return None
    try:
        scenario = ae.load_scenario_from_rolling_results(csv_path, "2020-01-20 20:00:00", "F10")
    except Exception as e:
        print(f"\n[real-data example skipped: {e}]")
        return None

    rec = pe.recommend_prevention(scenario.feeder_id, scenario.feeder_type, scenario.capacity_mw, scenario.trajectory)
    print("\n" + "=" * 100)
    print("REPRESENTATIVE REAL-DATA EXAMPLE (from rolling_integration.py output -- feeder capacity/forecast are")
    print("REAL model outputs; any recommended EV/Battery/Industrial actions remain SYNTHETIC assumptions)")
    print("=" * 100)
    print(f"Feeder: {rec['feeder_id']} ({scenario.feeder_type}), capacity={scenario.capacity_mw:.2f} MW")
    print(f"Baseline: load={rec['baseline_load_mw']:.2f} MW, risk={rec['baseline_risk']}, "
          f"stress={rec['baseline_stress_score']:.2f}, overload_before={rec['overload_before']}")
    print(f"Recommendation: status={rec['prevention_status']}, actions={[a['resource'] for a in rec['recommended_actions']]}, "
          f"reason={rec['reason']}")
    return rec


def make_plots(df):
    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(df))
    width = 0.35
    ax.bar(x - width / 2, df["baseline_load_mw"], width, label="Baseline load")
    ax.bar(x + width / 2, df["projected_load_mw"], width, label="Projected load")
    ax.axhline(CAPACITY, color="red", linestyle="--", label=f"Capacity ({CAPACITY:.0f} MW)")
    ax.set_xticks(x)
    ax.set_xticklabels(df["scenario"], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Load (MW)")
    ax.set_title("Prevention Engine: Baseline vs. Projected Load\n(CONTROLLED SIMULATION -- not real feeder events)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "baseline_vs_projected_load.png"), dpi=120)
    plt.close(fig)

    status_colors = {"NO_ACTION_REQUIRED": "green", "PREVENTED": "seagreen", "REDUCED_NOT_PREVENTED": "orange",
                       "INSUFFICIENT_FLEXIBILITY": "red", "DURATION_LIMITED": "darkred"}
    fig, ax = plt.subplots(figsize=(12, 5))
    colors = [status_colors.get(s, "gray") for s in df["prevention_status"]]
    ax.bar(df["scenario"], df["intervention_cost"], color=colors)
    ax.set_ylabel("Intervention cost (arbitrary units)")
    ax.set_title("Intervention Cost by Scenario, Colored by Prevention Status\n(CONTROLLED SIMULATION)")
    plt.xticks(rotation=30, ha="right", fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "cost_by_status.png"), dpi=120)
    plt.close(fig)

    print(f"Saved 2 plots under: {FIG_DIR}")


if __name__ == "__main__":
    df, detail = run_controlled()
    pd.set_option("display.width", 200)
    print(df.to_string(index=False))
    validate(df, detail)
    make_plots(df)
    real_rec = run_real_data_example()

    n_safe = int((df["prevention_status"] == "NO_ACTION_REQUIRED").sum())
    n_overload_cases = int(df["overload_before"].sum())
    n_prevented = int((df["prevention_status"] == "PREVENTED").sum())
    n_reduced_not_prevented = int((df["prevention_status"] == "REDUCED_NOT_PREVENTED").sum())
    n_insufficient = int((df["prevention_status"] == "INSUFFICIENT_FLEXIBILITY").sum())
    n_duration_limited = int((df["prevention_status"] == "DURATION_LIMITED").sum())
    actioned = df[df["prevention_status"] != "NO_ACTION_REQUIRED"]
    avg_cost = float(actioned["intervention_cost"].mean())
    avg_reduction = float(actioned["total_reduction_mw"].mean())
    combos = df.loc[df["actions"] != "NONE", "actions"].value_counts().to_dict()

    summary = {
        "n_scenarios": len(df),
        "n_safe_no_action": n_safe,
        "n_overload_before": n_overload_cases,
        "n_prevented": n_prevented,
        "n_reduced_not_prevented": n_reduced_not_prevented,
        "n_insufficient_flexibility": n_insufficient,
        "n_duration_limited": n_duration_limited,
        "avg_intervention_cost_where_actioned": avg_cost,
        "avg_mw_reduction_where_actioned": avg_reduction,
        "intervention_combinations_selected": combos,
        "real_data_example": real_rec if real_rec else None,
        "scenario_results": df.to_dict(orient="records"),
    }
    df.to_csv(os.path.join(DATA_DIR, "prevention_engine_evaluation_results.csv"), index=False)
    with open(os.path.join(REPORTS_DIR, "prevention_engine_evaluation_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\nScenarios: {len(df)}, safe/no-action: {n_safe}, overload-before: {n_overload_cases}")
    print(f"Prevented: {n_prevented}, reduced-not-prevented: {n_reduced_not_prevented}, "
          f"insufficient-flexibility: {n_insufficient}, duration-limited: {n_duration_limited}")
    print(f"Avg cost (where actioned): {avg_cost:.2f}, avg MW reduction: {avg_reduction:.2f}")
    print(f"Combinations selected: {combos}")
    print("Saved: ml/data/prevention_engine_evaluation_results.csv")
    print("Saved: ml/reports/prevention_engine_evaluation_summary.json")
    print("\nDONE.")
