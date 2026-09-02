# GridGuard AI — Prevention / Decision Engine

**Scripts:** [ml/src/prevention_engine.py](../src/prevention_engine.py), [ml/src/evaluate_prevention_engine.py](../src/evaluate_prevention_engine.py)
**Tests:** [ml/tests/test_prevention_engine.py](../tests/test_prevention_engine.py) — 27/27 passing
**Data:** `ml/data/prevention_engine_evaluation_results.csv`, `ml/reports/prevention_engine_evaluation_summary.json`
**Plots:** `ml/reports/figures/prevention_engine/*.png`

**This is a decision-support simulation, NOT real grid control, and NOT another ML model.** It orchestrates the existing Action Engine and Simulation Engine and selects among their outputs — it does not recreate forecasting, stress calculations, utilization calculations, risk calculations, or intervention constraints anywhere in this file. Does not modify any trained model, `regime_detector.py`, `robust_hourly_forecast.py`, `feeder_generator.py`, `stress_engine.py`, `rolling_integration.py`, `action_engine.py`, or `simulation_engine.py`.

---

## 1. Architecture

```
Stressed feeder
    v
Action Engine (action_engine.py, unmodified)
    v          -- generate_candidate_interventions(): 8 candidates
    v             (NO_ACTION + all 7 non-empty combinations of
    v              EV/Battery/Industrial, using action_engine's existing
    v              resource limits and disruption costs, unmodified)
Simulation Engine (simulation_engine.py, unmodified)
    v          -- verify_candidate(): simulate_scenario() with the
    v             candidate as a proposed_action and NO scenario
    v             adjustments, which itself calls the existing,
    v             unmodified Stress Engine for every before/after metric
Evaluate BEFORE vs AFTER
    v
Rank feasible candidates (deterministic, documented, this file only)
    v
Best recommendation
    v
Prevention result
```

**No stress, utilization, risk, or constraint logic is defined in this file.** Every number in the output comes from a call into `action_engine.py` (resource limits, candidate structure) or `simulation_engine.py` (which in turn calls `stress_engine.py`, unmodified).

---

## 2. Decision flow

1. **Baseline** — call `simulation_engine.simulate_scenario()` with no proposed action and no scenario adjustment, to get the feeder's current stress/risk/overload status purely via the existing Stress Engine.
2. **Is it already safe?** If `not overload_before` and `baseline_risk` is LOW/MODERATE → `NO_ACTION_REQUIRED`, stop immediately (no candidates generated).
3. **Otherwise**, generate all 8 candidates (Action Engine) and verify each (Simulation Engine).
4. **Rank** deterministically (Section 5) and select the best.
5. **Classify** the outcome into one of five statuses (Section 6) based on what the Stress Engine actually confirmed.

---

## 3. Candidate generation

`generate_candidate_interventions(capacity_mw)` calls `action_engine.build_resources_for_capacity()` (existing, unmodified) to get each resource's synthetic MW/duration/cost limits for this feeder, then builds:
- 1 × `NO_ACTION` (empty action list, for uniform baseline handling)
- 7 × non-empty combinations of {EV, BATTERY, INDUSTRIAL}, each candidate's actions set to that resource's **maximum** available MW/duration (the same "fully deployed or not deployed" binary model already established in `action_engine.py`)

No new resource magnitudes, durations, or costs are invented here — every limit is read from the existing Action Engine.

---

## 4. Simulation verification

Each candidate is verified by calling `simulation_engine.simulate_scenario()` with `proposed_actions=candidate["actions"]` and no temperature/EV-surge/solar-drop parameters (i.e., only the intervention layer of that module is exercised). This reuses:
- `simulation_engine`'s existing feasibility classification (feasible / partially_feasible / infeasible) against `action_engine`'s resource limits
- `simulation_engine`'s existing trajectory application (`action_engine.apply_actions_to_trajectory`, unmodified)
- `simulation_engine`'s existing before/after evaluation (`action_engine.evaluate_trajectory`, which calls `stress_engine.py` directly, unmodified)

The Prevention Engine never touches a trajectory, MW value, or stress score directly — every one comes back from this call.

---

## 5. Ranking logic (deterministic, exactly as specified)

```
1. Successfully resolves the risk
   (overload_before -> overload_after == False;  OR
    not overload_before -> projected risk in {LOW, MODERATE})
2. Lowest intervention cost (sum of resource disruption costs)
3. Lowest total MW deployed
4. Fewer simultaneous interventions, if still tied
```

