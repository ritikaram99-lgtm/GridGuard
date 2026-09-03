# GridGuard AI — Grid Stress Engine Sanity Analysis

**Script:** [ml/src/stress_engine_sanity_analysis.py](../src/stress_engine_sanity_analysis.py)
**Raw output:** [ml/reports/stress_engine_sanity_raw.json](stress_engine_sanity_raw.json)
**Raw rolled data:** `ml/data/stress_sanity_rolling_results.csv` (42,490 rows)

**This is a validation/sanity analysis only.** `feeder_generator.py`, `stress_engine.py`, the XGBoost model, and the feature pipeline were **not modified** — only their existing, unmodified functions were imported and called across a historical rolling window. **This is not scientific calibration.** There is no real feeder outage/overload label data anywhere in this project to calibrate weights or thresholds against — every conclusion below is about whether the engine behaves *internally consistently and sensibly*, not whether it predicts real-world events.

---

## Dataset / time period used

- **Period:** 2020-01-01 00:00:00 → 2020-06-26 00:00:00 — the existing chronological **test split** (`ml/data/processed/test.csv`), chosen because it's the one period the saved XGBoost model was never trained or tuned on, so its forecasts here are genuine out-of-sample predictions, not memorized fits.
- **4,249 forecast origins** × **10 feeders** = **42,490 feeder-time observations**.
- National current values and 24h-ahead forecasts come from the real, unmodified saved model (`ml/models/demand_xgboost.pkl`). Feeder allocation, capacities, voltage, and trajectories come from the real, unmodified `feeder_generator.py` functions, using the same construction as `run_example()` (deterministic/no-noise allocation for forward trajectories, noisy historical allocation only for capacity sizing).
- Confirmed: **zero NaN/inf values** across all 42,490 rolled observations.

Note on interpretation: because each feeder's `capacity_mw` is itself derived from *this same historical period's* peak synthetic load (times a margin — see [feeder_simulation_report.md](feeder_simulation_report.md)), utilization in this specific rolled window is, by construction, unlikely to exceed 100%. This matters for Sections 5 and 6 below.

---

## 1. Distribution of stress scores

**Overall (all 10 feeders, all 4,249 origins, n=42,490):**

| Stat | Value |
|---|---|
| Mean | 27.56 |
| Median | 26.83 |
| Std | 12.55 |
| Min | 3.40 |
| Max | 62.89 |

**Overall risk level distribution:**

| Level | % of observations |
|---|---|
| LOW | 58.59% |
| MODERATE | 41.37% |
| HIGH | 0.04% |
| CRITICAL | 0.00% |

**Per feeder:**

| Feeder | Type | Mean | Median | Std | Min | Max |
|---|---|---|---|---|---|---|
| F01 | RESIDENTIAL | 24.10 | 22.39 | 9.96 | 10.08 | 53.82 |
| F02 | RESIDENTIAL | 25.82 | 24.00 | 10.68 | 10.81 | 57.67 |
| F03 | COMMERCIAL | 20.72 | 13.87 | 14.95 | 3.53 | 57.03 |
| F04 | COMMERCIAL | 19.96 | 13.36 | 14.40 | 3.40 | 54.94 |
| F05 | INDUSTRIAL | 36.70 | 35.92 | 7.99 | 21.70 | 58.15 |
| F06 | INDUSTRIAL | 38.75 | 37.93 | 8.44 | 22.91 | 61.40 |
| F07 | MIXED | 27.55 | 29.21 | 11.83 | 8.58 | 51.71 |
| F08 | MIXED | 25.82 | 27.38 | 11.09 | 8.04 | 48.46 |
| F09 | EV_HEAVY | 27.62 | 24.02 | 9.85 | 13.11 | 60.79 |
| F10 | EV_HEAVY | 28.58 | 24.85 | 10.19 | 13.57 | 62.89 |

**Per-feeder risk distribution (%):**

| Feeder | LOW | MODERATE | HIGH | CRITICAL |
|---|---|---|---|---|
| F01 | 77.83 | 22.17 | 0.00 | 0.0 |
| F02 | 74.82 | 25.18 | 0.00 | 0.0 |
| F03 | 71.29 | 28.71 | 0.00 | 0.0 |
| F04 | 72.37 | 27.63 | 0.00 | 0.0 |
| F05 | 25.54 | 74.46 | 0.00 | 0.0 |
| F06 | 15.06 | 84.70 | 0.24 | 0.0 |
| F07 | 51.66 | 48.34 | 0.00 | 0.0 |
| F08 | 56.18 | 43.82 | 0.00 | 0.0 |
| F09 | 71.33 | 28.64 | 0.02 | 0.0 |
| F10 | 69.80 | 30.05 | 0.14 | 0.0 |

