"""
GridGuard AI - Controlled scenario evaluation for the Action/Optimization
Engine (ml/src/action_engine.py).

*** ALL SCENARIOS BELOW ARE DELIBERATELY CONSTRUCTED SIMULATION INPUTS. ***
None are real Panama feeder events. A round reference capacity_mw=100.0 is
used throughout so results are easy to verify by hand (same convention as
ml/src/stress_scenario_analysis.py from the prior stage).

Does not modify action_engine.py, stress_engine.py, or feeder_generator.py.
"""
import os
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import action_engine as ae

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
FIG_DIR = os.path.join(REPORTS_DIR, "figures", "action_engine")
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
    "SAFE": {
        "points": [(0, 45), (12, 60), (24, 55)],
        "feeder_type": "RESIDENTIAL",
        "purpose": "Feeder stays well under capacity throughout -- verifies no action recommended.",
    },
    "EV_ONLY_SUFFICIENT": {
        "points": [(0, 90), (2, 112), (4, 90), (24, 85)],
        "feeder_type": "EV_HEAVY",
        "purpose": "Small overshoot within EV's own 15 MW / 4h capacity, but not Battery's -- verifies EV alone is selected only when it's the cheapest sufficient option (expect Battery, actually cheaper, to win -- see report for why 'EV-only' does not mean 'EV is forced').",
    },
    "BATTERY_ONLY_SUFFICIENT": {
        "points": [(0, 90), (2, 108), (4, 90), (24, 85)],
        "feeder_type": "MIXED",
        "purpose": "Overshoot small enough that Battery alone (cheapest, 0.5 cost) suffices -- verifies single lowest-cost resource selected.",
    },
    "INDUSTRIAL_ONLY_SUFFICIENT": {
        "points": [(0, 90), (2, 108), (4, 90), (24, 85)],
        "feeder_type": "INDUSTRIAL",
        "purpose": "Same magnitude as BATTERY_ONLY -- included to show Industrial-only is never chosen over Battery when both suffice (Industrial costs 6x more), demonstrating the disruption-cost-minimizing objective concretely.",
    },
    "COMBINED_REQUIRED": {
        "points": [(0, 95), (3, 130), (6, 95), (24, 90)],
        "feeder_type": "COMMERCIAL",
        "purpose": "Overshoot exceeds any single resource's MW capacity -- verifies a combination is correctly required.",
    },
    "INSUFFICIENT_FLEXIBILITY": {
        "points": [(0, 90), (2, 175), (4, 90), (24, 85)],
        "feeder_type": "INDUSTRIAL",
        "purpose": "Overshoot exceeds even all three resources combined (max 60 MW) -- verifies honest insufficient-flexibility reporting.",
    },
    "DURATION_LIMITED": {
        "points": [(0, 140), (3, 140), (6, 102), (24, 102)],
        "feeder_type": "RESIDENTIAL",
        "purpose": "Sustained overload outlasting every resource's max duration -- verifies peak is reduced but overload is honestly reported as not fully prevented.",
    },
    "HIGH_RISK_NO_OVERLOAD": {
        "points": [(0, 88), (24, 92)],
        "feeder_type": "MIXED",
        "purpose": "High utilization (88-92%) but never technically crosses capacity -- verifies the engine still recommends action to reduce stress (using the non-overload safety-margin target), not just to prevent overload.",
    },
}


def run_all():
    rows = []
    detail = {}
    for name, spec in SCENARIOS.items():
        traj = traj_from_points(spec["points"])
        scenario = ae.FeederScenario(feeder_id=f"SCENARIO_{name}", feeder_type=spec["feeder_type"],
                                       capacity_mw=CAPACITY, trajectory=traj)
        rec = ae.recommend_action(scenario)
        detail[name] = {"purpose": spec["purpose"], "trajectory": traj, "recommendation": rec}
        rows.append({
            "scenario": name,
            "baseline_peak_mw": rec["baseline_forecast_mw"],
            "baseline_risk": rec["baseline_risk_level"],
            "baseline_overload": rec["baseline_overload_predicted"],
            "action_required": rec["action_required"],
            "actions": "+".join(a["resource"] for a in rec["recommended_actions"]) if rec["recommended_actions"] else "NONE",
            "total_reduction_mw": rec["total_reduction_mw"],
            "intervention_cost": rec["intervention_cost"],
            "projected_load_mw": rec["projected_load_mw"],
            "projected_risk": rec["projected_risk_level"],
            "overload_avoided": rec["overload_avoided"],
        })
    return pd.DataFrame(rows), detail


