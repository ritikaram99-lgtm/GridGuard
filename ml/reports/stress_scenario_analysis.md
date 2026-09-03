# GridGuard AI — Controlled Stress-Engine Scenario Validation

**Script:** [ml/src/stress_scenario_analysis.py](../src/stress_scenario_analysis.py)
**Raw output:** [ml/reports/stress_scenario_analysis_raw.json](stress_scenario_analysis_raw.json), `ml/data/stress_scenario_results.csv` (45 rows)

**This is a controlled simulation/validation task only.** `feeder_generator.py` and `stress_engine.py` were **not modified** — every scenario below calls their existing, unmodified functions with deliberately chosen inputs. No formula, weight, or threshold was changed to make any scenario "work."

## ⚠️ Important distinction

**Every scenario in this document is a deliberately constructed simulation input.** None of them are real Panama feeder events, historical overloads, real outage data, or validated real-world risk thresholds. They exist solely to verify that the GridGuard pipeline's *mechanics* — scoring, classification, overload detection, voltage-model activation — behave correctly when dangerous conditions occur, since [stress_engine_sanity.md](stress_engine_sanity.md) found the natural 2020 historical window never produced such conditions (max utilization observed there was 89.5%, zero CRITICAL, zero overload events).

---

## Baseline

All scenarios build on one real feeder state from the existing, unmodified pipeline: `feeder_generator.run_example()`'s default output, origin **2020-06-26 00:00:00** (the most recent available row). Baseline utilizations ranged 11.5%–45.5% across the 10 feeders (all LOW/borderline-MODERATE), confirming this is a genuinely "normal" starting point, not cherry-picked to be already stressed.

**Representative feeder for scenarios E–H: F10** (Tocumen EV Depot) — chosen because it has the tightest real `capacity_margin` (1.05) among the 10 feeders, making it the natural candidate to approach its own capacity fastest under demand elevation.

---

## 1–2. Scenario definitions, purpose, and results

### A–D: Demand elevation (all 10 feeders)

**Why:** to check the basic property "more demand → more stress" holds broadly, not just for one feeder, and to see whether ordinary-looking demand growth alone can push any feeder past LOW/MODERATE.

**Input modification:** baseline `current_load_mw` and `forecast_load_mw` multiplied by 1.00 / 1.10 / 1.20 / 1.30; capacity held fixed at each feeder's real (unmodified) `capacity_mw`.

| Scenario | Multiplier | Result |
|---|---|---|
| A_NORMAL | 1.00 | All 10 feeders LOW (F05/F06 borderline, 29.9/31.6) |
| B_ELEVATED_+10% | 1.10 | F05, F06 → MODERATE; rest still LOW |
| C_ELEVATED_+20% | 1.20 | F05, F06, F09, F10 → MODERATE; rest LOW |
| D_ELEVATED_+30% | 1.30 | Same 4 feeders MODERATE (higher within band); rest LOW |

**Increasing demand increased (never decreased) stress score for every one of the 10 feeders across A→D — verified directly, zero violations.** However, **a 30% demand increase alone was not enough to push any feeder out of MODERATE into HIGH** — even F06 (tightest-margin industrial feeder among A–D) only reached 41.1 at +30%. This is a real, useful finding: ordinary demand growth in this margin regime (1.05–1.30x historical peak) moves the score meaningfully but gradually; reaching HIGH/CRITICAL via demand growth alone would require elevation beyond +30%, or a tighter capacity margin (see Scenario E).

### E: TIGHT_CAPACITY (F10)

**Why:** to isolate the effect of a tighter capacity assumption from demand growth — "what if this feeder simply has less headroom," independent of any demand change.

**Input modification:** F10's `current_load_mw`/`forecast_load_mw` held at baseline; `capacity_mw` deliberately overridden from its real 5.76 MW to **1.05× the current load (2.34 MW)** — i.e., an artificially tight capacity assumption applied only for this scenario, not a change to `feeder_generator.py`'s own capacity logic.

**Result:** utilization jumps to 95.2%, score **66.13 → HIGH**. Confirms the engine responds correctly to capacity assumptions, not just raw load — the same physical load that was LOW/borderline against the real capacity becomes HIGH against a tighter one.

### F: OVERLOAD (F10)

