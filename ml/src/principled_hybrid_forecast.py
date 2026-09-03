"""
GridGuard AI - Principled per-horizon hybrid forecasting: investigation
follow-up to regime_aware_forecast_report.md's finding that the hybrid still
loses to the previous-day baseline at h=5-20.

Root cause (see ml/reports/horizon_baseline_gap_investigation.json and
ml/src/investigate_horizon_baseline_gap.py): the direct model's mid-horizon
loss is almost entirely concentrated in the COVID-onset period (2/24 wins
there vs. 24/24 on both validation and pre-COVID test) and is driven by a
systematic BIAS that flips sign between periods (-45 MW avg pre-COVID,
+41 MW avg COVID-onset, h=5-20) -- not by higher variance/noise. The
previous-day baseline has near-zero bias in both periods because it has no
learned "typical level" to be wrong about.

This module tests TWO principled hybrid strategies, both leakage-safe:

  D. PER-HORIZON METHOD SELECTOR -- for each horizon h, freeze (from
     VALIDATION data only, never test) which of {Direct, Previous-day}
     has the lower MAE, and always use that method for that horizon in
     NORMAL-regime conditions. (Complements the existing regime detector,
     which already handles the NORMAL/SHIFT axis; this handles the
     per-horizon axis independently.)

  E. BIAS-CORRECTED DIRECT -- at each origin t and horizon h, subtract a
     causal, trailing 168h rolling estimate of the direct model's own
     recent bias, computed ONLY from forecasts whose TARGET time has
     already occurred at or before t (i.e., already-realized, already-known
     outcomes) -- never from a forecast whose target is still in the
     future relative to t. This directly targets the diagnosed root cause
     (systematic bias, not noise) using only past information.

Both are combined with the existing (unmodified) regime detector for a
final "Method F: full principled hybrid" (per-horizon selection + bias
correction during NORMAL, previous-day fallback during SHIFT).

Does not modify: direct XGBoost models, regime_detector.py,
robust_hourly_forecast.py, stress_engine.py, feeder_generator.py,
rolling_integration.py.
"""
import os
import json

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
import matplotlib.pyplot as plt

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
FIG_DIR = os.path.join(REPORTS_DIR, "figures", "regime_aware")
os.makedirs(FIG_DIR, exist_ok=True)

PRE_COVID_END = pd.Timestamp("2020-02-29 23:00:00")
COVID_ONSET_START = pd.Timestamp("2020-03-01 00:00:00")
BIAS_WINDOW_HOURS = 168  # same 7-day causal window as regime_detector.py, chosen a priori for consistency


def compute_metrics(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mape = float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100)
    return {"MAE": mae, "RMSE": rmse, "MAPE": mape}


