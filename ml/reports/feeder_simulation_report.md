# GridGuard AI — Synthetic Feeder Simulation & Grid Stress Engine

**Scripts:** [ml/src/feeder_generator.py](../src/feeder_generator.py), [ml/src/stress_engine.py](../src/stress_engine.py)
**Tests:** [ml/tests/test_feeder_simulation.py](../tests/test_feeder_simulation.py) — 45/45 passing
**Example output:** [ml/reports/feeder_example_output.json](feeder_example_output.json)

**This stage does not retrain the XGBoost model or modify the feature pipeline** ([build_features.py](../src/build_features.py), [train_xgboost.py](../src/train_xgboost.py)). The saved model (`ml/models/demand_xgboost.pkl`) is loaded read-only and its existing 24h-ahead national forecast is *consumed* as an input to the feeder simulator.

---

## ⚠️ Why synthetic feeders are necessary (and what that means)

The Panama dataset (`ml/data/raw/continuous dataset.csv`, verified in the [dataset audit](dataset_audit.md)) contains only **national aggregate** electricity demand — one number per hour for the entire country. It has **no feeder-, substation-, or location-level measurements**, and no real Panama distribution-grid topology, feeder capacities, or voltage data exist anywhere in this project.

GridGuard's architecture, however, needs feeder-level stress detection. To bridge that gap without real feeder data, this stage builds an explicitly **synthetic feeder simulation layer**: a documented, reproducible, mathematical allocation of the real national demand signal down to 10 invented feeders (`F01`–`F10`), each with an invented profile, location, and capacity.

**This is a simulation for building and testing the GridGuard pipeline end-to-end — not real Panama feeder telemetry.** Every feeder id, name, location, load value, capacity, and voltage value produced by `feeder_generator.py` is synthetic. This is stated in the module's docstring, printed in example output (`SYNTHETIC_DATA_WARNING` field), and repeated here so it cannot be missed or later presented as real measured data.

---

## 1. Feeder profiles

10 synthetic feeders, 5 types, each with a documented qualitative load-shape (see `_RAW_HOURLY_SHAPE` in `feeder_generator.py`):

| Type | Documented behavior |
|---|---|
| `RESIDENTIAL` | Low overnight, small morning bump, strong evening peak (18:00–21:00) |
| `COMMERCIAL` | Very low overnight, strong daytime plateau (09:00–17:00), much lower on weekends |
| `INDUSTRIAL` | Relatively flat, high demand around the clock; mild weekday bias |
| `MIXED` | Arithmetic average of RESIDENTIAL and COMMERCIAL shapes — an intermediate behavior, as specified |
| `EV_HEAVY` | Elevated overnight (managed/scheduled charging) plus a strong evening peak (18:00–22:00, post-commute charging) |

These are hand-authored, illustrative shapes reflecting widely-known qualitative demand behavior for each customer class. **They are not fit to any measured Panama feeder data — none exists.**

### The 10 feeders

| ID | Name | Type | Location (simulated) | Relative weight | Capacity margin |
|---|---|---|---|---|---|
| F01 | Panama City Residential North | RESIDENTIAL | 9.05, -79.52 | 1.2 | 1.25 |
| F02 | San Miguelito Residential | RESIDENTIAL | 9.03, -79.50 | 1.0 | 1.20 |
| F03 | Panama City Commercial Core | COMMERCIAL | 8.98, -79.53 | 1.4 | 1.15 |
| F04 | Costa del Este Business Park | COMMERCIAL | 9.00, -79.48 | 1.1 | 1.20 |
| F05 | Colon Free Zone Industrial A | INDUSTRIAL | 9.36, -79.90 | 1.8 | 1.15 |
| F06 | Panama Pacifico Industrial B | INDUSTRIAL | 8.92, -79.60 | 1.6 | 1.10 |
| F07 | Arraijan Mixed Suburban | MIXED | 8.95, -79.66 | 1.0 | 1.25 |
| F08 | La Chorrera Mixed Fringe | MIXED | 8.88, -79.78 | 0.8 | 1.30 |
| F09 | Via Espana EV Corridor | EV_HEAVY | 8.99, -79.52 | 0.6 | 1.10 |
| F10 | Tocumen EV Depot | EV_HEAVY | 9.07, -79.38 | 0.4 | 1.05 |

