"""
GridGuard AI - Stress Engine sanity analysis (validation only).

Does NOT modify feeder_generator.py, stress_engine.py, the XGBoost model, or
the feature pipeline -- it only imports and calls their existing, unmodified
functions across a historical rolling window to check whether the Grid
Stress Engine behaves sensibly. This is an engineering sanity check, NOT a
scientific calibration -- there is no real feeder outage/overload label data
anywhere in this project to calibrate against.
"""
import os
import sys
import json
import time

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import feeder_generator as fg
import stress_engine as se

PROC_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
FIG_DIR = os.path.join(os.path.dirname(__file__), "..", "reports", "figures", "stress_sanity")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
os.makedirs(FIG_DIR, exist_ok=True)

SEED = fg.SEED

# ---------------------------------------------------------------------------
# 0. Load data / model (read-only) and set up feeders + capacities
# ---------------------------------------------------------------------------
print("Loading data and saved model (read-only)...")
national_demand = fg.load_national_demand_series()
model, model_meta, features_full = fg.load_saved_model_and_features()
feature_cols = model_meta["feature_list"]

test_df = pd.read_csv(os.path.join(PROC_DIR, "test.csv"))
test_df["origin_datetime"] = pd.to_datetime(test_df["origin_datetime"])
test_df = test_df.sort_values("origin_datetime").reset_index(drop=True)
assert test_df["origin_datetime"].is_monotonic_increasing

PERIOD_START = test_df["origin_datetime"].min()
PERIOD_END = test_df["origin_datetime"].max()
print(f"Rolling period used: {PERIOD_START} -> {PERIOD_END} ({len(test_df)} origins, existing test.csv)")

feeders = fg.get_feeder_definitions()
historical_feeder_loads = fg.allocate_feeder_loads(national_demand, feeders, seed=SEED, add_noise=True)
capacities = fg.compute_feeder_capacities(feeders, historical_feeder_loads)
avg_hourly_shape = fg.historical_average_hourly_shape(national_demand)

feeder_ids = [f["id"] for f in feeders]
feeder_type_map = {f["id"]: f["type"] for f in feeders}

# ---------------------------------------------------------------------------
# 1. Vectorized national forecast for every origin in the period
# ---------------------------------------------------------------------------
print("Predicting 24h-ahead national demand for every origin (existing saved model, unmodified)...")
X_all = test_df[feature_cols].astype(float)
forecast_national_all = model.predict(X_all)
current_national_all = test_df["lag_0h_nat_demand"].values

# ---------------------------------------------------------------------------
# 2. Roll the stress engine across every (origin, feeder) pair
# ---------------------------------------------------------------------------
print("Rolling feeder trajectories + stress engine across the period (this can take a bit)...")
t0 = time.time()
records = []

for idx in range(len(test_df)):
    origin_dt = test_df["origin_datetime"].iloc[idx]
    current_nat = float(current_national_all[idx])
    forecast_nat = float(forecast_national_all[idx])

    national_traj = fg.build_national_trajectory(origin_dt, current_nat, forecast_nat, avg_hourly_shape)
    feeder_traj_df = fg.build_feeder_trajectories(national_traj, feeders)  # unmodified function, add_noise=False

    for fid in feeder_ids:
        traj = feeder_traj_df[fid]
        cap = float(capacities.loc[fid, "capacity_mw"])
        current_load = float(traj.iloc[0])
        forecast_load = float(traj.iloc[-1])
        util_traj = (traj / cap).values
        voltage_traj = fg.simulate_voltage(util_traj, seed=SEED, add_noise=False)  # deterministic, matches run_example
        current_voltage = float(voltage_traj[0])

        score, components = se.compute_stress_score(current_load, forecast_load, cap, current_voltage)
        risk = se.classify_stress(score)
        tto = se.time_to_overload(traj, cap)

        records.append({
            "origin_datetime": origin_dt,
            "feeder_id": fid,
            "feeder_type": feeder_type_map[fid],
            "capacity_mw": cap,
            "current_load_mw": current_load,
            "forecast_load_mw": forecast_load,
            "current_utilization": current_load / cap,
            "forecast_utilization": forecast_load / cap,
            "voltage_pu": current_voltage,
            "stress_score": score,
            "risk_level": risk,
            "comp_current_utilization": components["current_utilization"],
            "comp_forecast_utilization": components["forecast_utilization"],
            "comp_trajectory_slope": components["trajectory_slope"],
            "comp_voltage_stress": components["voltage_stress"],
            "comp_headroom": components["headroom"],
            "overload_predicted": tto["overload_predicted"],
            "time_to_overload_hours": tto["time_to_overload_hours"],
        })
    if (idx + 1) % 1000 == 0:
        print(f"  ...{idx + 1}/{len(test_df)} origins processed ({time.time()-t0:.1f}s elapsed)")

