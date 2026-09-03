# GridGuard AI — Genuine Hourly (t+1h..t+24h) Demand Forecasting Model

**Scripts:** [ml/src/train_hourly_xgboost.py](../src/train_hourly_xgboost.py), [ml/src/hourly_forecast.py](../src/hourly_forecast.py)
**Model artifacts:** [ml/models/hourly_demand_xgboost.pkl](../models/hourly_demand_xgboost.pkl), [ml/models/hourly_model_metadata.json](../models/hourly_model_metadata.json)
**Per-horizon metrics:** `ml/data/hourly_forecast_per_horizon_metrics.csv`

This model **replaces the previous approach of interpolating** a single 24h-ahead forecast against a historical diurnal shape (`feeder_generator.build_national_trajectory`) **with genuine, independent XGBoost predictions for every hour t+1 through t+24.** The existing 24h model (`ml/models/demand_xgboost.pkl`) is preserved completely unmodified, as instructed — this is a new, separate model, not a replacement of it in place.

---

## Approach

A **single XGBoost model** with an explicit `forecast_horizon` feature (1–24), as specified. Each training row is one `(origin time t, horizon h)` pair:
- **Target:** `nat_demand` at `t + h`
- **Origin-time features** (37 columns — demand lags, rolling stats, origin + 24h-lagged weather, origin calendar): identical in *definition* to `build_features.py`'s origin-time features, but reimplemented independently in this new pipeline (per instructions, `build_features.py` itself was not touched). These depend only on information available at or before `t`, so they are leakage-safe **for every horizon simultaneously** — none of them depend on `h`.
- **`forecast_horizon`** (1 column): the horizon itself, 1–24.
- **Target-time calendar features** (13 columns — hour/day/month/weekend + cyclical encodings + holiday/school, evaluated at `t+h`): deterministic calendar facts about a future timestamp, known arbitrarily far in advance — the same rationale already used and justified in `build_features.py` for the single-horizon model.
- **No target-time weather** is used anywhere — real weather forecasts are not available in this dataset, so including `t+h` weather would mean using actual future weather, not a realistic forecast input (same rationale as `build_features.py`).

**Total: 51 features.** Dataset: 47,856 valid origins (same 168h warm-up + 24h tail-truncation window as `build_features.py`) × 24 horizons = **1,148,544 rows**, split chronologically at the same boundaries as the existing 24h model (train ≤2018, val=2019, test=2020 H1), so a given origin's 24 rows always fall entirely within one split.

## Leakage / integrity validation — all passed

| Check | Result |
|---|---|
| Every horizon 1–24 present | **True** |
| `target_datetime == origin_datetime + forecast_horizon` (all rows) | **True** |
| No duplicate (origin, horizon) rows | **True** |
| No NaN/inf in features or target | **True** |
| No target-time weather features present | **True** |
| Max origin lookback bounded at 168h | **True** |
| Sampled `lag_1h_nat_demand` matches manual lookup | **True** |
| Chronological, non-overlapping train/val/test splits | **True** |
| Saved model's `feature_names` match `hourly_model_metadata.json` exactly | **True** |

**Genuineness check:** for a sample test-set origin, the 24 predictions were compared against a naive linear interpolation between the h=0 actual and the h=24 prediction (i.e., what the *old* interpolation approach would have produced). Maximum absolute difference: **414.6 MW** — the predictions clearly follow real intra-day demand structure (a dip overnight, a sharp morning ramp, an evening peak) rather than a straight line, confirming these are genuine independent per-horizon model outputs, not interpolation. Each of the 24 predictions for a given origin used a distinct `forecast_horizon` input value (verified directly).

Hyperparameters: `n_estimators=500` (best iteration 355, early-stopped on validation MAE), `max_depth=7`, `learning_rate=0.05`, `subsample/colsample_bytree=0.8`, `min_child_weight=5`, `random_state=42`. Training took 23.8s for 836K rows.

---

## Metrics by horizon

### Validation set (2019 — in-distribution, no known regime shift)

| Horizon | Model MAE | Baseline MAE | Improvement |
|---|---|---|---|
| 1h | 35.6 | 46.5 | **+23.4%** |
| 6h | 40.2 | 209.8 | **+80.9%** |
| 12h | 43.4 | 277.2 | **+84.3%** (peak) |
| 18h | 46.0 | 222.0 | **+79.3%** |
| 24h | 46.8 | 79.6 | **+41.2%** |