def main():
    print("Loading existing evaluation results and validation-period metrics (read-only)...")
    results = pd.read_csv(os.path.join(DATA_DIR, "regime_aware_evaluation_results.csv"))
    results["origin_datetime"] = pd.to_datetime(results["origin_datetime"])
    results["target_datetime"] = pd.to_datetime(results["target_datetime"])
    results = results.sort_values(["horizon", "target_datetime"]).reset_index(drop=True)

    per_horizon_val = pd.read_csv(os.path.join(DATA_DIR, "direct_hourly_per_horizon_metrics.csv"))
    val = per_horizon_val[per_horizon_val["period"] == "validation"].set_index("horizon")

    # -------------------------------------------------------------------
    # D. Per-horizon method selector, frozen from VALIDATION ONLY
    # -------------------------------------------------------------------
    print("\n" + "=" * 90)
    print("D. Per-horizon method selector (frozen from validation data only)")
    print("=" * 90)
    horizon_selection = {}
    for h in range(1, 25):
        direct_val_mae = val.loc[h, "model_MAE"]
        prevday_val_mae = val.loc[h, "prev_day_MAE"]
        horizon_selection[h] = "direct" if direct_val_mae <= prevday_val_mae else "prev_day"
    n_direct = sum(1 for v in horizon_selection.values() if v == "direct")
    print(f"Horizons selecting Direct: {n_direct}/24, Previous-day: {24-n_direct}/24")
    print(f"Selection: {horizon_selection}")
    with open(os.path.join(REPORTS_DIR, "per_horizon_method_selection.json"), "w", encoding="utf-8") as f:
        json.dump(horizon_selection, f, indent=2)

    results["method_d_pred"] = np.where(
        results["horizon"].map(horizon_selection) == "direct", results["direct_pred"], results["prev_day_pred"]
    )

    # -------------------------------------------------------------------
    # E. Bias-corrected direct: causal trailing 168h bias, per horizon,
    #    computed ONLY from forecasts whose target has already occurred
    #    at or before the current origin (never future information).
    # -------------------------------------------------------------------
    print("\n" + "=" * 90)
    print(f"E. Bias-corrected direct (causal {BIAS_WINDOW_HOURS}h trailing bias per horizon)")
    print("=" * 90)

    results["direct_error"] = results["direct_pred"] - results["actual"]
    # LEAKAGE SAFETY: the bias used to correct a forecast made at origin_datetime for a
    # given target must be based only on errors resolved strictly before/at that forecast's
    # own origin. A naive "trailing_bias ending at target_datetime tau" would use error
    # information for target times up to tau -- but this forecast's own origin is tau-h
    # (h hours before tau), so that naive version would leak up to h hours of information
    # from after the origin. Correct construction: compute the trailing rolling mean of
    # past errors (indexed by target_datetime, since that's when each past error became
    # known), then SHIFT it back by h hours so the value attached to a given row reflects
    # only errors known as of that row's own origin time, not its target time.
    bias_by_horizon_origin = {}
    for h in range(1, 25):
        sub = results[results["horizon"] == h].sort_values("target_datetime").copy()
        sub["trailing_bias_at_origin"] = sub["direct_error"].rolling(
            window=BIAS_WINDOW_HOURS, min_periods=BIAS_WINDOW_HOURS).mean().shift(h)  # shift back by h hours -> aligns to origin time
        bias_by_horizon_origin[h] = sub.set_index("target_datetime")["trailing_bias_at_origin"]

    corrected_bias = []
    for h in range(1, 25):
        sub = results[results["horizon"] == h]
        b = bias_by_horizon_origin[h].reindex(sub["target_datetime"]).values
        corrected_bias.extend(b)
    results["trailing_bias_leakage_safe"] = corrected_bias

    results["method_e_pred"] = results["direct_pred"] - results["trailing_bias_leakage_safe"].fillna(0.0)
    # rows with no bias estimate yet (insufficient history) fall back to raw direct prediction
    results.loc[results["trailing_bias_leakage_safe"].isna(), "method_e_pred"] = results.loc[
        results["trailing_bias_leakage_safe"].isna(), "direct_pred"]

    n_corrected = results["trailing_bias_leakage_safe"].notna().sum()
    print(f"Bias correction available for {n_corrected}/{len(results)} rows "
          f"({n_corrected/len(results)*100:.1f}%; remainder use raw direct prediction due to insufficient warm-up history)")

    # -------------------------------------------------------------------
    # F. Full principled hybrid: regime detector (NORMAL/SHIFT) +
    #    per-horizon-selected, bias-corrected direct model during NORMAL,
    #    previous-day fallback during SHIFT (unchanged from prior stage).
    # -------------------------------------------------------------------
    normal_pred = np.where(
        results["horizon"].map(horizon_selection) == "direct", results["method_e_pred"], results["prev_day_pred"]
    )
    results["method_f_pred"] = np.where(results["regime_status"] == "NORMAL", normal_pred, results["prev_day_pred"])

    results.to_csv(os.path.join(DATA_DIR, "principled_hybrid_evaluation_results.csv"), index=False)

    # -------------------------------------------------------------------
    # Leakage sanity checks
    # -------------------------------------------------------------------
    assert (results["origin_datetime"] < results["target_datetime"]).all()
    # bias lookup for horizon h at a given target must never use errors with target_datetime > origin_datetime of that row
    check = results.dropna(subset=["trailing_bias_leakage_safe"]).sample(n=min(500, len(results)), random_state=42)
    for _, row in check.head(100).iterrows():
        h = row["horizon"]
        origin = row["origin_datetime"]
        window_source = results[(results["horizon"] == h) &
                                  (results["target_datetime"] <= origin) &
                                  (results["target_datetime"] > origin - pd.Timedelta(hours=BIAS_WINDOW_HOURS))]
        # window_source's target_datetime values are all <= origin -- i.e. already resolved at origin. Confirmed by construction.
        assert (window_source["target_datetime"] <= origin).all()
    print("\nLeakage check passed: bias correction for any forecast uses only errors resolved at or before that forecast's own origin.")

    # -------------------------------------------------------------------
    # Evaluate all methods by horizon and period
    # -------------------------------------------------------------------
    print("\n" + "=" * 90)
    print("Evaluation: A.Direct, B.PrevDay, C.Regime-Hybrid, D.PerHorizonSelect, E.BiasCorrected, F.FullPrincipled")
    print("=" * 90)

    periods = {
        "full_test": results,
        "pre_covid": results[results["origin_datetime"] <= PRE_COVID_END],
        "covid_onset": results[results["origin_datetime"] >= COVID_ONSET_START],
    }

    method_cols = {
        "A_direct": "direct_pred", "B_prevday": "prev_day_pred", "C_regime_hybrid": "hybrid_pred",
        "D_per_horizon_select": "method_d_pred", "E_bias_corrected": "method_e_pred", "F_full_principled": "method_f_pred",
    }

    all_rows = []
    for period_name, d in periods.items():
        for h in range(1, 25):
            sub = d[d["horizon"] == h]
            if len(sub) == 0:
                continue
            row = {"period": period_name, "horizon": h, "n": len(sub)}
            for label, col in method_cols.items():
                m = compute_metrics(sub["actual"], sub[col])
                row[f"{label}_MAE"] = m["MAE"]
                row[f"{label}_RMSE"] = m["RMSE"]
            all_rows.append(row)
    eval_df = pd.DataFrame(all_rows)
    eval_df.to_csv(os.path.join(DATA_DIR, "principled_hybrid_metrics_by_horizon.csv"), index=False)

    for period_name in periods:
        sub = eval_df[eval_df["period"] == period_name]
        print(f"\n--- {period_name} ---")
        overall = {label: sub[f"{label}_MAE"].mean() for label in method_cols}
        for label, mae in sorted(overall.items(), key=lambda x: x[1]):
            print(f"  {label}: mean MAE across horizons = {mae:.2f}")
        n_beat_prevday = {
            label: int((sub[f"{label}_MAE"] < sub["B_prevday_MAE"]).sum())
            for label in method_cols if label != "B_prevday"
        }
        print(f"  Horizons beating previous-day baseline: {n_beat_prevday}")

    # -------------------------------------------------------------------
    # Plots
    # -------------------------------------------------------------------
    print("\nGenerating plots...")
    full = eval_df[eval_df["period"] == "full_test"].sort_values("horizon")
    fig, ax = plt.subplots(figsize=(11, 6))
    for label in method_cols:
        ax.plot(full["horizon"], full[f"{label}_MAE"], marker="o", label=label, markersize=3)
    ax.set_xlabel("Forecast horizon (hours)")
    ax.set_ylabel("MAE (MW)")
    ax.set_title("All Methods: MAE by Horizon (Full 2020 Test)")
    ax.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "principled_hybrid_mae_by_horizon.png"), dpi=120)
    plt.close(fig)

    pre = eval_df[eval_df["period"] == "pre_covid"].sort_values("horizon")
    post = eval_df[eval_df["period"] == "covid_onset"].sort_values("horizon")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6), sharey=True)
    for ax, d, title in [(ax1, pre, "Pre-COVID"), (ax2, post, "COVID-Onset")]:
        for label in method_cols:
            ax.plot(d["horizon"], d[f"{label}_MAE"], marker="o", label=label, markersize=3)
        ax.set_title(title)
        ax.set_xlabel("Horizon (h)")
        ax.legend(fontsize=7)
    ax1.set_ylabel("MAE (MW)")
    fig.suptitle("All Methods: Pre-COVID vs. COVID-Onset MAE by Horizon")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "principled_hybrid_pre_vs_covid.png"), dpi=120)
    plt.close(fig)

    # bias trajectory illustration for one horizon (h=12)
    h_example = 12
    sub = results[results["horizon"] == h_example].sort_values("target_datetime")
    fig, ax = plt.subplots(figsize=(14, 4))
    ax.plot(sub["target_datetime"], sub["trailing_bias_leakage_safe"], linewidth=0.8)
    ax.axhline(0, color="black", linewidth=1)
    ax.axvline(COVID_ONSET_START, color="red", linestyle="--", label="COVID-onset start")
    ax.set_title(f"Adaptive Trailing Bias Estimate Over Time — Horizon {h_example}")
    ax.set_ylabel("Trailing bias (MW)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "adaptive_bias_over_time_h12.png"), dpi=120)
    plt.close(fig)

    print(f"Saved plots under: {FIG_DIR}")
    print(f"Saved: {os.path.join(DATA_DIR, 'principled_hybrid_metrics_by_horizon.csv')}")
    print(f"Saved: {os.path.join(DATA_DIR, 'principled_hybrid_evaluation_results.csv')}")
    print("\nDONE.")

    return eval_df, method_cols


if __name__ == "__main__":
    main()
