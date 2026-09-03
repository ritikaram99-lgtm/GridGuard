# GridGuard AI — What-If Scenario Simulation Engine

**Scripts:** [ml/src/simulation_engine.py](../src/simulation_engine.py), [ml/src/evaluate_simulation_engine.py](../src/evaluate_simulation_engine.py)
**Tests:** [ml/tests/test_simulation_engine.py](../tests/test_simulation_engine.py) — 28/28 passing (125/125 across the full ML test suite, no regressions)
**Data:** `ml/data/simulation_engine_evaluation_results.csv`, `ml/reports/simulation_engine_evaluation_summary.json`
**Plots:** `ml/reports/figures/simulation_engine/*.png`

**This is a decision-support simulation, NOT real grid control, and NOT a newly trained ML model.** Does not modify any trained model, the feature pipeline, `regime_detector.py`, `robust_hourly_forecast.py`, `feeder_generator.py`, `stress_engine.py`, `rolling_integration.py`, or `action_engine.py` — this module imports and reuses `action_engine.py`'s existing resource-limit definitions and trajectory-application logic unmodified.

---

## 1. Architecture

```
Existing 24h forecast (unmodified, from rolling_integration.py / direct_hourly_forecast.py)
        v
Scenario parameters (ambient_temperature_c, ev_surge_pct, solar_drop_pct)
        v
Apply scenario adjustments (THIS MODULE — documented synthetic coefficients)
        v
Modified 24h load trajectory
        v
Existing, UNMODIFIED Stress Engine (via action_engine.evaluate_trajectory)
        v
Scenario outcome
        v
(optional) Action Engine intervention (EV/Battery/Industrial, existing limits)
        v
Existing, UNMODIFIED Stress Engine again
        v
Final before/after comparison
```