Industrial feeders (F05, F06) run consistently higher stress (mean ~37, mostly MODERATE) — expected, since `INDUSTRIAL`'s near-flat, high-utilization load shape combined with tighter capacity margins (1.10–1.15) keeps them persistently closer to capacity than e.g. commercial feeders, which spend most hours at low utilization (F03/F04 medians of 13–14, driven low by the many off-peak hours in their sharply peaked daytime shape). **No feeder ever reached CRITICAL in this 6-month period, and only F06/F09/F10 briefly touched HIGH (0.02–0.24% of the time).**

---

## 2. Utilization vs. stress relationship

| Relationship | Pearson r | Spearman ρ |
|---|---|---|
| Current utilization vs. stress score | **0.9707** | 0.9711 |
| Forecast utilization vs. stress score | **0.9751** | 0.9774 |

Both relationships are very strongly positive, as intended — stress increases essentially monotonically with both current and forecast utilization across the full rolled dataset (both p-values effectively 0). Plots: [current_utilization_vs_stress.png](figures/stress_sanity/current_utilization_vs_stress.png), [forecast_utilization_vs_stress.png](figures/stress_sanity/forecast_utilization_vs_stress.png).

---

## 3. Controlled monotonicity / property checks

Five controlled sweeps, each holding all other inputs fixed and varying one input across a wide range, checking that the stress score never decreases in the "worsening" direction. **All five passed, with zero violations:**

| Property | Setup | Result |
|---|---|---|
| Increasing current utilization | current_load 0→150 MW, forecast=60, capacity=100, voltage=0.98 fixed | **PASS** (min step Δ = 0.000000) |
| Increasing forecast utilization | forecast_load 0→150 MW, current=40, capacity=100, voltage=0.98 fixed | **PASS** (min step Δ = 0.000000) |
| Increasing positive trajectory slope | forecast_load 20→180 MW, current=20 fixed, capacity=100 | **PASS** (min step Δ = 0.000000) |
| Worsening voltage | voltage_pu 1.05→0.80, current=forecast=60, capacity=100 fixed | **PASS** (min step Δ = 0.000000) |
| Reducing headroom (via shrinking capacity) | capacity 200→51 MW, load=50 fixed | **PASS** (min step Δ = 0.070459) |

**All monotonicity properties passed.** No formula bug was found, so — per the task instructions — **nothing in `stress_engine.py` was changed.**

---

## 4. Component contribution analysis

### The headroom = current_utilization identity

**Confirmed exactly, both empirically and algebraically:** `comp_headroom == comp_current_utilization` for **all 42,490 rolled observations** (max absolute difference: 1.39e-16, i.e. floating-point noise only). An independent algebraic sweep over current_load/capacity combinations confirms the same identity (max diff 1.11e-16).

This is a direct mathematical consequence of the current definitions:
```
current_utilization_component = clip(current_load / capacity, 0, 1)
headroom_component            = 1 - clip((capacity - current_load) / capacity, 0, 1)
                               = clip(current_load / capacity, 0, 1)   [same expression]
```

**This means current utilization effectively contributes to the score through two separate weighted terms** — `current_utilization` (weight 0.35) and `headroom` (weight 0.10) — for a **combined effective weight of 0.45 out of 1.00 (45%)**, more than any other single factor by a wide margin (next highest is `forecast_utilization` at 0.30). This is stated here as a documented observation, **not corrected** — the task instructions are explicit that the formula should not be modified unless an actual coding bug is found, and this is a design/weighting redundancy, not a computational error (both components are individually well-defined and correct given their formulas; they simply reduce to the same value).

### Representative examples (nearest-to-median real observation in each observed band)

| Level | Feeder | Score | current_util | forecast_util | voltage_pu | current_util contribution | forecast_util contribution | slope contribution | voltage contribution | headroom contribution |
|---|---|---|---|---|---|---|---|---|---|---|
| LOW | F08 (MIXED), 2020-02-28 06:00 | 20.06 | 0.301 | 0.216 | 1.020 | 10.55 pts (52.6%) | 6.49 pts (32.4%) | 0.00 (0%) | 0.00 (0%) | 3.01 pts (15.0%) |
| MODERATE | F05 (INDUSTRIAL), 2020-03-05 07:00 | 39.09 | 0.529 | 0.510 | 1.020 | 18.50 pts (47.3%) | 15.30 pts (39.1%) | 0.00 (0%) | 0.00 (0%) | 5.29 pts (13.5%) |
| HIGH | F09 (EV_HEAVY), 2020-01-20 20:00 | 60.79 | 0.820 | 0.796 | 1.020 | 28.70 pts (47.2%) | 23.89 pts (39.3%) | 0.00 (0%) | 0.00 (0%) | 8.20 pts (13.5%) |
| CRITICAL | — | — | — | — | — | — | — | — | — | *no CRITICAL observation occurred in this period (see Section 5)* |