results = pd.DataFrame(records)
elapsed = time.time() - t0
print(f"Done: {len(results)} feeder-time observations in {elapsed:.1f}s")

results.to_csv(os.path.join(PROC_DIR, "..", "stress_sanity_rolling_results.csv"), index=False)

# ---------------------------------------------------------------------------
# Sanity: no NaN/inf anywhere in the rolled results
# ---------------------------------------------------------------------------
numeric_cols = results.select_dtypes(include=[np.number]).columns
assert np.isfinite(results[numeric_cols].values).all(), "Non-finite values found in rolled results!"
print("Confirmed: no NaN/inf values in rolled results.")

# ===========================================================================
# 1. Distribution of stress scores
# ===========================================================================
print("\n" + "=" * 80)
print("1. Distribution of stress scores")
print("=" * 80)

overall_stats = results["stress_score"].describe()
print("\nOverall stress score stats:")
print(overall_stats)

risk_counts_overall = results["risk_level"].value_counts(normalize=True).reindex(["LOW", "MODERATE", "HIGH", "CRITICAL"]).fillna(0) * 100
print("\nOverall risk level distribution (%):")
print(risk_counts_overall.round(2))

per_feeder_stats = results.groupby("feeder_id")["stress_score"].agg(["mean", "median", "std", "min", "max"])
print("\nPer-feeder stress score stats:")
print(per_feeder_stats.round(2))

per_feeder_risk = (results.groupby("feeder_id")["risk_level"]
                    .value_counts(normalize=True).unstack().reindex(columns=["LOW", "MODERATE", "HIGH", "CRITICAL"]).fillna(0) * 100)
print("\nPer-feeder risk level distribution (%):")
print(per_feeder_risk.round(2))

# ===========================================================================
# 2. Utilization vs stress relationship
# ===========================================================================
print("\n" + "=" * 80)
print("2. Utilization vs stress relationship")
print("=" * 80)

pearson_current, p_current = stats.pearsonr(results["current_utilization"], results["stress_score"])
spearman_current, sp_current = stats.spearmanr(results["current_utilization"], results["stress_score"])
pearson_forecast, p_forecast = stats.pearsonr(results["forecast_utilization"], results["stress_score"])
spearman_forecast, sp_forecast = stats.spearmanr(results["forecast_utilization"], results["stress_score"])

print(f"current_utilization vs stress_score: Pearson r={pearson_current:.4f} (p={p_current:.2e}), "
      f"Spearman rho={spearman_current:.4f} (p={sp_current:.2e})")
print(f"forecast_utilization vs stress_score: Pearson r={pearson_forecast:.4f} (p={p_forecast:.2e}), "
      f"Spearman rho={spearman_forecast:.4f} (p={sp_forecast:.2e})")

fig, ax = plt.subplots(figsize=(7, 6))
ax.scatter(results["current_utilization"], results["stress_score"], s=3, alpha=0.15)
ax.set_xlabel("Current utilization (load / capacity)")
ax.set_ylabel("Stress score")
ax.set_title(f"Current Utilization vs Stress Score (Pearson r={pearson_current:.3f})")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "current_utilization_vs_stress.png"), dpi=120)
plt.close(fig)