Implemented as a plain sort key (`_ranking_key`) — no randomness, fully reproducible, directly unit-tested (`test_equal_cost_candidates_prefer_lower_mw`, `test_fewer_interventions_preferred_when_otherwise_equivalent`).

---

## 6. Prevention statuses

| Status | Meaning |
|---|---|
| `NO_ACTION_REQUIRED` | Feeder already safe; no candidates generated |
| `PREVENTED` | Best candidate resolves the risk, confirmed by the Stress Engine |
| `INSUFFICIENT_FLEXIBILITY` | Even all three resources combined provide less MW than the required reduction (magnitude-limited) |
| `DURATION_LIMITED` | Combined resources numerically provide enough MW, but no candidate's duration reaches the moment of peak risk (timing-limited) |
| `REDUCED_NOT_PREVENTED` | Fallback status for any other not-resolved case not cleanly classified as the two above |

The magnitude-vs-duration distinction (`INSUFFICIENT_FLEXIBILITY` vs. `DURATION_LIMITED`) reuses the exact same diagnostic bookkeeping (`required_reduction_mw` vs. `max_feasible_reduction_mw`) already established and validated in the Action Engine work — computed here only as a classification aid over already-known Stress Engine outputs, never as a new stress calculation.

**Never claims `PREVENTED` falsely:** the status is set only after `simulation_engine`'s recalculated `overload_after` / `final_risk` (both derived from `stress_engine.time_to_overload` / `classify_stress`) confirm resolution — verified directly by `test_prevented_status_only_when_stress_engine_confirms_no_overload` and `test_never_falsely_claims_prevented`.

---

## 7. Controlled evaluation results

Seven scenarios (round reference `capacity_mw = 100.0`, all explicitly labeled CONTROLLED SIMULATION):

| Scenario | Baseline load | Baseline risk | Status | Actions | Cost | Reduction | Projected load | Projected risk |
|---|---|---|---|---|---|---|---|---|
| SAFE | 60.0 | MODERATE | **NO_ACTION_REQUIRED** | none | 0.0 | 0.0 | 60.0 | MODERATE |
| SMALL_OVERLOAD | 108.0 | HIGH | **PREVENTED** | BATTERY | 0.5 | 20.0 | 88.0 | MODERATE |
| MULTIPLE_FEASIBLE | 109.0 | HIGH | **PREVENTED** | BATTERY | 0.5 | 20.0 | 89.0 | HIGH |
| LARGER_OVERLOAD | 130.0 | HIGH | **PREVENTED** | BATTERY+INDUSTRIAL | 3.5 | 45.0 | 85.0 | MODERATE |
| INSUFFICIENT_FLEXIBILITY | 175.0 | HIGH | **INSUFFICIENT_FLEXIBILITY** | BATTERY | 0.5 | 20.0 | 155.0 | MODERATE |
| DURATION_LIMITED | 140.0 | HIGH | **DURATION_LIMITED** | BATTERY | 0.5 | 20.0 | 120.0 | HIGH |
| HIGH_RISK_NO_OVERLOAD | 92.0 | HIGH | **PREVENTED** | EV+BATTERY | 1.5 | 35.0 | 92.0 | MODERATE |

All 7 assertions passed, including `MULTIPLE_FEASIBLE` correctly selecting the cheapest of >1 feasible candidates (BATTERY, cost 0.5) over more expensive but equally-sufficient options.

**A genuinely instructive result worth explaining, not hiding:** `HIGH_RISK_NO_OVERLOAD`'s recommended intervention (EV+Battery) does **not** change the trajectory's peak/endpoint value at all (projected_load_mw = 92.0, identical to baseline) — because both resources' durations (≤4h) expire well before hour 24, where this trajectory's maximum occurs. Yet the status is correctly `PREVENTED`, because `stress_score` is weighted ~45% by **current** utilization (`current_utilization` + `headroom`, which are mathematically identical per the stress-engine sanity analysis from an earlier stage) and only ~30% by forecast/endpoint utilization — reducing the *current* load substantially (88 → well below via EV+Battery) is enough to drop the overall risk from HIGH to MODERATE even without touching the future peak. **This is the existing Stress Engine's own weighting doing exactly what it's defined to do** — the Prevention Engine faithfully reports what the Stress Engine confirms, nothing more.

### Representative real-data example

