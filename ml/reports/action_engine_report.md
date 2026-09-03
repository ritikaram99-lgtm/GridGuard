# GridGuard AI — Action / Optimization Engine

**Scripts:** [ml/src/action_engine.py](../src/action_engine.py), [ml/src/evaluate_action_engine.py](../src/evaluate_action_engine.py)
**Tests:** [ml/tests/test_action_engine.py](../tests/test_action_engine.py) — 32/32 passing
**Data:** `ml/data/action_engine_evaluation_results.csv`, `ml/reports/action_engine_evaluation_summary.json`
**Plots:** `ml/reports/figures/action_engine/evaluate_*.png`

**This is a decision-support simulation, NOT real grid control.** It does not modify any trained model, `regime_detector.py`, `robust_hourly_forecast.py`, `feeder_generator.py`, `stress_engine.py`, or `rolling_integration.py` — this stage rebuilds `action_engine.py` to consume the current pipeline's real output schema (genuine hourly, regime-aware forecast trajectories from `rolling_integration.py`) in place of the earlier prototype, which was built against the now-superseded interpolated-trajectory pipeline.

---

## 1. Architecture

```
rolling_integration.py output (feeder_id, forecast trajectory, capacity, ...)
        v
FeederScenario  (this module's input container)
        v
evaluate_trajectory()  -->  existing, unmodified stress_engine.py
        |                   (compute_stress_score, classify_stress, time_to_overload)
        v
baseline metrics  -->  is action needed?
        v
generate_candidates()  -->  7 combinations of {EV, Battery, Industrial}
        v
apply_actions_to_trajectory()  -->  modified trajectory
        v
evaluate_trajectory() AGAIN on the modified trajectory (same stress_engine calls)
        v
recommend_action()  -->  ranked candidates, best feasible action
```

**The stress engine remains the sole source of truth for risk** — every baseline and projected metric is produced by calling `stress_engine.py`'s existing, unmodified functions, never by assuming `projected_load = load - action` resolves the problem on its own.

## 2. Synthetic assumptions

**All flexibility values are synthetic engineering assumptions**, sized as a fraction of each feeder's own (also synthetic) `capacity_mw` — none of these numbers come from real Panama EV fleets, battery installations, or industrial demand-response contracts.

| Resource | Magnitude | Duration | Disruption cost |
|---|---|---|---|
| EV charging shift | 0.15 × capacity_mw | ≤ 4h | 1.0 |
| Battery discharge | 0.20 × capacity_mw | min(energy/power, 4h); energy = 1.0×capacity_mw MWh at 70% SOC | 0.5 |
| Industrial load shift | 0.25 × capacity_mw | ≤ 6h | 3.0 |

Combined maximum: 0.60 × capacity_mw — deliberately not enough to guarantee every overload is preventable (see `INSUFFICIENT_FLEXIBILITY` result below). A non-overload "elevated risk" target (`NON_OVERLOAD_TARGET_UTILIZATION = 0.90`) is used when stress is HIGH/CRITICAL but no overload is yet predicted — also a documented, tunable engineering threshold, not a validated real-world value.

## 3. Decision logic

1. **Required MW reduction** — `peak_load - capacity` if overload predicted; otherwise `peak_load - 0.90×capacity` (the elevated-risk safety-margin target).
2. **Available flexibility** — the 3 synthetic resources, sized to the specific feeder's capacity; 7 non-empty combinations generated.
3. **Selection** — deterministic 3-tier sort: (1) resolves the trigger (prevents overload, or brings peak utilization under the 90% margin), (2) minimizes disruption cost, (3) minimizes total MW deployed. Never optimizes for maximum reduction.
4. **Constraints** — each resource's own MW/duration/SOC limits are enforced by construction; verified never violated (test suite).
5. **Insufficient flexibility** — if no combination resolves the trigger, the engine reports `overload_avoided: False` plus `required_reduction_mw`, `max_feasible_reduction_mw`, `remaining_overload_mw`, and a best-effort action — never a false claim of success.

This is a **simple, transparent rule-based combinatorial search** over 7 candidates (not RL, not a neural network, not an LLM) — every step is inspectable and reproducible.

---

## 4. Output schema

Each `recommend_action()` call returns:

```
feeder_id, feeder_type, target_timestamp, baseline_forecast_mw, capacity_mw,
baseline_utilization, baseline_risk_level, baseline_overload_predicted,
action_required, recommended_actions (list), total_reduction_mw,
projected_load_mw, projected_utilization, projected_risk_level,
overload_avoided, intervention_cost, reason, alternatives (list)
```

`target_timestamp` is the timestamp of the trajectory's **peak** load (the actual moment of concern), not just the 24h endpoint. `reason` is a plain-English explanation referencing the specific feeder, timestamp, and selected action.

---

## 5. Controlled scenario results

Eight scenarios were run (round reference `capacity_mw = 100.0`, hand-verifiable — all explicitly labeled CONTROLLED SIMULATION, not real feeder events):