**Across all three real examples above (and consistent with the aggregate component means below), `current_utilization` + `headroom` together always account for roughly 60–68% of the score, `forecast_utilization` accounts for roughly 32–39%, and `trajectory_slope`/`voltage_stress` contribute 0%.** This is not specific to these three examples — see the aggregate component statistics below.

### Aggregate component statistics (all 42,490 observations)

| Component | Mean (raw, 0-1) | Std | Max | Rows > 0 |
|---|---|---|---|---|
| `current_utilization` | 0.360 | 0.169 | 0.895 | all |
| `forecast_utilization` | 0.366 | 0.171 | 0.824 | all |
| `trajectory_slope` | 0.025 | 0.055 | 0.431 | 19,778 / 42,490 (46.6%) |
| `voltage_stress` | **0.000** | 0.000 | **0.000** | **0 / 42,490 (0%)** |
| `headroom` | 0.360 | 0.169 | 0.895 | all (identical to current_utilization) |

**`voltage_stress` was exactly zero in every single one of the 42,490 rolled observations.** This is because the voltage model only starts sagging above 50% utilization (drop_coefficient 0.10/unit) and only drops below the 0.95 pu stress threshold once utilization exceeds ~120% — but observed utilization in this period never exceeded 89.5% (see Section 5), so voltage never sagged past 0.9805 pu, well above the 0.95 pu threshold where `voltage_stress` starts contributing. **In this historical period, the Grid Stress Engine's score is effectively driven entirely by the three utilization-derived terms (`current_utilization`, `forecast_utilization`, `headroom` — the last being identical to the first) plus an occasional small `trajectory_slope` contribution; `voltage_stress` never activates.**

---

## 5. Event usefulness

Overall distribution: **58.6% LOW, 41.4% MODERATE, 0.04% HIGH, 0.00% CRITICAL.**

This is **closer to "mostly LOW/MODERATE" than to "a reasonable mixture across all four bands."** The engine essentially never produces HIGH and never produces CRITICAL in this 6-month rolled historical window — max observed utilization was 89.5% (current) / 82.4% (forecast), and the maximum stress score observed anywhere in the entire period was **62.89** (feeder F10, barely into the HIGH band, which starts at 61).