fig, ax = plt.subplots(figsize=(7, 6))
ax.scatter(results["forecast_utilization"], results["stress_score"], s=3, alpha=0.15, color="darkorange")
ax.set_xlabel("Forecast utilization (24h-ahead load / capacity)")
ax.set_ylabel("Stress score")
ax.set_title(f"Forecast Utilization vs Stress Score (Pearson r={pearson_forecast:.3f})")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "forecast_utilization_vs_stress.png"), dpi=120)
plt.close(fig)

# ===========================================================================
# 3. Controlled monotonicity property checks
# ===========================================================================
print("\n" + "=" * 80)
print("3. Controlled monotonicity property checks")
print("=" * 80)

def check_monotonic_nondecreasing(x_values, scores, tol=1e-9):
    diffs = np.diff(scores)
    return bool(np.all(diffs >= -tol)), diffs.min()

monotonicity_results = {}

# (a) increasing current_load, holding forecast_load/capacity/voltage fixed
capacity_fixed, forecast_fixed, voltage_fixed = 100.0, 60.0, 0.98
current_sweep = np.linspace(0, 150, 200)
scores_a = [se.compute_stress_score(c, forecast_fixed, capacity_fixed, voltage_fixed)[0] for c in current_sweep]
ok_a, mindiff_a = check_monotonic_nondecreasing(current_sweep, scores_a)
monotonicity_results["increasing_current_utilization"] = {"passed": ok_a, "min_diff": float(mindiff_a)}
print(f"(a) Increasing current_load (0->150, cap=100, forecast=60, voltage=0.98 fixed): "
      f"non-decreasing = {ok_a} (min step diff = {mindiff_a:.6f})")

# (b) increasing forecast_load, holding current_load/capacity/voltage fixed
current_fixed = 40.0
forecast_sweep = np.linspace(0, 150, 200)
scores_b = [se.compute_stress_score(current_fixed, fc, capacity_fixed, voltage_fixed)[0] for fc in forecast_sweep]
ok_b, mindiff_b = check_monotonic_nondecreasing(forecast_sweep, scores_b)
monotonicity_results["increasing_forecast_utilization"] = {"passed": ok_b, "min_diff": float(mindiff_b)}
print(f"(b) Increasing forecast_load (0->150, cap=100, current=40, voltage=0.98 fixed): "
      f"non-decreasing = {ok_b} (min step diff = {mindiff_b:.6f})")

# (c) increasing positive trajectory slope directly (forecast - current growing, current fixed low)
current_fixed_c = 20.0
slope_forecast_sweep = np.linspace(20, 180, 200)  # forecast >= current, slope >= 0 growing
scores_c = [se.compute_stress_score(current_fixed_c, fc, capacity_fixed, voltage_fixed)[0] for fc in slope_forecast_sweep]
ok_c, mindiff_c = check_monotonic_nondecreasing(slope_forecast_sweep, scores_c)
monotonicity_results["increasing_positive_trajectory_slope"] = {"passed": ok_c, "min_diff": float(mindiff_c)}
print(f"(c) Increasing positive trajectory slope (current=20 fixed, forecast 20->180, cap=100): "
      f"non-decreasing = {ok_c} (min step diff = {mindiff_c:.6f})")

# (d) worsening voltage (decreasing voltage_pu), holding current/forecast/capacity fixed
current_fixed_d, forecast_fixed_d = 60.0, 60.0
voltage_sweep = np.linspace(1.05, 0.80, 200)  # decreasing voltage = worsening
scores_d = [se.compute_stress_score(current_fixed_d, forecast_fixed_d, capacity_fixed, v)[0] for v in voltage_sweep]
ok_d, mindiff_d = check_monotonic_nondecreasing(voltage_sweep, scores_d)  # x decreasing, so check score is non-decreasing as we iterate (voltage worsening)
monotonicity_results["worsening_voltage"] = {"passed": ok_d, "min_diff": float(mindiff_d)}
print(f"(d) Worsening voltage (1.05->0.80, current=forecast=60, cap=100 fixed): "
      f"non-decreasing (as voltage drops) = {ok_d} (min step diff = {mindiff_d:.6f})")

