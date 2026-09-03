# GridGuard AI — Why h=5-20 Loses to Previous-Day, and a Principled Per-Horizon Hybrid

**Scripts:** [ml/src/investigate_horizon_baseline_gap.py](../src/investigate_horizon_baseline_gap.py), [ml/src/principled_hybrid_forecast.py](../src/principled_hybrid_forecast.py)
**Data:** `ml/data/horizon_bias_variance_decomposition.csv`, `ml/data/principled_hybrid_metrics_by_horizon.csv`, `ml/data/principled_hybrid_evaluation_results.csv`, `ml/reports/horizon_baseline_gap_investigation.json`, `ml/reports/per_horizon_method_selection.json`

**Not modified:** direct XGBoost models, `regime_detector.py`, `robust_hourly_forecast.py`, `stress_engine.py`, `feeder_generator.py`, `rolling_integration.py`. This is a read-only investigation plus one new, standalone evaluation script.

---

## Part 1 — Investigation: why does h=5-20 lose to previous-day?

### It doesn't, in-distribution

| Period | Direct beats strongest baseline |
|---|---|
| **Validation (2019)** | **24 / 24 horizons** |
| **Pre-COVID test (Jan-Feb 2020)** | **24 / 24 horizons** |
| **COVID-onset test (Mar-Jun 2020)** | **2 / 24 horizons** |
| Full test (blend of the two) | 4 / 24 horizons |

**The h=5-20 loss reported previously is almost entirely a property of the blended full-test metric, not of the direct architecture itself.** On validation and on the pre-COVID slice of the actual test set, direct XGBoost wins every single horizon, often by wide margins (see the val table in [direct_hourly_model_comparison.md](direct_hourly_model_comparison.md)). The apparent "h=5-20 weakness" only appears once COVID-onset rows are blended in.

### The mechanism: a bias sign-flip, not added noise

Decomposing test-period errors into bias (mean signed error) and residual spread, per horizon:

| Horizon | Pre-COVID direct bias (MW) | COVID-onset direct bias (MW) | Prev-day bias (both periods) |
|---|---|---|---|
| 5 | −35.2 | **+25.5** | ≈ −2 / +1 |
| 10 | −43.2 | **+29.7** | ≈ −2 / +1 |
| 15 | −47.3 | **+56.6** | ≈ −2 / +1 |
| 20 | −50.8 | **+51.4** | ≈ −2 / +1 |

**Direct model bias flips sign between periods** (average −45.5 MW pre-COVID → +40.7 MW COVID-onset, h=5-20). **The previous-day baseline stays near-zero bias in both periods** — it has no learned "typical level" to be systematically wrong about; it simply tracks whatever demand did yesterday.

**Mechanistically:** pre-COVID, the direct model's mid-horizon predictions lean heavily on target-time calendar features (established in [direct_hourly_model_comparison.md](direct_hourly_model_comparison.md) §7 — `target_hour_of_day`, `target_hour_cos` dominate at h=6/h=12). This produces a persistent, modest under-prediction (real demand runs slightly above the calendar-learned "typical" level, consistent with the ordinary year-over-year growth trend documented in the dataset audit) — but the bias is small and consistent enough that its low error *variance* still beats the previous-day baseline's noisier, larger-magnitude but unbiased errors. Once COVID-onset suppresses actual demand well below the calendar-learned "typical" level, the SAME systematic reliance on calendar features now produces a much larger over-prediction — the bias grows and flips sign, and now compounds with (rather than partially offsetting) the model's baseline error, driving MAE up well past the previous-day baseline's.

**COVID-onset bias-to-MAE ratio (h=5-20 average): 0.40** — meaning systematic bias, not noise, accounts for roughly 40% of the total error magnitude during the shift. See [bias_decomposition_pre_vs_covid.png](figures/regime_aware/bias_decomposition_pre_vs_covid.png).