| Scenario | Baseline peak | Baseline risk | Action | Cost | Projected peak | Overload avoided |
|---|---|---|---|---|---|---|
| SAFE | 60.0 | MODERATE | none | 0.0 | 60.0 | — (n/a, no overload) |
| EV_ONLY_SUFFICIENT | 112.0 | HIGH | BATTERY | 0.5 | 92.0 | **True** |
| BATTERY_ONLY_SUFFICIENT | 108.0 | HIGH | BATTERY | 0.5 | 90.0 | **True** |
| INDUSTRIAL_ONLY_SUFFICIENT | 108.0 | HIGH | BATTERY | 0.5 | 90.0 | **True** |
| COMBINED_REQUIRED | 130.0 | HIGH | BATTERY+INDUSTRIAL | 3.5 | 94.7 | **True** |
| INSUFFICIENT_FLEXIBILITY | 175.0 | HIGH | EV+BATTERY+INDUSTRIAL | 4.5 | 115.0 | **False** (remaining 15.0 MW) |
| DURATION_LIMITED | 140.0 | HIGH | EV+INDUSTRIAL | 4.0 | 102.0 | **False** (peak reduced, not eliminated) |
| HIGH_RISK_NO_OVERLOAD | 92.0 | HIGH | BATTERY | 0.5 | 92.0 | **False** (peak untouched — see note) |

**A notable, honestly-reported result:** `EV_ONLY_SUFFICIENT` and `INDUSTRIAL_ONLY_SUFFICIENT` were deliberately named/sized to test whether each resource *individually* can resolve its scenario — and in both cases the engine correctly selected **BATTERY** instead, because Battery is cheaper (0.5 vs. 1.0 for EV, vs. 3.0 for Industrial) and was *also* magnitude-sufficient for these particular overshoots. This is not a bug — it is the cost-minimizing objective working exactly as designed: the engine never picks a more expensive resource just because a scenario's name suggests it, only because it's actually the best available option. It demonstrates the same "multiple feasible solutions → prefer lowest cost" behavior established in the earlier Action Engine work.

**`HIGH_RISK_NO_OVERLOAD` result explained:** this scenario's load rises slowly from 88 to 92 MW across the full 24h horizon, with the peak occurring at the very last hour (h=24) — beyond every resource's maximum duration (Battery 3.5h, EV 4h, Industrial 6h). No combination can touch the actual peak, so the engine correctly reports the trigger as unresolved rather than claiming a fix. This is a second, distinct real demonstration of the **duration-vs-magnitude** limitation (see below), now also occurring for a non-overload, elevated-risk trigger.

**Summary statistics** (`ml/reports/action_engine_evaluation_summary.json`):
- Overloads before: 6 (of 8 scenarios)
- Overloads avoided: 4
- Insufficient-flexibility cases: 2 (`INSUFFICIENT_FLEXIBILITY`, magnitude-limited; `DURATION_LIMITED`, duration-limited — two distinct failure modes, both correctly distinguished and reported)
- Average MW reduction where action was taken: 32.14 MW

Plots: `evaluate_before_after_peak.png`, `evaluate_intervention_cost.png`, `evaluate_reduction_mw.png` under `ml/reports/figures/action_engine/`.

---

## 6. Validation — 32/32 tests passed

Covers: no action for safe feeders; high-risk and overload triggers both correctly initiate action; each resource type individually verified feasible; insufficient-flexibility honestly reported (both magnitude- and duration-limited failure modes); resource constraints never violated; projected load/utilization/overload status independently cross-checked against direct `stress_engine.py` calls; action never produces negative or increased load; fully deterministic across repeated calls; lowest-cost solution preferred among multiple feasible options; all required output fields present and finite.

---

## 7. Limitations

1. **Binary (all-or-nothing) resource deployment** — no continuous/partial-magnitude optimization; a future version could search over partial deployments.
2. **Duration-vs-magnitude distinction remains unresolved** — as before, `remaining_overload_mw`/`required_reduction_mw` are magnitude-only summaries and can understate a purely duration-limited failure (see `DURATION_LIMITED` and `HIGH_RISK_NO_OVERLOAD` above); `overload_avoided` (derived from the real modified trajectory via `stress_engine.time_to_overload`) remains the authoritative signal.
3. **Actions always dispatch at the trajectory's first hour** — no model of delaying dispatch to better align a resource's active window with when peak stress actually occurs; this directly causes the `HIGH_RISK_NO_OVERLOAD` and `DURATION_LIMITED` failure cases above.
4. **All resource assumptions are synthetic** — restated per this task's explicit requirement; never validated against real Panama grid-flexibility data.
5. **Not validated against real grid operators or control systems** — a decision-support simulation only.
6. **`load_scenario_from_rolling_results()`** (a helper for loading one real origin+feeder from `rolling_feeder_results.csv`) uses a chunked linear scan since that file is ~318 MB — adequate for occasional lookups, not optimized for bulk use across many origins.

## Files created / changed

- **Rewritten:** [ml/src/action_engine.py](../src/action_engine.py) (previous prototype, built for the now-superseded interpolated-trajectory pipeline, replaced)
- **Created:** [ml/src/evaluate_action_engine.py](../src/evaluate_action_engine.py)
- **Rewritten:** [ml/tests/test_action_engine.py](../tests/test_action_engine.py)
- **Created:** [ml/reports/action_engine_report.md](action_engine_report.md) (this document), `ml/reports/action_engine_evaluation_summary.json`, `ml/data/action_engine_evaluation_results.csv`, 3 plots under `ml/reports/figures/action_engine/`

**Not modified:** any trained model, `regime_detector.py`, `robust_hourly_forecast.py`, `feeder_generator.py`, `stress_engine.py`, `rolling_integration.py`, backend, frontend, Gemini integration, or database.