**Locations are simulated/demo coordinates near Panama for map-display purposes only** — each carries a `location.note` field stating this explicitly and it is unit-tested (`test_locations_documented_as_simulated`). **`capacity_margin`** is the headroom multiplier used to size each feeder's capacity (Section on Capacity below); **F10's margin (1.05) is deliberately tight** — a documented scenario-design choice so at least one feeder naturally exercises HIGH/CRITICAL stress in examples and tests, not a claim about a real overloaded feeder.

Feeders are **not identical except for noise**: types, relative weights, capacity margins, and hourly/day-type shapes all differ meaningfully (asserted in tests).

---

## 2. National-to-feeder allocation methodology

For feeder *i* at time *t*:

```
raw_i(t)  = national_demand(t) x base_share_i x shape_i(hour(t)) x daytype_i(is_weekend(t))
load_i(t) = max(raw_i(t) x (1 + eps_i(t)), 0)
```

- **`base_share_i`**: feeder *i*'s share of `COVERAGE_FACTOR` (= 5% of national demand, an arbitrary, documented, easily-changed "10-feeder pilot deployment" assumption — not a real feeder count), proportional to `relative_weight_i`. `sum(base_share_i) == COVERAGE_FACTOR` exactly (tested).
- **`shape_i(hour)`**: the feeder type's 24-hour load shape, normalized so its mean over 24 hours is exactly 1.0.
- **`daytype_i`**: a weekday/weekend multiplier pair, hand-chosen for the weekday value and then *solved* for the weekend value so that `(5/7)*weekday + (2/7)*weekend = 1.0` — i.e., the time-weighted weekly average of the day-type multiplier is exactly 1.0 by construction.
- **`eps_i(t)`**: independent, reproducible, bounded noise per feeder — `Normal(0, 0.05)` clipped to `[-0.20, 0.20]`, drawn from a per-feeder RNG stream seeded as `seed + feeder_index + 1`.

**Why this guarantees the aggregate tracks the national signal:** because `shape_i` has mean 1.0 over 24 hours and `daytype_i` has a weighted-mean of 1.0 over a week, the product `shape_i(hour) x daytype_i(daytype)` has an expected value of exactly 1.0 averaged over **any full 7-day window**. Therefore:

```
E[ sum_i load_i(t) over a full week ] = sum_i(base_share_i) x mean(national_demand over that week)
                                        = COVERAGE_FACTOR x mean(national_demand over that week)
```

This is verified directly in tests (`test_aggregate_feeder_demand_tracks_national_signal_weekly`, tolerance 2%, and `..._with_noise`, tolerance 5%). Hour-to-hour, the aggregate is **not** a fixed fraction of national demand — different feeder types peak at different hours, so the aggregate has its own texture — but it converges to `COVERAGE_FACTOR x national_demand` on average, which is the intended, documented behavior (not a bug).

**Feeder load always depends on the national signal, hour of day, day of week, and feeder type** — never generated as an independent random value per feeder (verified by `test_feeder_load_depends_on_national_demand_level` and `test_feeder_load_varies_by_hour_and_type`).

**Non-negativity**: `national_demand >= 0`, `base_share_i >= 0`, `shape_i > 0`, `daytype_i > 0`, and `(1 + eps_i)` is clipped to `[0.80, 1.20]` (always positive) — so `raw_i(t) >= 0` always, and the `max(..., 0)` clamp is a defensive backstop, not load-bearing. Verified directly (`test_feeder_loads_non_negative`).

**Reproducibility**: fixed `SEED = 42` (module-level default, overridable per call); identical seeds produce bit-identical output (`test_allocation_is_reproducible`); the noise-free allocation (used for forecasts) is deterministic by construction.

---

## 3. Feeder forecast trajectories

For each feeder, per horizon step: **current load, capacity, forecast load, utilization, and voltage** are provided (see `run_example()` output format).

