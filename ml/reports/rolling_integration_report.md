# GridGuard AI — Rolling Historical Integration (FINAL Forecasting Architecture)

**Script:** [ml/src/rolling_integration.py](../src/rolling_integration.py) — fully rewritten for this integration; this is the **only** source file modified for this task.
**Output data:** [ml/data/rolling_feeder_results.csv](../data/rolling_feeder_results.csv) (1,019,760 rows, ~318 MB)
**Tests:** [ml/tests/test_rolling_integration.py](../tests/test_rolling_integration.py) — 13/13 passing
**Raw summary:** [ml/reports/rolling_integration_summary.json](rolling_integration_summary.json)

**Not modified:** any trained model, `build_features.py`, `regime_detector.py`, `robust_hourly_forecast.py`, `stress_engine.py`, `feeder_generator.py`, the Prevention/Action Engine, or any backend/frontend code.

---

## ⚠️ Synthetic data / voltage disclaimer

**All feeder-level output remains SYNTHETIC simulation data** — the underlying Mendeley dataset contains only national aggregate demand; no real Panama feeder measurements exist anywhere in this project (see `feeder_generator.py`'s module docstring). **Voltage (`voltage_pu`) is a simplified engineering approximation** — a linear function of utilization — **not a power-flow simulation and not measured data.** Nothing in this file or report should be presented as real Panama grid telemetry.

---

## 1. Final forecasting architecture

```
Origin t
   |
   v
Regime Detector (existing, unmodified regime_detector.py)
   |
   +-- NORMAL --> Direct XGBoost (existing, unmodified per-horizon models)
   |              + causal 168h bias correction (computed in
   |                rolling_integration.py only; not added to any
   |                existing file)
   |
   +-- SHIFT ---> Same-hour-previous-day fallback
   |
   v
24 genuine hourly forecasts (t+1 .. t+24)
   |
   v
Existing, unmodified synthetic feeder allocation (feeder_generator.py)
   |
   v
Existing, unmodified Grid Stress Engine (stress_engine.py)
   |
   v
ml/data/rolling_feeder_results.csv
```

This replaces the prior version's forecasting call — a single 24h XGBoost point interpolated against a historical diurnal shape (`feeder_generator.build_national_trajectory`) — with the finalized principled hybrid (Method F) established in [principled_hybrid_investigation.md](principled_hybrid_investigation.md): the best full-test mean MAE of every approach tested (63.15 MW), beating both plain Direct XGBoost (77.72) and the previous-day baseline alone (66.15).

**Where the bias-correction logic lives:** per this task's explicit instruction to modify only `rolling_integration.py`, the causal 168h bias-correction computation (previously prototyped in the standalone `principled_hybrid_forecast.py` experiment) was reimplemented directly inside `rolling_integration.py` — `regime_detector.py` and `robust_hourly_forecast.py` remain byte-for-byte unchanged. The bias-correction construction (trailing rolling mean of past errors, indexed by target time, shifted back by `h` hours so a forecast is only corrected using errors known as of its own origin) is identical to the leakage-verified version from the prior investigation.

**Warm-up extension:** unlike the standalone experiment (where the first 168h of the test period had no bias estimate available), this integration computes national forecasts starting from `2019-12-17` — 199h before the test period begins — so the bias window is already populated for every one of the 4,249 test origins, with no fallback-to-raw-prediction gap.

---

## 2. Number of origins and forecast rows

| | Value |
|---|---|
| Forecast origins | **4,249** (2020-01-01 00:00 → 2020-06-26 00:00, unchanged boundaries) |
| Horizons per origin | 24 |
| Feeders per origin | 10 |
| **Total forecast rows** | **1,019,760** (4,249 × 24 × 10) |

---

## 3. Regime distribution

| Status | Origins | % |
|---|---|---|
| NORMAL | 3,451 | 81.2% |
| SHIFT | 798 | 18.8% |

Matches the regime detector's behavior established and validated in [regime_aware_forecast_report.md](regime_aware_forecast_report.md) exactly (same frozen, train/val-derived threshold, same detector, unmodified).

## 4. Forecast method distribution

| Method | Origins |
|---|---|
| BIAS_CORRECTED_DIRECT_XGBOOST | 3,451 |
| PREVIOUS_DAY_FALLBACK | 798 |

One-to-one with the regime distribution, as designed (a single per-origin decision applied uniformly across all 24 horizons for that origin, matching `robust_hourly_forecast.py`'s existing design philosophy from the prior stage).

---

## 5. Feeder-level stress distribution

**Overall risk-level distribution (per origin-feeder pair, n=42,490):**

| Level | % |
|---|---|
| LOW | 59.32% |
| MODERATE | 40.58% |
| HIGH | 0.106% |
| CRITICAL | 0.00% |

**Max stress score:** 64.60 (feeder F10, 2020-01-20 20:00) — HIGH band, similar in magnitude and location to the prior interpolation-based pipeline's max of 62.89, now derived from genuine hourly forecasts rather than interpolation.
**Max utilization:** 0.8950 (89.5%).

**Per-feeder summary:**

| Feeder | Type | Mean stress | Median | Max stress | Mean util. | Max util. | Records ≥ MODERATE |
|---|---|---|---|---|---|---|---|
| F01 | RESIDENTIAL | 24.0 | 22.1 | 54.9 | 0.318 | 0.767 | 915 |
| F02 | RESIDENTIAL | 25.7 | 23.7 | 58.9 | 0.341 | 0.822 | 1,084 |
| F03 | COMMERCIAL | 20.5 | 13.9 | 58.2 | 0.266 | 0.801 | 1,171 |
| F04 | COMMERCIAL | 19.8 | 13.4 | 56.1 | 0.257 | 0.772 | 1,129 |
| F05 | INDUSTRIAL | 36.5 | 35.4 | 59.4 | 0.480 | 0.831 | 3,151 |
| F06 | INDUSTRIAL | 38.5 | 37.3 | **62.7** | 0.507 | 0.878 | **3,571** |
| F07 | MIXED | 27.4 | 28.9 | 52.8 | 0.360 | 0.735 | 2,003 |
| F08 | MIXED | 25.6 | 27.1 | 49.5 | 0.337 | 0.689 | 1,760 |
| F09 | EV_HEAVY | 27.5 | 24.0 | 62.4 | 0.363 | 0.865 | 1,202 |
| F10 | EV_HEAVY | 28.4 | 24.8 | **64.6** | 0.376 | **0.895** | 1,300 |

Pattern consistent with all prior stages: industrial feeders (F05, F06) run persistently higher stress due to their near-flat, high-utilization load shape combined with tighter capacity margins; EV-heavy F10 (tightest margin, 1.05) shows the single highest peak stress in the dataset.

## 6. Overloads / time-to-overload

**Zero predicted overload events** across all 42,490 origin-feeder pairs — consistent with every prior stage of this project. Feeder capacities are sized from each feeder's own historical peak allocation with margin, so utilization within this same historical-adjacent period structurally tends to stay below 100%. The controlled scenario validation in [stress_scenario_analysis.md](stress_scenario_analysis.md) previously and separately confirmed overload detection works correctly when it does occur — that mechanism was not re-tested here since no overload condition is present in this natural data.

---

## 7. Validation results — all 16 checks passed

| Check | Result |
|---|---|
| Exactly 24 horizons per (origin, feeder) | **True** |
| `forecast_datetime == origin_datetime + forecast_horizon` for all rows | **True** |
| No duplicate (origin, horizon, feeder) rows | **True** |
| No NaN/inf in core numeric columns | **True** |
| `stress_score` always in [0, 100] | **True** |
| `utilization` / `forecast_utilization` ≥ 0 | **True** |
| `forecast_mw` ≥ 0 | **True** |
| `risk_level` agrees with `stress_engine.classify_stress()` recomputed on every row | **True** |
| `forecast_method` only takes the two valid values | **True** |
| NORMAL origins use `BIAS_CORRECTED_DIRECT_XGBOOST` exclusively | **True** |
| SHIFT origins use `PREVIOUS_DAY_FALLBACK` exclusively | **True** |
| Exactly 240 rows per origin (24 horizons × 10 feeders) | **True** |
| 2020 test-period boundaries preserved exactly | **True** |
| Origins processed in chronological order | **True** |
| Fallback source timestamps never in the future | **True** |
| Bias correction uses only already-resolved (past) forecast errors | **True** |

**Test suite:** 13/13 tests passed in `ml/tests/test_rolling_integration.py`, covering the same checks against the real production functions on representative origins (both a known NORMAL and a known SHIFT origin), plus schema validation of the actual output CSV.

---

## 8. Leakage checks

- **Regime decision causality:** re-verified end-to-end (`test_regime_decision_causal`) — truncating the raw data to just after a given origin produces an identical regime classification and score, confirming no forward-looking dependency.
- **Bias correction causality:** for a 300-row sample, every forecast error contributing to a correction has `target_datetime <= origin_datetime` of the row being corrected — i.e., only outcomes already known at the time that forecast was made were used, verified both inline (assertion in `rolling_integration.py`) and independently in the test suite.
- **Fallback causality:** every `previous_day` source timestamp (`origin + h - 24` for h=1..24) is `<= origin`, verified for all 1,019,760 rows via a vectorized assertion.
- **Feature/model integrity:** all 24 direct models' `feature_names` were confirmed to match `direct_hourly_metadata.json` exactly before any prediction was made.

No existing model, threshold, or pipeline file was altered to produce these results.

---

## 9. Known limitations

1. **Zero overload events in this natural period** — as in every prior stage, this is a property of how feeder capacities are sized relative to this historical-adjacent demand window, not a gap in the pipeline's ability to detect overload (separately validated via controlled scenarios).
2. **The regime detector still only catches 18.8% of the full test period as SHIFT**, concentrated in the more severe stretch of COVID-onset (documented in [regime_aware_forecast_report.md](regime_aware_forecast_report.md)) — the bias correction (Method E component) partially compensates for the remaining 71.6% of COVID-onset hours that stay classified NORMAL, but per [principled_hybrid_investigation.md](principled_hybrid_investigation.md), this combination still does not fully match the previous-day baseline's own COVID-onset accuracy.
3. **Output file size** (~318 MB for 1,019,760 rows) is substantially larger than the prior version's 42,490-row file (~9 MB) — a direct, expected consequence of storing genuine per-horizon forecasts (24×) rather than a single 24h endpoint per origin-feeder pair.
4. **Voltage remains a simplified linear approximation**, not a power-flow simulation — restated per this task's explicit requirement.
5. **All feeder-level data remains synthetic** — restated per this task's explicit requirement; see the disclaimer at the top of this document.
6. This stage integrates the finalized forecasting architecture only — the Prevention/Action Engine, backend, frontend, and Gemini integration remain untouched, per this task's stop condition.

---

## Files changed for this integration

- **Modified:** [ml/src/rolling_integration.py](../src/rolling_integration.py) (only file changed)
- **Created:** [ml/tests/test_rolling_integration.py](../tests/test_rolling_integration.py)
- **Updated:** [ml/reports/rolling_integration_report.md](rolling_integration_report.md) (this document), [ml/reports/rolling_integration_summary.json](rolling_integration_summary.json), [ml/data/rolling_feeder_results.csv](../data/rolling_feeder_results.csv), plots under `ml/reports/figures/rolling_integration/`