**Conclusion: the h=5-20 loss is a regime-shift-driven bias problem, concentrated in COVID-onset, not an inherent weakness of the direct multi-horizon architecture at those horizons.**

---

## Part 2 — Testing a principled per-horizon hybrid

Two new, leakage-safe strategies were tested, on top of the existing (unmodified) regime detector and previous-day fallback:

### D. Per-horizon method selector (frozen from validation only)

For each horizon h, freeze whichever of {Direct, Previous-day} has the lower MAE **on validation data (2019) only** — never touching test. Result: **Direct is selected for all 24/24 horizons** (`ml/reports/per_horizon_method_selection.json`). This is an important, honest **null result**: it directly confirms Part 1's finding — there is no horizon where the direct model is genuinely weaker in-distribution, so a naive per-horizon static selector adds nothing beyond what's already known. Method D's full-test performance is mathematically identical to plain Direct (77.72 MAE both).

### E. Bias-corrected direct (adaptive, causal, leakage-safe)

Targets the diagnosed root cause directly: at each origin `t` and horizon `h`, subtract a **causal 168h (7-day) trailing estimate of the direct model's own recent bias**, computed only from forecasts whose **target time has already occurred at or before `t`** (already-realized, known outcomes — never a forecast whose target is still in the future relative to `t`).

**Leakage-safety construction (the critical detail):** a naive version computing "trailing bias ending at target time τ" and attaching it to the forecast made for τ would leak up to `h` hours of post-origin information (since that forecast's own origin is `τ−h`, before τ). The implementation instead computes the trailing rolling bias indexed by *target* time (since that's when each past error becomes known), then **shifts it back by `h` hours** so the value attached to any row reflects only errors already known as of that row's own *origin* time. Verified directly: for a sample of 100 corrected rows, every error contributing to that row's bias estimate has `target_datetime <= origin_datetime` of the row being corrected (test in the script; all passed). Bias correction is available for 95.8% of rows (the remainder — the first 168h of the test period — fall back to the raw uncorrected prediction, since no trailing window exists yet).

**Result:** substantial improvement pre-COVID (39.71 vs. 51.26 MAE, direct model, averaged across horizons — a ~22% reduction) and a modest improvement during COVID-onset (89.29 vs. 91.28) — smaller there because the 168h smoothing window lags a sudden shift; the correction only builds up over the following week, consistent with the regime detector's own ~5.5-week detection lag documented in [regime_aware_forecast_report.md](regime_aware_forecast_report.md).

### F. Full principled hybrid (D + E + regime detector, unmodified)

NORMAL-regime origins: bias-corrected direct prediction (per-horizon selection already resolves to "direct" everywhere, so this reduces to Method E in NORMAL mode). SHIFT-regime origins: previous-day fallback (unchanged from the prior stage).

---

## Results — all six methods, full 2020 test period

| Method | Mean MAE (all horizons) | Horizons beating previous-day baseline |
|---|---|---|
| A. Direct XGBoost | 77.72 | 4/24 |
| B. Previous-day baseline | 66.15 | — |
| C. Regime-hybrid (prior stage) | 68.74 | 8/24 |
| D. Per-horizon selector | 77.72 (= A, null result) | 4/24 |
| E. Bias-corrected direct | 72.49 | 6/24 |
| **F. Full principled hybrid** | **63.15 (best of all six)** | **11/24** |

**Method F beats the previous-day baseline's own mean MAE (63.15 vs. 66.15) — the first method in this entire investigation to do so on the blended full test set.** Per-horizon, F beats previous-day at **h = {1, 2, 3, 4, 5, 19, 20, 21, 22, 23, 24}** — up from C's {1,2,3,4,21,22,23,24}, adding h=5, 19, 20 as new wins via the bias correction. F still loses at h=6-18, but by a much narrower margin than plain Direct — e.g. at h=12: F=70.9 vs. baseline=66.1 (a 4.8 MW gap) vs. Direct's 91.1 vs. 66.1 (a 25.0 MW gap), roughly an **80% reduction in the loss margin** at the worst-affected horizons.