**Why a scenario layer, not a model input:** the direct XGBoost forecasting models intentionally exclude target-time weather (no real weather-forecast data exists in this project — see `build_features.py`'s documented rationale), and have no EV-surge or solar-generation features at all — neither signal exists anywhere in the underlying Mendeley dataset. **The three what-if sliders therefore cannot be, and are not, fed into the forecasting models.** Instead, this module takes the model's existing, unmodified 24h forecast as a baseline and applies transparent, deterministic adjustments on top of it — a scenario model, not a forecast model.

**The Stress Engine remains the sole source of truth** for stress score, risk level, utilization, voltage, and time-to-overload at every stage (baseline, post-scenario, post-intervention) — all three evaluations call `action_engine.evaluate_trajectory()`, which itself calls `stress_engine.py`'s existing, unmodified functions. Nothing is recreated or approximated.

---

## 2. Scenario inputs

| Input | Type | Description |
|---|---|---|
| `ambient_temperature_c` | float or `None` | Absolute ambient temperature for the scenario (°C). `None` = no temperature effect. |
| `ev_surge_pct` | float, default 0 | % change in EV charging demand (signed; negative = decrease). |
| `solar_drop_pct` | float, default 0 | % drop in behind-the-meter solar generation (typically 0-100). |
| `feeder_type` | str | One of RESIDENTIAL / COMMERCIAL / INDUSTRIAL / MIXED / EV_HEAVY — determines EV-surge sensitivity. |
| `baseline_trajectory` | pd.Series, or `baseline_forecast_mw` + `target_timestamp` | The existing 24h forecast to scenario-adjust. |
| `proposed_actions` | optional list | EV/Battery/Industrial intervention(s) to layer on top, reusing `action_engine.py`'s existing limits. |

---

## 3. Scenario equations / logic

All three effects are computed as **exact, additive MW contributions** so they can be attributed individually and sum exactly to the total change — no residual or interaction term.

**Temperature** (multiplicative on baseline load, uniform across all 24 hours):
```
temp_multiplier = 1 + (2.0% / °C) × (ambient_temperature_c − 27.0°C reference)
temperature_effect_mw(t) = baseline_load(t) × (temp_multiplier − 1)
```

**EV surge** (proportional to baseline load, feeder-type-weighted):
```
ev_surge_effect_mw(t) = baseline_load(t) × (ev_surge_pct / 100) × feeder_type_ev_sensitivity
```
where `feeder_type_ev_sensitivity` = 1.00 (EV_HEAVY), 0.40 (MIXED), 0.20 (RESIDENTIAL), 0.05 (COMMERCIAL), 0.00 (INDUSTRIAL).

**Solar drop** (additive, daylight-hours-only, capacity-scaled):
```
solar_drop_effect_mw(t) = (solar_drop_pct / 100) × 0.10 × capacity_mw × daylight_shape(hour(t))
daylight_shape(h) = sin(π × (h − 7) / 11)  for h in [7, 18], else 0   (peaks at solar noon)
```

**Combined:**
```
scenario_load(t) = max(baseline_load(t) + temperature_effect_mw(t) + ev_surge_effect_mw(t) + solar_drop_effect_mw(t), 0)
```

Verified by test (`test_combined_scenario_sums_individual_effects_exactly`): `load_change_mw["total"] == temperature + ev_surge + solar_drop` to within floating-point tolerance, for every scenario.

---

## 4. Synthetic assumptions — explicit, all documented, none learned

| Assumption | Value | Status |
|---|---|---|
| Reference temperature | 27.0 °C | **Synthetic** — a round documented reference, not derived from data |
| Temperature sensitivity | +2.0% load per +1 °C | **Synthetic** — the *sign* is loosely motivated by the ~0.65 real correlation between temperature and national demand found in the original dataset audit, but the coefficient itself was **not fitted or learned** — it is a chosen-for-plausibility scenario parameter |
| EV feeder-type sensitivity weights | 1.00 / 0.40 / 0.20 / 0.05 / 0.00 | **Synthetic** — hand-chosen, not derived from any real EV penetration study |
| Solar penetration fraction | 10% of feeder capacity | **Synthetic** — an assumed behind-the-meter solar capacity, not measured |
| Daylight shape | half-sine, hours 7–18 | **Synthetic** — a simplification of a real solar generation profile, not measured irradiance data |
| EV/Battery/Industrial intervention limits | reused unmodified from `action_engine.py` | Same synthetic assumptions already documented there (0.15/0.20/0.25 × capacity, etc.) |

**None of these coefficients are derived from real Panama feeder telemetry.** The underlying feeder loads and capacities they're applied to are themselves synthetic (see `feeder_generator.py`).

---

## 5. Intervention compatibility

`proposed_actions` (optional) are applied **on top of** the scenario-adjusted trajectory, reusing `action_engine.py`'s existing `Action`, `build_resources_for_capacity`, and `apply_actions_to_trajectory` **unmodified** — the same synthetic resource limits, the same clipping-to-limit behavior, and the same three-tier feasibility classification:
- **`feasible`** — every proposed action was within limits as requested.
- **`partially_feasible`** — at least one action was clipped to a resource's limit.
- **`infeasible`** — no proposed action was valid at all (unknown resource, non-positive values).

This mirrors `action_engine.py`'s feasibility semantics exactly, so both engines behave consistently for a user moving between "recommend an action" (Action Engine) and "show me what this specific action does" (this module).

---

## 6. Stress Engine integration — verified

`test_stress_scores_match_stress_engine_directly` independently recomputes a scenario's stress score via a direct call to `stress_engine.compute_stress_score` / `classify_stress` and confirms it matches the simulation engine's reported value exactly. Every one of the three evaluation stages (baseline, scenario, post-intervention) goes through this same unmodified path — there is no separate/parallel stress calculation anywhere in this module.

---

## 7. Test results — 28/28 passed

Covers all 12 requested categories: baseline (zero scenario params) leaves the trajectory unchanged; temperature, EV surge, and solar drop each independently and correctly affect output (including feeder-type and daylight-hour edge cases); combined scenario effects sum exactly; intervention reduces load; the full scenario+intervention pipeline behaves consistently; stress is independently verified against `stress_engine.py`; overload status is correctly derived from `time_to_overload`; extreme/negative inputs never produce negative load; results are fully deterministic across repeated calls; and invalid inputs (bad capacity, NaN temperature, negative trajectory, missing baseline, unknown resource, over-limit action) are all correctly rejected or classified.

Full ML test suite (125 tests across `simulation_engine`, `action_engine`, `regime_detector`, `feeder_simulation`) passes with no regressions.

---

## 8. Controlled scenario results

Seven scenarios (round reference `capacity_mw = 100.0`, EV_HEAVY feeder, all explicitly labeled CONTROLLED SIMULATION):

| Scenario | Baseline peak | Scenario peak | Final peak | Baseline→Final risk | Overload after scenario | Overload avoided |
|---|---|---|---|---|---|---|
| NOMINAL | 80.0 | 80.0 | 80.0 | MODERATE→MODERATE | False | — |
| HIGH_TEMPERATURE | 80.0 | 97.6 | 97.6 | MODERATE→MODERATE | False | — |
| HIGH_EV_SURGE | 80.0 | 136.0 | 136.0 | MODERATE→HIGH | **True** | — (no intervention) |
| LOW_SOLAR | 80.0 | 82.2 | 82.2 | MODERATE→MODERATE | False | — |
| COMBINED_ADVERSE | 80.0 | 142.6 | 142.6 | MODERATE→HIGH | **True** | — (no intervention) |
| **ADVERSE_PLUS_SUCCESSFUL_INTERVENTION** | 80.0 | 141.6 | **81.6** | MODERATE→**MODERATE** | True | **True** |
| **ADVERSE_PLUS_INSUFFICIENT_INTERVENTION** | 80.0 | 176.0 | 156.0 | MODERATE→HIGH | True | **False** |

**NOMINAL confirms the scenario layer is a true no-op at reference parameters** (scenario == baseline exactly). **HIGH_TEMPERATURE/HIGH_EV_SURGE/LOW_SOLAR each isolate their respective effect** (verified: the other two variables' `load_change_mw` are exactly zero in each single-factor scenario). **COMBINED_ADVERSE exceeds any single factor alone** (142.6 MW vs. 136.0 MW for EV surge alone, the largest individual contributor).

**ADVERSE_PLUS_SUCCESSFUL_INTERVENTION** uses a trajectory whose peak falls early (h=2, within every resource's duration window) — with all three synthetic resources fully deployed (EV 15 MW/4h + Battery 20 MW/3.5h + Industrial 25 MW/6h = 60 MW), the peak drops from 141.6 to 81.6 MW and **overload is genuinely avoided**, confirmed by `stress_engine.time_to_overload` on the recalculated trajectory.

**ADVERSE_PLUS_INSUFFICIENT_INTERVENTION** (same early-peak trajectory, more extreme conditions, only a single small resource) reduces the peak (176.0 → 156.0 MW, 20 MW applied) but **honestly reports `overload_avoided: False`** — the engine never claims success it didn't achieve.

**Summary:** 0 of 7 scenarios start overloaded (deliberately — the baseline is sub-capacity, as scenarios are meant to test); 4 develop overload after scenario adjustment; of the 2 scenarios with an intervention applied, 1 successfully avoids overload and 1 does not (correctly reported).

Plots: [peak_load_stages.png](figures/simulation_engine/peak_load_stages.png) (baseline → scenario → post-intervention, all 7 scenarios), [stress_before_after.png](figures/simulation_engine/stress_before_after.png), [attribution_combined_adverse.png](figures/simulation_engine/attribution_combined_adverse.png) (per-variable MW breakdown).

---

## 9. Limitations

1. **Scenario coefficients are synthetic and unvalidated** — restated per this task's requirement; the temperature sign is data-motivated, but no coefficient here was fitted to real data.
2. **Scenario effects are applied uniformly/simply** — temperature is a flat multiplier across all hours (no time-of-day-dependent cooling-load curve); EV surge is a flat proportional scaling (no charging-window-specific shape); solar drop uses a simplified half-sine daylight profile, not measured irradiance or cloud-cover data.
3. **The duration-vs-magnitude intervention limitation carries over from `action_engine.py`** — a resource dispatched at h=0 cannot help with stress that occurs after its duration expires; this module inherits that behavior by design (it reuses `action_engine.py`'s trajectory-application logic unmodified) and it was directly encountered during scenario design (see Section 8's discussion of trajectory peak timing).
4. **The flat-trajectory fallback** (`build_flat_trajectory`, used when only a scalar `baseline_forecast_mw` is supplied instead of a real 24-point forecast) is a documented approximation — time-to-overload precision is reduced in that mode versus supplying a real trajectory from `rolling_integration.py`.
5. **Not validated against real weather, EV, or solar data** — no such data exists in this project for Panama feeders.

## Files created

- [ml/src/simulation_engine.py](../src/simulation_engine.py)
- [ml/src/evaluate_simulation_engine.py](../src/evaluate_simulation_engine.py)
- [ml/tests/test_simulation_engine.py](../tests/test_simulation_engine.py)
- [ml/reports/simulation_engine_report.md](simulation_engine_report.md) (this document), `ml/reports/simulation_engine_evaluation_summary.json`, `ml/data/simulation_engine_evaluation_results.csv`, 3 plots under `ml/reports/figures/simulation_engine/`

**Not modified:** any trained model, `regime_detector.py`, `robust_hourly_forecast.py`, `feeder_generator.py`, `stress_engine.py`, `rolling_integration.py`, or `action_engine.py` (imported and reused only). No backend, frontend, Gemini, or database work was started.