# (e) reducing headroom via decreasing capacity, holding current/forecast_load fixed absolute MW
current_fixed_e, forecast_fixed_e, voltage_fixed_e = 50.0, 50.0, 0.98
capacity_sweep = np.linspace(200, 51, 200)  # decreasing capacity => decreasing headroom, increasing utilization
scores_e = [se.compute_stress_score(current_fixed_e, forecast_fixed_e, cap, voltage_fixed_e)[0] for cap in capacity_sweep]
ok_e, mindiff_e = check_monotonic_nondecreasing(capacity_sweep, scores_e)  # capacity decreasing across iteration => score should be non-decreasing
monotonicity_results["reducing_headroom_via_capacity"] = {"passed": ok_e, "min_diff": float(mindiff_e)}
print(f"(e) Reducing headroom via shrinking capacity (200->51, load=50 fixed): "
      f"non-decreasing (as capacity shrinks) = {ok_e} (min step diff = {mindiff_e:.6f})")

all_monotonic_passed = all(v["passed"] for v in monotonicity_results.values())
print(f"\nAll monotonicity properties passed: {all_monotonic_passed}")

# ===========================================================================
# 4. Component contribution analysis
# ===========================================================================
print("\n" + "=" * 80)
print("4. Component contribution analysis")
print("=" * 80)

# Verify the headroom == current_utilization identity directly and empirically
identity_check = np.allclose(results["comp_headroom"], results["comp_current_utilization"])
print(f"Identity check: comp_headroom == comp_current_utilization for ALL {len(results)} rolled observations: {identity_check}")
max_abs_diff = (results["comp_headroom"] - results["comp_current_utilization"]).abs().max()
print(f"Max |headroom - current_utilization| across all observations: {max_abs_diff:.2e}")

# also verify algebraically over the monotonicity sweep grids for extra confidence
alg_diffs = []
for c in np.linspace(0, 200, 50):
    for cap in [10, 100, 500]:
        _, comps = se.compute_stress_score(c, c, cap, 1.0)
        alg_diffs.append(abs(comps["headroom"] - comps["current_utilization"]))
print(f"Algebraic sweep max diff (should be ~0): {max(alg_diffs):.2e}")

# representative scenario examples across risk bands (pick closest-to-median observation per band, if present)
component_cols = ["comp_current_utilization", "comp_forecast_utilization", "comp_trajectory_slope",
                   "comp_voltage_stress", "comp_headroom"]
weights = se.STRESS_WEIGHTS
examples = {}
for level in ["LOW", "MODERATE", "HIGH", "CRITICAL"]:
    subset = results[results["risk_level"] == level]
    if len(subset) == 0:
        examples[level] = None
        continue
    target_score = subset["stress_score"].median()
    row = subset.iloc[(subset["stress_score"] - target_score).abs().argsort().iloc[0]]
    contributions = {c: float(row[c] * weights[c.replace("comp_", "")]) for c in component_cols}
    examples[level] = {
        "origin_datetime": str(row["origin_datetime"]),
        "feeder_id": row["feeder_id"],
        "feeder_type": row["feeder_type"],
        "stress_score": float(row["stress_score"]),
        "current_utilization": float(row["current_utilization"]),
        "forecast_utilization": float(row["forecast_utilization"]),
        "voltage_pu": float(row["voltage_pu"]),
        "component_raw_values": {c: float(row[c]) for c in component_cols},
        "component_score_contributions": contributions,
        "component_pct_of_score": {k: (v / row["stress_score"] * 100 if row["stress_score"] > 0 else 0) for k, v in contributions.items()},
    }
    print(f"\n{level} example (feeder {row['feeder_id']}, {row['feeder_type']}, {row['origin_datetime']}): "
          f"score={row['stress_score']:.2f}")
    for c in component_cols:
        comp_name = c.replace("comp_", "")
        print(f"    {comp_name}: raw={row[c]:.3f} x weight={weights[comp_name]:.2f} = {row[c]*weights[comp_name]*100:.2f} pts "
              f"({row[c]*weights[comp_name]*100/row['stress_score']*100 if row['stress_score']>0 else 0:.1f}% of score)")