Ran against one real origin/feeder from the existing `rolling_integration.py` output (`ml/data/rolling_feeder_results.csv`) — **feeder F10, origin 2020-01-20 20:00** (the highest-stress observation identified in earlier project stages):

```
Feeder: F10 (EV_HEAVY), capacity=5.76 MW   [REAL — feeder_generator.py's synthetic capacity, unmodified]
Baseline: load=5.01 MW, risk=HIGH, stress=64.60, overload_before=False   [REAL — Stress Engine output on the real forecast trajectory]
Recommendation: status=PREVENTED, actions=['BATTERY']
```

The baseline `stress=64.60` matches exactly the value independently reported in `rolling_integration_report.md` for this same feeder/origin, confirming the loader (`action_engine.load_scenario_from_rolling_results`) correctly reconstructs the real trajectory from the pipeline's output. **The forecast trajectory and capacity here are real model outputs; the recommended BATTERY action and its magnitude remain a synthetic assumption**, as throughout this entire Action/Simulation/Prevention layer.

**Summary statistics** (`ml/reports/prevention_engine_evaluation_summary.json`):
- Scenarios: 7 (1 safe, 5 with baseline overload, 1 elevated-risk-without-overload)
- Prevented: 4, Insufficient flexibility: 1, Duration limited: 1, Reduced-not-prevented: 0
- Average intervention cost (where actioned): 1.17
- Average MW reduction (where actioned): 26.67
- Intervention combinations selected: BATTERY (4×), BATTERY+INDUSTRIAL (1×), EV+BATTERY (1×) — **BATTERY appears most often because it is the cheapest resource (cost 0.5) and is selected whenever it alone is sufficient**, consistent with the cost-minimizing ranking objective.

Plots: [baseline_vs_projected_load.png](figures/prevention_engine/baseline_vs_projected_load.png), [cost_by_status.png](figures/prevention_engine/cost_by_status.png).

---

## 8. Synthetic assumptions

**All EV/Battery/Industrial resource assumptions remain synthetic**, inherited entirely and unmodified from `action_engine.py`'s `RESOURCE_ASSUMPTIONS` (EV: 15% capacity/4h/cost 1.0; Battery: 20% capacity/SOC-derived ≤4h/cost 0.5; Industrial: 25% capacity/6h/cost 3.0). Nothing here introduces any new synthetic value — the Prevention Engine's only original logic is the ranking key and the five-way status classification, both of which operate purely on already-computed Action/Simulation outputs.

---

## 9. Limitations

1. **Inherits the duration-vs-magnitude limitation** from `action_engine.py`/`simulation_engine.py` by design (candidates are dispatched starting at h=0; a resource cannot help with risk occurring after its duration expires) — `DURATION_LIMITED` exists specifically to report this honestly rather than hide it.
2. **Binary (all-or-nothing) candidate deployment** — no continuous/partial-magnitude search across the 7 combinations; a future version could explore partial deployments for cheaper marginal solutions.
3. **8 candidates is a small, complete search space** for 3 resources — this scales combinatorially and would need revisiting if more resource types were added.
4. **`REDUCED_NOT_PREVENTED` is a fallback status** not exercised by any of the 7 controlled scenarios here (all "not resolved" cases in this evaluation cleanly fell into either `INSUFFICIENT_FLEXIBILITY` or `DURATION_LIMITED`) — it exists for completeness for edge cases where no valid action can be applied at all despite one being needed.
5. **Not validated against real grid operators or control systems** — a decision-support simulation only, at the end of a pipeline (forecast → feeder simulation → stress → action/simulation → prevention) where every upstream stage's own limitations (documented in each stage's respective report) still apply.

## Files created

- [ml/src/prevention_engine.py](../src/prevention_engine.py)
- [ml/src/evaluate_prevention_engine.py](../src/evaluate_prevention_engine.py)
- [ml/tests/test_prevention_engine.py](../tests/test_prevention_engine.py)
- [ml/reports/prevention_engine_report.md](prevention_engine_report.md) (this document), `ml/reports/prevention_engine_evaluation_summary.json`, `ml/data/prevention_engine_evaluation_results.csv`, 2 plots under `ml/reports/figures/prevention_engine/`

**Not modified:** any trained model, `regime_detector.py`, `robust_hourly_forecast.py`, `feeder_generator.py`, `stress_engine.py`, `rolling_integration.py`, `action_engine.py`, or `simulation_engine.py` (all imported and reused only). No backend, frontend, or Gemini integration was started.