**The model beats the persistence baseline at all 24 of 24 horizons on validation**, by wide margins (23–84%). This confirms the underlying modeling approach is fundamentally sound in-distribution.

### Test set (2020 H1 — includes the previously documented COVID-19 regime shift)

| Horizon | Model MAE | Baseline MAE | Improvement |
|---|---|---|---|
| **1h** | 81.5 | 38.1 | **−113.8%** (worst) |
| 2h | 82.2 | 69.8 | −17.9% |
| 3h | 83.7 | 97.7 | +14.3% |
| 12h | 88.5 | 197.3 | **+55.2%** (best MAE-improvement horizon) |
| 22h | 87.0 | 99.2 | +12.3% |
| 23h | 86.9 | 79.4 | −9.5% |
| **24h** | 86.9 | 66.0 | **−31.7%** |

**The model beats baseline at 20 of 24 horizons on test, but underperforms it at both extremes: h=1, 2, 23, 24.** Full 24-row table in `ml/data/hourly_forecast_per_horizon_metrics.csv`. See [mae_by_horizon.png](figures/hourly_forecast/mae_by_horizon.png), [rmse_by_horizon.png](figures/hourly_forecast/rmse_by_horizon.png), [mape_by_horizon.png](figures/hourly_forecast/mape_by_horizon.png), [model_vs_baseline_by_horizon.png](figures/hourly_forecast/model_vs_baseline_by_horizon.png).

**Best horizon (lowest test MAE):** h=1 (81.5 MW) — but this is misleading in isolation, since the baseline is far better there (see below).
**Worst horizon (highest test MAE):** h=10 (88.7 MW).
**Best horizon by improvement-over-baseline:** h=12 (+55.2%).
**Worst horizon by improvement-over-baseline:** h=1 (−113.8%).

---

## Root-cause investigation: two distinct, separable findings

### Finding 1 — a genuine structural weakness at h=1 (present even without any regime shift)

Splitting the test period into **pre-COVID (Jan–Feb 2020)** and **COVID-onset (Mar–Jun 2020)**, using the same methodology as [regime_shift_analysis.md](regime_shift_analysis.md):

| Horizon | Pre-COVID improvement | COVID-onset improvement |
|---|---|---|
| 1h | **−16.3%** | **−178.7%** |
| 2h | +36.6% | −54.8% |
| 3h | +53.8% | −12.7% |
| 12h | +78.7% | +34.5% |
| 22h | +50.8% | −15.4% |
| 23h | +39.6% | −46.1% |
| 24h | +28.7% | **−78.4%** |

**Even in the "clean" pre-COVID period, the model underperforms the baseline at h=1** (−16.3%), while beating it comfortably everywhere else (h=2–24: +29% to +79%). This is confirmed by **feature importance**: `forecast_horizon` ranks **42nd of 51 features** (importance 0.0008) and `lag_0h_nat_demand` — the single most relevant feature for very-short-horizon accuracy — ranks similarly low (0.0040). The top features are almost entirely target-time calendar signals (`target_is_weekend` 32.3%, `target_hour_of_day` 20.6%, `target_hour_cos` 10.5%, `target_day_of_week` 9.5%, `target_holiday_flag` 7.7%).

**Root cause:** training a single model on 24 pooled horizons with unweighted squared-error loss lets the calendar/seasonal signal — which explains the most *aggregate* variance across all horizons combined — dominate tree splits, at the expense of the recency signal that specifically matters at short horizons (where the achievable baseline error is already tiny, so there is little pooled-loss incentive for the model to chase it). This is a known, documented pitfall of naively pooling multi-horizon regression targets, not a data leakage issue — every leakage check above passed.

### Finding 2 — the model is *more* exposed to the known COVID regime shift than a persistence baseline

Comparing pre-COVID vs. COVID-onset directly: the model's advantage over baseline **shrinks or reverses across nearly every horizon** during COVID-onset, and the failure zone **expands** from just h=1 (pre-COVID) to h=1–3 *and* h=22–24 (COVID-onset). This is the same phenomenon already documented for the original 24h model in [regime_shift_analysis.md](regime_shift_analysis.md) and [regime_shift_investigation.md](regime_shift_investigation.md) — a real, external 2020 demand-regime change, plausibly (not confirmed) related to COVID-19 restrictions, that this model (trained only on 2015–2018) had no way to see coming. Because this hourly model leans even more heavily on calendar/seasonal features (Finding 1) than the original 24h model did, it is plausibly *more* exposed to a period where the "typical calendar-based expectation" diverges sharply from reality — the persistence baseline, by contrast, directly tracks whatever the actual (suppressed) current level is, which is inherently more robust to this kind of shift, especially at short and long horizons.