**Important caveat on interpreting this as "the formula is too conservative":** this is very plausibly a consequence of how feeder capacities are sized (`capacity_mw = margin × historical_peak_load`, margins 1.05–1.30 — see [feeder_simulation_report.md](feeder_simulation_report.md)), not necessarily a flaw in the stress formula itself. Because capacities are *derived from* the very same historical demand history being scored, utilization in that same historical window can, by construction, only approach but rarely exceed 100% (exactly 1/margin at the historical peak instant, i.e. ~95.2% for F10's 1.05 margin) — the historical rolled data was never going to naturally generate many CRITICAL or overload events, regardless of how the score is weighted. **This is a scenario-coverage limitation of the sanity-check setup, not conclusive evidence that the score formula itself needs correction** — see the recommendation in Section 8.

Per the task instructions, **thresholds/weights were not adjusted to make this distribution "look better."**

---

## 6. Time-to-overload relationship

**Zero overload events (`overload_predicted=True`) occurred anywhere in the 42,490 rolled observations.** This directly follows from Section 5: since utilization never exceeded ~89.5% and forecast utilization never exceeded ~82.4%, no feeder's forecast trajectory ever crossed its own capacity in this period.

**Consequently, the requested correlation between `time_to_overload_hours` and `stress_score` could not be computed from the historical rolled data — there is no data to compute it from.** This is reported honestly rather than substituting a fabricated or cherry-picked result. The `time_to_overload_vs_stress.png` plot was not generated for the same reason (no rows to plot).

The mechanism itself (interpolated crossing detection) was separately validated with controlled synthetic trajectories in [feeder_simulation_report.md](feeder_simulation_report.md) Section 6 and in the unit test suite (`test_overload_detected_when_trajectory_crosses_capacity`, `test_overload_already_at_start`, etc.) — those confirm the *mechanism* works correctly. What this sanity analysis adds is the observation that **the historical rolling period used here provides zero real-world-shaped examples to check the stress-score/time-to-overload relationship against**, which is itself a useful and honest finding (see Section 8).

---

## 7. Visualizations

Saved under `ml/reports/figures/stress_sanity/`:

- [stress_score_distribution.png](figures/stress_sanity/stress_score_distribution.png) — histogram of all 42,490 scores, with LOW/MODERATE/HIGH/CRITICAL boundaries marked
- [stress_by_feeder.png](figures/stress_sanity/stress_by_feeder.png) — boxplot of stress score by feeder
- [current_utilization_vs_stress.png](figures/stress_sanity/current_utilization_vs_stress.png)
- [forecast_utilization_vs_stress.png](figures/stress_sanity/forecast_utilization_vs_stress.png)
- [example_stress_trajectory.png](figures/stress_sanity/example_stress_trajectory.png) — the single highest-stress observation found (feeder F10, 2020-01-20 20:00, score 62.89), trajectory vs. capacity line

`time_to_overload_vs_stress.png` was **not generated** — no overload-predicted rows existed to plot (Section 6).

---

## 8. Is the current formula reasonable as an initial engineering heuristic?

**Yes, with one caveat, based strictly on what was tested:**

- It is **internally consistent**: all five controlled monotonicity properties passed with zero violations — increasing utilization, positive slope, worsening voltage, and shrinking headroom never decrease the score.
- It **correlates strongly and sensibly** with utilization (r ≈ 0.97–0.98 for both current and forecast utilization) — the score is not arbitrary or noisy relative to the inputs it's supposed to summarize.
- It **produces zero NaN/inf/out-of-range values** across 42,490 real rolled observations plus all controlled edge cases (zero capacity, extreme values).

**The caveat:** the current weighting makes the score **effectively a triple-counted-utilization score** in the regime this historical period actually explores — `current_utilization` and `headroom` are mathematically identical (combined 45% weight), `forecast_utilization` adds another 30–39%, and `voltage_stress` contributed **exactly 0%** across the entire 6-month period (never once activated), leaving `trajectory_slope` (weight 0.15, non-zero in 46.6% of rows but small in magnitude) as the only source of score variation genuinely independent of raw utilization level. This isn't necessarily wrong for a first-pass heuristic — but it does mean four of the five documented "components" mostly collapse into "how utilized is this feeder," and the engine's behavior in the HIGH/CRITICAL range and around actual overload events is **untested by this analysis**, because no such events occurred in the available historical window.

## Limitations

- No real feeder outage/overload data exists to check whether LOW/MODERATE/HIGH/CRITICAL actually correspond to meaningfully different real-world risk — this analysis checks internal consistency, not predictive validity.
- The rolled period (2020 test set) never naturally produces HIGH, CRITICAL, or overload conditions, because feeder capacities are sized from that same period's historical peaks with margin — this is a property of how the scenario was constructed, not a property of the stress formula, and it means Sections 5 and 6 could not be evaluated under real "stress" conditions.
- `voltage_stress` was not exercised at all in this period; its behavior at high utilization (>120%) is validated only by the controlled sweep in Section 3, not by real rolled data here.
- Component contribution examples for CRITICAL could not be drawn from real data (none occurred); only LOW/MODERATE/HIGH examples are real observations.

---

## Recommendation

**C) Investigate a specific issue further before proceeding to rolling integration** — specifically: the engine's mathematical behavior is sound (monotonicity holds, correlations are sensible, no NaN/inf), so this is **not** a case for a targeted formula correction (B). But this sanity analysis, run only against the natural historical distribution, was **structurally unable to exercise the HIGH/CRITICAL and overload-detection paths** (0.04% HIGH, 0% CRITICAL, 0% overload predicted across 42,490 observations) — precisely the states the rolling integration and any future prevention layer most need to depend on. Before building the rolling integration layer, it would be worth re-running this same sanity analysis (same unmodified `feeder_generator.py`/`stress_engine.py`) against a small set of **deliberately constructed stress scenarios** (e.g., an artificially elevated demand multiplier, or a tighter-margin feeder pushed with above-historical-peak input) so that the CRITICAL band, voltage-stress activation, and the time-to-overload/stress relationship can actually be observed and sanity-checked at least once before the rolling integration layer is built on top of an engine whose upper-range behavior remains unverified against any concrete example.