# ===========================================================================
# 5. Event usefulness (distribution shape assessment, not threshold tuning)
# ===========================================================================
print("\n" + "=" * 80)
print("5. Event usefulness")
print("=" * 80)
print("Overall risk level distribution (%):")
print(risk_counts_overall.round(2))

fig, ax = plt.subplots(figsize=(8, 5))
ax.hist(results["stress_score"], bins=50, color="steelblue")
for edge in [30, 60, 80]:
    ax.axvline(edge, color="red", linestyle="--", alpha=0.6)
ax.set_title("Distribution of Stress Scores (all feeders, full test period)")
ax.set_xlabel("Stress score")
ax.set_ylabel("Count (feeder-hours)")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "stress_score_distribution.png"), dpi=120)
plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 6))
results.boxplot(column="stress_score", by="feeder_id", ax=ax)
ax.set_title("Stress Score by Feeder")
plt.suptitle("")
ax.set_xlabel("Feeder")
ax.set_ylabel("Stress score")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "stress_by_feeder.png"), dpi=120)
plt.close(fig)

# ===========================================================================
# 6. Time-to-overload relationship
# ===========================================================================
print("\n" + "=" * 80)
print("6. Time-to-overload relationship")
print("=" * 80)

overload_rows = results[results["overload_predicted"] == True].copy()
print(f"Rows with overload predicted: {len(overload_rows)} / {len(results)} ({len(overload_rows)/len(results)*100:.3f}%)")

if len(overload_rows) >= 5:
    r_tto, p_tto = stats.pearsonr(overload_rows["time_to_overload_hours"], overload_rows["stress_score"])
    rho_tto, sp_tto = stats.spearmanr(overload_rows["time_to_overload_hours"], overload_rows["stress_score"])
    print(f"time_to_overload_hours vs stress_score (overload-predicted rows only): "
          f"Pearson r={r_tto:.4f} (p={p_tto:.2e}), Spearman rho={rho_tto:.4f} (p={sp_tto:.2e})")

    counterexamples = overload_rows.sort_values("time_to_overload_hours")
    print("\nShortest time-to-overload cases (expect high stress):")
    print(counterexamples[["origin_datetime", "feeder_id", "time_to_overload_hours", "stress_score", "risk_level"]].head(10).to_string())

    # counterexample search: short time-to-overload but NOT high/critical stress
    short_tto_low_stress = overload_rows[(overload_rows["time_to_overload_hours"] <= 6) & (overload_rows["stress_score"] < 61)]
    print(f"\nCounterexamples (time_to_overload <= 6h but stress_score < 61 / not HIGH or CRITICAL): {len(short_tto_low_stress)}")
    if len(short_tto_low_stress) > 0:
        print(short_tto_low_stress[["origin_datetime", "feeder_id", "time_to_overload_hours", "stress_score",
                                     "current_utilization", "forecast_utilization"]].head(10).to_string())
else:
    r_tto, p_tto, rho_tto, sp_tto = None, None, None, None
    counterexamples = pd.DataFrame()
    short_tto_low_stress = pd.DataFrame()
    print("Too few overload-predicted rows in this period for a meaningful correlation.")

if len(overload_rows) > 0:
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(overload_rows["time_to_overload_hours"], overload_rows["stress_score"], s=20, alpha=0.6)
    ax.set_xlabel("Time to overload (hours)")
    ax.set_ylabel("Stress score")
    ax.set_title("Time to Overload vs Stress Score (overload-predicted cases only)")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "time_to_overload_vs_stress.png"), dpi=120)
    plt.close(fig)