**These are two separable findings, not one:** Finding 1 (h=1 weakness) would exist regardless of COVID; Finding 2 (regime-shift amplification) is layered on top of it and is responsible for most of the h=23-24 and much of the added h=2-3 weakness specifically in the test period.

---

## Comparison with the existing 24h model

The existing single-horizon model ([model_evaluation.md](model_evaluation.md)) achieved **+5.7% MAE improvement** over baseline on the full 2020 test set at h=24 specifically (its only horizon). This new model's h=24 test performance is **−31.7%** — noticeably worse at that specific horizon, on the same test period. This is a genuine regression for h=24 specifically, and is consistent with Finding 2: the original 24h model's top features were more balanced between calendar (`target_hour_of_day`, `target_day_of_week`) and recency (`lag_0h_nat_demand` ranked #2) than this pooled model's, which may make the original somewhat more robust at exactly the horizon it was purpose-built and evaluated for. The new model's real advantage is that it usefully covers h=1–23 (which the old model could not forecast at all, only interpolate), and outperforms baseline substantially across the middle of that range even during COVID-onset (e.g., h=12: +34.5% during COVID-onset).

---

## Plots

Saved under `ml/reports/figures/hourly_forecast/`:

- [mae_by_horizon.png](figures/hourly_forecast/mae_by_horizon.png), [rmse_by_horizon.png](figures/hourly_forecast/rmse_by_horizon.png), [mape_by_horizon.png](figures/hourly_forecast/mape_by_horizon.png) — model vs. baseline, all 24 horizons, test set
- [model_vs_baseline_by_horizon.png](figures/hourly_forecast/model_vs_baseline_by_horizon.png) — % MAE improvement by horizon
- [24h_forecast_example.png](figures/hourly_forecast/24h_forecast_example.png) — one full 24h genuine forecast vs. actual vs. naive linear interpolation (illustrating the genuineness check)
- [actual_vs_predicted_example2.png](figures/hourly_forecast/actual_vs_predicted_example2.png) — a second, randomly chosen example origin

---

## Limitations

1. **h=1 underperforms baseline even without any regime shift** (Finding 1) — a structural consequence of pooled multi-horizon training with unweighted loss, not a leakage bug. Candidate fixes not implemented here (would require a decision before further work): horizon-weighted loss, per-horizon sample weighting, an explicit `lag_0h × forecast_horizon` interaction feature, or a small ensemble of horizon-bucket-specific models.
2. **The model is more exposed to the 2020 regime shift than the original 24h model or the trivial baseline**, especially at the horizon extremes (Finding 2) — inherited from, not independent of, the limitation already documented for the underlying data/regime in earlier reports.
3. **h=24 specifically regresses relative to the existing, separately-trained 24h model** on the same test period (−31.7% vs. +5.7%) — the two models should not be assumed interchangeable at that horizon without further comparison.
4. **No target-time weather** is used (by design, matching the existing model's rationale) — this may leave useful predictive signal on the table at all horizons, unrelated to the regime-shift issue.
5. This model is **not yet wired into `feeder_generator.py` or `rolling_integration.py`** — per scope, this stage only builds and validates the standalone hourly forecasting component. `ml/src/hourly_forecast.py` provides a clean inference API (`predict_hourly_trajectory`) ready for that integration once a decision is made on how to address Findings 1–2.

## Files created

- [ml/src/train_hourly_xgboost.py](../src/train_hourly_xgboost.py)
- [ml/src/hourly_forecast.py](../src/hourly_forecast.py)
- [ml/models/hourly_demand_xgboost.pkl](../models/hourly_demand_xgboost.pkl)
- [ml/models/hourly_model_metadata.json](../models/hourly_model_metadata.json)
- `ml/data/hourly_forecast_per_horizon_metrics.csv`
- [ml/reports/hourly_forecast_evaluation.md](hourly_forecast_evaluation.md) (this document)
- 6 plots under `ml/reports/figures/hourly_forecast/`

**Not modified:** `stress_engine.py`, `feeder_generator.py`, `rolling_integration.py`, `build_features.py`, `train_xgboost.py`, `ml/models/demand_xgboost.pkl`, or `ml/data/processed/*` — all preserved exactly as they were.