### ⚠️ Forecast trajectory resolution limitation (read before using)

The saved XGBoost model was trained and evaluated for a **single fixed 24-hour-ahead horizon** ([model_evaluation.md](model_evaluation.md)) — it produces **exactly one forecast point per origin timestamp**, not a per-hour trajectory for hours 1–23.

To still provide an hourly-resolution trajectory for feeder/stress-engine purposes, `build_national_trajectory()` constructs an **engineered interpolation**: it anchors exactly to the real current value at h=0 and the real single XGBoost forecast at h=24 (both real, model-derived numbers), and fills in hours 1–23 using the **historical average diurnal demand shape** purely as an interpolation curve — not as additional model predictions. Because the horizon is exactly 24 hours, h=0 and h=24 fall on the same hour-of-day, which makes this a clean shape-preserving blend (see the function's docstring for the exact formula).

**This must never be described as "the model forecasts hour-by-hour."** It is a documented visualization/simulation convenience built from one real data point and one real model output, shaped by history — not independent predictions at each intermediate hour. Feeder-level trajectories are then this national trajectory allocated deterministically (no fresh noise — forecasts use expected values, not injected randomness) via the same allocation formula as Section 2, per feeder.

### Voltage model (explicitly simulated, not measured)

```
voltage_pu = clip(1.02 - 0.10 x max(utilization - 0.5, 0) + noise, 0.85, 1.05)
```

A simplified linear approximation: no drop below 50% utilization, then a linear sag above it, plus small Gaussian noise (`std=0.003`). This is **loosely inspired by qualitative distribution-feeder voltage-drop behavior under load** — it is not a power-flow simulation and not measured data. Documented in `VOLTAGE_MODEL` in `feeder_generator.py`; every value it produces is clearly synthetic.

---

## 4. Capacity assignment

```
capacity_mw_i = capacity_margin_i x max(historical synthetic load_i)
```

Each feeder's capacity is sized from the **maximum value in its own historical synthetic allocation** (2015–2020, the full raw dataset range), scaled up by its `capacity_margin` (documented per-feeder in Section 1, range 1.05–1.30). This guarantees capacity always exceeds the historical peak (tested: `test_capacity_exceeds_historical_max`) while keeping some feeders (notably F10, margin 1.05) close enough to their historical ceiling to realistically approach or exceed capacity under above-average conditions — which is the point of the simulation (testing the stress engine against varied scenarios), not a claim about real infrastructure limits.

---

## 5. Grid Stress Engine ([stress_engine.py](../src/stress_engine.py))

**Deterministic and rule-based — not a machine-learning model.** No training, no fitted parameters, no hidden state; every constant is a plain, editable module-level value.

### Stress score formula

```
score = 100 x [ w1 x current_utilization
              + w2 x forecast_utilization
              + w3 x trajectory_slope
              + w4 x voltage_stress
              + w5 x headroom ]
```

| Component | Weight | Definition (all clipped to [0,1]) |
|---|---|---|
| `current_utilization` | 0.35 | `current_load / capacity` |
| `forecast_utilization` | 0.30 | `forecast_load_24h / capacity` |
| `trajectory_slope` | 0.15 | `(forecast_load - current_load) / capacity` — rising trajectories add risk; flat/falling contribute 0 |
| `voltage_stress` | 0.10 | 0 at/above 0.95 pu, 1 at/below 0.90 pu, linear between |
| `headroom` | 0.10 | `1 - (capacity - current_load) / capacity` — less spare capacity = more stress |

Weights sum to 1.0 (asserted at import time). **All weights are plain constants in `STRESS_WEIGHTS` at the top of the module — change a number and re-run, no retraining involved anywhere.**

### Risk classification

| Score | Level |
|---|---|
| 0–30 | LOW |
| 31–60 | MODERATE |
| 61–80 | HIGH |
| 81–100 | CRITICAL |

**These are initial engineering thresholds chosen for interpretability and demonstration — not scientifically validated against real grid-reliability or outage data** (none exists in this project). They should be calibrated against real outage/overload history before any operational use. This caveat is stated in the module docstring, not just here.

---

## 6. Time-to-overload methodology

`time_to_overload(trajectory, capacity_mw)` scans an hourly trajectory for the first point at/above capacity, then **linearly interpolates** between the last sub-capacity point and the first at/over-capacity point to estimate a crossing time.

**Resolution limitation, stated directly in the function's return value (`resolution_note`) as well as here:** the underlying national demand trajectory is only available at hourly resolution (Section 3) — the interpolation gives an **hour-level estimate** (± roughly 1 hour), **not** a minute-level or sub-hourly-accurate prediction, because the model behind it was never evaluated at sub-hourly resolution.

**Worked illustrative example** (constructed to demonstrate the mechanism — not a feeder scenario claim): a trajectory linearly rising from 50 MW to 150 MW over 24 hourly points against a 100 MW capacity is correctly detected as crossing at **h=12.0** (test: `test_overload_detected_when_trajectory_crosses_capacity`).

**Real (synthetic-data) example** — feeder F10 (Tocumen EV Depot) at its historical peak allocation, `2020-01-17 20:00:00` (an evening EV-charging peak hour):

| Field | Value |
|---|---|
| Current load | 5.15 MW |
| Capacity | 5.76 MW (margin 1.05) |
| Current utilization | 89.5% |
| Forecast load (24h) | 3.95 MW (next day, same hour, national demand was lower) |
| Stress score | **60.84** |
| Risk level | **HIGH** |
| Overload predicted | No (forecast trajectory declines, doesn't cross capacity) |

This shows the engine correctly flagging a near-full feeder as HIGH even though the specific forecast doesn't cross capacity in that instance — `current_utilization` (weight 0.35) and `headroom` (weight 0.10) dominate the score here, not the forecast/slope terms.

---

## 7. Assumptions and limitations (summary)

- **All feeder data is synthetic** — ids, names, locations, loads, capacities, and voltages. No real Panama feeder measurements exist in or were used by this project.
- `COVERAGE_FACTOR = 0.05` (10 feeders ≈ 5% of national demand) is an arbitrary, documented "pilot" assumption, easily changed.
- Hourly load shapes per feeder type are hand-authored from general domain knowledge of customer-class behavior, not fit to any measured data.
- Forecast trajectories beyond the model's single real 24h-ahead point are an **engineered interpolation** using historical diurnal shape, not independent per-hour model predictions.
- Voltage is a simplified linear approximation, not a power-flow simulation or measured value.
- Stress-score weights and LOW/MODERATE/HIGH/CRITICAL thresholds are **initial, uncalibrated engineering choices**, explicitly flagged as needing validation against real outage/reliability data before operational use.
- Time-to-overload crossing estimates are accurate only to roughly hourly resolution, inherited from the underlying model's evaluated horizon.

## 8. Reproducibility

- `SEED = 42` (module default in `feeder_generator.py`, passed explicitly through every call in this report/tests).
- Per-feeder noise uses independent RNG streams (`np.random.default_rng(seed + feeder_index + 1)`), so results are bit-identical across runs with the same seed and change predictably if the seed changes.
- Forecast-trajectory allocation is fully deterministic (no noise injected into forward-looking values).
- Verified directly: `test_allocation_is_reproducible`, `test_different_seeds_give_different_noise`, `test_no_noise_allocation_is_deterministic_and_matches_formula`.

---

## Test results

```
ml/tests/test_feeder_simulation.py — 45 passed in 5.06s
```

Covers: reproducibility, non-negativity, no NaN/inf across the full pipeline (allocation → capacity → trajectory → voltage → stress score → classification → time-to-overload), aggregate-vs-national tracking (weekly, with and without noise), feeder-load dependence on national demand/hour/day-type, capacity sizing, stress-score bounds and monotonicity, all four classification boundaries (including invalid-input rejection), overload detection (rising/flat/already-over trajectories), and an end-to-end run through the real saved model + real feeder pipeline with an exhaustive finite/non-negative check on every output field.