**Why:** to explicitly exercise the overload-detection and time-to-overload pathway, which the sanity analysis found never activated naturally.

**Input modification:** an explicit, hand-constructed linear trajectory from 0.60×capacity (3.45 MW) at h=0 to 1.40×capacity (8.06 MW) at h=24, capacity fixed at F10's real 5.76 MW.

**Result:** `overload_predicted = True`, score **69.00 → HIGH**. Crossing time comparison:

| | Value |
|---|---|
| Expected crossing (algebraic, exact since trajectory is linear) | h = 12.0000 |
| Function-reported `time_to_overload_hours` | h = 12.0000 |
| Match within 0.01h | **True** |

The interpolation logic is exactly correct on this controlled, exactly-solvable case.

### G: HIGH_UTILIZATION (F10)

**Why:** to check the score/classification right at the edge of capacity, without actually crossing it.

**Input modification:** current = 0.97×capacity, forecast = 0.99×capacity (both near but below capacity).

**Result:** score **73.65 → HIGH**, `overload_predicted = False` (correctly — the trajectory never reaches 100%). Confirms HIGH can be reached through sustained near-capacity utilization alone, without a predicted crossing.

### H: VOLTAGE_STRESS (F10, two sub-cases)

**Why:** the sanity analysis found `voltage_stress` contributed exactly 0 in all 42,490 historical observations because utilization never exceeded ~89.5%, while the voltage model only starts sagging past its 0.95pu threshold above ~120% utilization. This scenario deliberately pushes utilization past that point.

**Input modification:** load held constant at 1.30× capacity (H1) and 1.70× capacity (H2) — deliberately over 100%, solely to exercise the voltage model.

| Sub-scenario | Utilization | Voltage (pu) | voltage_stress component | Score | Risk |
|---|---|---|---|---|---|
| H1 (partial) | 130% | 0.9400 | 0.20 (partial) | 77.00 | HIGH |
| H2 (saturated) | 170% | 0.9000 | 1.00 (saturated) | **85.00** | **CRITICAL** |

**Voltage stress activates exactly where the model's own math says it should** (below 0.95pu), confirmed against the unmodified `voltage_stress_component` function, and **H2 is the first and only scenario to reach CRITICAL** in this entire exercise.

---

## 2. Global validation checks (all 45 scenario rows)

| Check | Result |
|---|---|
| No NaN/inf in stress_score, utilization, or voltage | **True** |
| stress_score bounded [0, 100] | **True** |
| HIGH occurs somewhere | **True** (E, F, G, H1) |
| CRITICAL occurs somewhere | **True** (H2) |
| Overload detection activates somewhere | **True** (F, H1, H2) |
| Voltage stress activates somewhere | **True** (H1, H2) |
| Increasing demand never decreases stress (all 10 feeders, A→D) | **True** |

**Every target pathway listed in the task was successfully exercised at least once, using only the existing, unmodified engine.**

---

## 3. Time-to-overload: three controlled trajectories

Capacity reference: F10's real capacity (5.76 MW).

| # | Trajectory | Expected | Actual `overload_predicted` | Actual `time_to_overload_hours` |
|---|---|---|---|---|
| 1 | Never crosses (0.40×→0.55×capacity, stays below throughout) | No overload | **False** | **None** |
| 2 | Crosses exactly halfway (0.50×→1.50×capacity, linear) | Overload at h=12.0 (algebraic) | **True** | **12.0000** (exact match) |
| 3 | Already above capacity at h=0 (1.10×→1.30×capacity) | Overload at h=0, not interpolated | **True**, `time_to_overload_hours=0.0`, `interpolated=False` | Matches exactly |

All three behave exactly as expected, with the halfway-crossing case validated against an independently computed algebraic expected value, not just eyeballed.

---

## 4. Scenario summary table