# ===========================================================================
# 7. Example stress trajectory plot (pick the feeder/origin with the highest
#    observed stress score in the rolled period, for a concrete illustration)
# ===========================================================================
top_row = results.loc[results["stress_score"].idxmax()]
top_origin = top_row["origin_datetime"]
top_feeder = top_row["feeder_id"]
print(f"\nHighest-stress observation in rolled period: feeder {top_feeder} at {top_origin}, score={top_row['stress_score']:.2f}")

current_nat_top = float(test_df.loc[test_df["origin_datetime"] == top_origin, "lag_0h_nat_demand"].iloc[0])
X_top = test_df.loc[test_df["origin_datetime"] == top_origin, feature_cols].astype(float)
forecast_nat_top = float(model.predict(X_top)[0])
national_traj_top = fg.build_national_trajectory(top_origin, current_nat_top, forecast_nat_top, avg_hourly_shape)
feeder_traj_top = fg.build_feeder_trajectories(national_traj_top, feeders)[top_feeder]
cap_top = float(capacities.loc[top_feeder, "capacity_mw"])

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(feeder_traj_top.index, feeder_traj_top.values, marker="o", markersize=3, label=f"{top_feeder} forecast trajectory")
ax.axhline(cap_top, color="red", linestyle="--", label=f"Capacity ({cap_top:.2f} MW)")
ax.set_title(f"Example Stress Trajectory — Feeder {top_feeder} ({feeder_type_map[top_feeder]}), origin {top_origin}\n"
             f"Stress score={top_row['stress_score']:.1f} ({top_row['risk_level']})")
ax.set_ylabel("Load (MW)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "example_stress_trajectory.png"), dpi=120)
plt.close(fig)

# ===========================================================================
# Save all summary numbers for the report
# ===========================================================================
summary = {
    "period": {"start": str(PERIOD_START), "end": str(PERIOD_END), "n_origins": int(len(test_df)),
               "n_feeder_time_observations": int(len(results))},
    "overall_stats": overall_stats.to_dict(),
    "overall_risk_distribution_pct": risk_counts_overall.round(4).to_dict(),
    "per_feeder_stats": per_feeder_stats.round(4).to_dict(orient="index"),
    "per_feeder_risk_distribution_pct": per_feeder_risk.round(4).to_dict(orient="index"),
    "correlations": {
        "current_utilization_vs_stress": {"pearson_r": float(pearson_current), "pearson_p": float(p_current),
                                            "spearman_rho": float(spearman_current), "spearman_p": float(sp_current)},
        "forecast_utilization_vs_stress": {"pearson_r": float(pearson_forecast), "pearson_p": float(p_forecast),
                                             "spearman_rho": float(spearman_forecast), "spearman_p": float(sp_forecast)},
    },
    "monotonicity_checks": monotonicity_results,
    "all_monotonicity_passed": bool(all_monotonic_passed),
    "headroom_current_utilization_identity": {
        "identical_in_rolled_data": bool(identity_check),
        "max_abs_diff_rolled_data": float(max_abs_diff),
        "max_abs_diff_algebraic_sweep": float(max(alg_diffs)),
        "combined_effective_weight": float(weights["current_utilization"] + weights["headroom"]),
    },
    "component_examples": examples,
    "overload": {
        "n_overload_predicted": int(len(overload_rows)),
        "pct_overload_predicted": float(len(overload_rows) / len(results) * 100),
        "correlation_time_to_overload_vs_stress": (
            {"pearson_r": float(r_tto), "pearson_p": float(p_tto), "spearman_rho": float(rho_tto), "spearman_p": float(sp_tto)}
            if r_tto is not None else None
        ),
        "n_counterexamples_short_tto_low_stress": int(len(short_tto_low_stress)),
    },
    "highest_stress_observation": {
        "origin_datetime": str(top_origin), "feeder_id": top_feeder, "stress_score": float(top_row["stress_score"]),
        "risk_level": top_row["risk_level"],
    },
}

out_path = os.path.join(REPORTS_DIR, "stress_engine_sanity_raw.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, default=str)
print(f"\nSaved: {out_path}")
print(f"Saved plots under: {FIG_DIR}")
print("\nDONE.")