def validate(df, detail):
    print("=" * 100)
    print("CONTROLLED SCENARIO VALIDATION")
    print("=" * 100)

    r = detail["SAFE"]["recommendation"]
    assert r["action_required"] is False
    print("SAFE: no action required -- PASS")

    r = detail["BATTERY_ONLY_SUFFICIENT"]["recommendation"]
    assert r["overload_avoided"] is True and r["recommended_actions"][0]["resource"] == "BATTERY" and len(r["recommended_actions"]) == 1
    print("BATTERY_ONLY_SUFFICIENT: single cheapest sufficient resource (BATTERY) selected -- PASS")

    r = detail["INDUSTRIAL_ONLY_SUFFICIENT"]["recommendation"]
    assert r["recommended_actions"][0]["resource"] == "BATTERY"  # cheaper than Industrial, both sufficient
    print("INDUSTRIAL_ONLY_SUFFICIENT scenario (same magnitude): still picks BATTERY over INDUSTRIAL on cost -- PASS")

    r = detail["EV_ONLY_SUFFICIENT"]["recommendation"]
    assert r["overload_avoided"] is True
    print(f"EV_ONLY_SUFFICIENT: resolved via '{'+'.join(a['resource'] for a in r['recommended_actions'])}' -- PASS")

    r = detail["COMBINED_REQUIRED"]["recommendation"]
    assert r["overload_avoided"] is True and len(r["recommended_actions"]) >= 2
    print(f"COMBINED_REQUIRED: combination '{'+'.join(a['resource'] for a in r['recommended_actions'])}' -- PASS")

    r = detail["INSUFFICIENT_FLEXIBILITY"]["recommendation"]
    assert r["overload_avoided"] is False and r["remaining_overload_mw"] > 0
    print(f"INSUFFICIENT_FLEXIBILITY: honestly reports overload_avoided=False, "
          f"remaining={r['remaining_overload_mw']:.2f} MW -- PASS")

    r = detail["DURATION_LIMITED"]["recommendation"]
    baseline_peak = r["baseline_forecast_mw"]
    assert r["overload_avoided"] is False and r["projected_load_mw"] < baseline_peak
    print(f"DURATION_LIMITED: peak reduced {baseline_peak:.1f} -> {r['projected_load_mw']:.1f} MW, "
          f"overload still not avoided -- PASS")

    r = detail["HIGH_RISK_NO_OVERLOAD"]["recommendation"]
    assert r["baseline_overload_predicted"] is False
    assert r["action_required"] is True
    print(f"HIGH_RISK_NO_OVERLOAD: action recommended without overload trigger "
          f"(baseline_risk={r['baseline_risk_level']}) -- PASS")

    print("\nALL SCENARIO ASSERTIONS PASSED")


def make_plots(df, detail):
    fig, ax = plt.subplots(figsize=(11, 6))
    x = np.arange(len(df))
    width = 0.35
    ax.bar(x - width / 2, df["baseline_peak_mw"], width, label="Before (baseline peak)")
    ax.bar(x + width / 2, df["projected_load_mw"], width, label="After (projected peak)")
    ax.axhline(CAPACITY, color="red", linestyle="--", label=f"Capacity ({CAPACITY:.0f} MW)")
    ax.set_xticks(x)
    ax.set_xticklabels(df["scenario"], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Peak load (MW)")
    ax.set_title("Before vs. After: Peak Load, All Scenarios\n(CONTROLLED SIMULATION -- not real feeder events)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "evaluate_before_after_peak.png"), dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 6))
    colors = ["green" if v else "red" for v in df["overload_avoided"].where(df["baseline_overload"], other=True)]
    ax.bar(df["scenario"], df["intervention_cost"], color=colors)
    ax.set_ylabel("Intervention cost (arbitrary units)")
    ax.set_title("Intervention Cost by Scenario\n(green = trigger resolved, red = not fully resolved; CONTROLLED SIMULATION)")
    plt.xticks(rotation=30, ha="right", fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "evaluate_intervention_cost.png"), dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.bar(df["scenario"], df["total_reduction_mw"])
    ax.set_ylabel("Total reduction deployed (MW)")
    ax.set_title("Total MW Reduction by Scenario\n(CONTROLLED SIMULATION)")
    plt.xticks(rotation=30, ha="right", fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "evaluate_reduction_mw.png"), dpi=120)
    plt.close(fig)

    print(f"Saved 3 plots under: {FIG_DIR}")


if __name__ == "__main__":
    df, detail = run_all()
    print(df.to_string(index=False))
    validate(df, detail)
    make_plots(df, detail)

    n_baseline_overload = int(df["baseline_overload"].sum())
    n_overload_avoided = int((df["baseline_overload"] & df["overload_avoided"]).sum())
    n_insufficient = int((df["baseline_overload"] & ~df["overload_avoided"]).sum())
    avg_reduction = float(df.loc[df["action_required"], "total_reduction_mw"].mean())

    summary = {
        "n_scenarios": len(df),
        "n_baseline_overload": n_baseline_overload,
        "n_overload_avoided": n_overload_avoided,
        "n_insufficient_flexibility_cases": n_insufficient,
        "avg_mw_reduction_where_action_taken": avg_reduction,
        "scenario_results": df.to_dict(orient="records"),
    }
    df.to_csv(os.path.join(DATA_DIR, "action_engine_evaluation_results.csv"), index=False)
    with open(os.path.join(REPORTS_DIR, "action_engine_evaluation_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\nOverloads before: {n_baseline_overload}, avoided: {n_overload_avoided}, "
          f"insufficient-flexibility cases: {n_insufficient}")
    print(f"Average MW reduction where action was taken: {avg_reduction:.2f}")
    print(f"Saved: ml/data/action_engine_evaluation_results.csv")
    print(f"Saved: ml/reports/action_engine_evaluation_summary.json")
    print("\nDONE.")