**By period:**

| Period | A. Direct | B. Prevday | C. Regime-hybrid | E. Bias-corrected | F. Full principled |
|---|---|---|---|---|---|
| Pre-COVID | 51.26 | 85.17 | 51.26 | **39.71** | **39.71** |
| COVID-onset | 91.28 | **56.40** | 77.70 | 89.29 | 75.17 |
| Full test | 77.72 | 66.15 | 68.74 | 72.49 | **63.15** |

Bias correction alone (E) delivers the biggest single win **pre-COVID** (22% better than plain Direct — a genuine accuracy improvement in normal conditions, independent of the regime question). The regime detector remains essential for COVID-onset (F's 75.17 there beats E-alone's 89.29 by using the fallback for the 28.4% of hours it flags), though none of the tested methods yet beat the previous-day baseline's own COVID-onset performance outright.

Plots: [principled_hybrid_mae_by_horizon.png](figures/regime_aware/principled_hybrid_mae_by_horizon.png), [principled_hybrid_pre_vs_covid.png](figures/regime_aware/principled_hybrid_pre_vs_covid.png), [adaptive_bias_over_time_h12.png](figures/regime_aware/adaptive_bias_over_time_h12.png) (shows the bias estimate tracking the sign flip around COVID onset, with the expected ~1-week lag).

---

## Leakage safety — summary of what was verified

- Method D's threshold/selection uses validation data only (never test), matching the same discipline as the regime detector's threshold freezing.
- Method E's bias correction is indexed and shifted so that every correction uses only forecast errors whose **target time is at or before the origin time of the forecast being corrected** — verified programmatically on a sample of 100 rows, and by construction (the shift-by-`h` step) for all rows.
- `origin_datetime < target_datetime` holds for all 101,976 evaluation rows (unchanged check from the prior stage).
- No thresholds or weights in this investigation were selected by looking at test-period MAE — Method D's selection and Method E's window (168h, matching the regime detector's own window, chosen a priori for consistency) were both fixed before evaluating on test.

---

## Limitations

1. **Bias correction still lags a sudden shift** by roughly the smoothing window's length (~1 week) — it cannot help during the first ~168h after a shift begins, the same fundamental lag the regime detector has.
2. **COVID-onset performance still falls short of the plain previous-day baseline** even under the full principled hybrid (75.17 vs. 56.40) — this investigation narrows the gap substantially but does not close it. The remaining gap is concentrated in the 71.6% of COVID-onset hours the conservative regime detector does not flag as SHIFT, where bias-corrected direct is still weaker than simple previous-day tracking.
3. **Method D's null result is specific to this dataset/period** — a per-horizon selector is not inherently useless in general, but on this data, with only 2015-2019 as "normal" training/validation signal, it had nothing to select against.
4. **This remains an experiment, not a deployed pipeline** — no existing model, detector, or downstream integration was modified.

## Answer to the direct question

**Why does h=5-20 lose to previous-day?** Because the direct model's mid-horizon predictions carry a systematic, calendar-feature-driven bias that is small and beneficial (net-positive vs. baseline) in normal conditions but flips sign and grows large during the COVID-onset regime shift — and the full-test metric blends a period where direct wins everywhere (pre-COVID, validation) with a period where it loses badly (COVID-onset), making the aggregate look like a persistent horizon-specific weakness when it is not.

**Does a principled per-horizon hybrid help?** Yes — the full hybrid (per-horizon selection + causal bias correction + the existing regime detector) achieves the best mean MAE of all six methods tested (63.15, beating even the previous-day baseline's own mean of 66.15) and nearly triples the horizon win count against baseline (4→11 of 24), while every step remains leakage-verified. It does not fully close the COVID-onset gap, which remains the dominant open limitation.