| Scenario | What it tests | Stress score | Risk level | Overload predicted |
|---|---|---|---|---|
| A_NORMAL (all feeders) | Baseline | 7.0 – 31.6 | LOW (8/10), MODERATE (2/10 borderline) | No |
| B/C/D_ELEVATED (+10/20/30%) | Demand growth | 7.7 – 41.1 | LOW / MODERATE | No |
| E_TIGHT_CAPACITY | Reduced headroom, load fixed | 66.13 | **HIGH** | No |
| F_OVERLOAD | Explicit crossing trajectory | 69.00 | **HIGH** | **Yes (h=12.0)** |
| G_HIGH_UTILIZATION | Near-capacity, no crossing | 73.65 | **HIGH** | No |
| H1_VOLTAGE_STRESS_PARTIAL | 130% utilization | 77.00 | **HIGH** | Yes (h=0, already over) |
| H2_VOLTAGE_STRESS_SATURATED | 170% utilization | **85.00** | **CRITICAL** | Yes (h=0, already over) |

**This is what the existing, unmodified engine actually produced — no scenario was adjusted after the fact to hit a particular label.** Notably, ordinary demand growth (A–D) tops out well within MODERATE; reaching HIGH required either a tighter capacity assumption (E), an explicit overload trajectory (F), sustained near-100% utilization (G), or overt overload with voltage sag (H); reaching CRITICAL required the most extreme constructed input (H2, 170% utilization) — CRITICAL was not "easy" to trigger even deliberately.

---

## 5. Plots

Saved under `ml/reports/figures/stress_scenarios/` (all captions/titles marked as simulated inputs):

- [demand_elevation_stress_by_feeder.png](figures/stress_scenarios/demand_elevation_stress_by_feeder.png) — stress score vs. demand multiplier, all 10 feeders, scenarios A–D
- [voltage_stress_activation.png](figures/stress_scenarios/voltage_stress_activation.png) — utilization→voltage and utilization→voltage_stress_component curves (unmodified voltage model), with H1/H2 marked
- [overload_trajectory_scenario_f.png](figures/stress_scenarios/overload_trajectory_scenario_f.png) — Scenario F's constructed trajectory crossing capacity, with the detected crossing point marked
- [time_to_overload_scenarios.png](figures/stress_scenarios/time_to_overload_scenarios.png) — the three Section 3 trajectories overlaid against capacity
- [all_scenarios_summary.png](figures/stress_scenarios/all_scenarios_summary.png) — every scenario's score, color-coded by risk level

---

## Limitations

- All scenario inputs (demand multipliers, tight-capacity value, overload trajectory shape, voltage-stress utilization levels) were chosen by the analyst to exercise specific code paths — they are not drawn from or validated against any real feeder behavior, because no such data exists in this project.
- Only one feeder (F10) was used for scenarios E–H; other feeders would activate the same paths at different absolute MW levels (proportional to their own capacity) but the underlying formula behavior is identical across feeders, so this is not expected to change the conclusions.
- The explicit linear trajectories constructed here (`make_linear_trajectory`) are simpler than `feeder_generator.build_national_trajectory`'s diurnal-shape-based interpolation — they were deliberately kept simple so the expected crossing point could be computed algebraically and compared exactly, not to represent realistic demand curves.
- This exercise confirms the engine's mechanics respond correctly to constructed inputs; it still does not confirm that the LOW/MODERATE/HIGH/CRITICAL boundaries or the stress formula's weights correspond to any real-world grid-reliability meaning — that remains unvalidated, as stated throughout.

---

## Final recommendation

**A) Upper-range behavior validated → proceed to rolling integration.**

All target pathways were successfully and correctly exercised using the existing, unmodified engine: HIGH occurred (four different ways: tight capacity, explicit overload, near-capacity utilization, and partial voltage stress), CRITICAL occurred (saturated voltage stress), overload detection activated and its crossing-time interpolation matched an independently computed algebraic expected value exactly, and voltage stress activated precisely at its documented 0.95pu threshold and saturated precisely at 0.90pu. Increasing demand never decreased stress across all 10 feeders. No NaN/inf values and no out-of-bounds scores occurred across all 45 constructed scenarios. No implementation bug was found, so — per the task instructions — nothing in `stress_engine.py` or `feeder_generator.py` was changed. The engine's mechanics are now confirmed to behave sensibly across its full documented range (not just the narrow band the natural historical data happened to explore), which is the specific gap [stress_engine_sanity.md](stress_engine_sanity.md) Section 8 flagged before recommending this step. The rolling integration layer can proceed on top of this validated mechanical behavior — with the still-open caveat, unchanged from prior reports, that the weights and thresholds themselves remain uncalibrated engineering choices, not validated real-world risk measures.
