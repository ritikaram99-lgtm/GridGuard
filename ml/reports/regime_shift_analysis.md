# GridGuard AI — Regime-Shift Diagnostic (Pre-COVID vs. COVID-Onset Test Periods)

**Script:** [ml/src/regime_shift_analysis.py](../src/regime_shift_analysis.py)
**Raw output:** [ml/reports/regime_shift_diagnostic_raw.json](regime_shift_diagnostic_raw.json)
**Scope:** read-only diagnostic. Loads the already-saved `ml/models/demand_xgboost.pkl` and the already-saved `ml/data/processed/test.csv` only. **No retraining, no changes to the model, feature engineering, dataset, or any other code.**

Before running, the script re-verifies that the loaded model's `feature_names` match `model_metadata.json`'s recorded feature list, and that the two periods below partition the existing test set exactly (no overlap, no rows added or dropped).

---

## Period definitions (exact)

| Period | Origin date range | Rows |
|---|---|---|
| Pre-COVID | 2020-01-01 00:00:00 → 2020-02-29 23:00:00 | 1,440 |
| COVID-onset | 2020-03-01 00:00:00 → 2020-06-26 00:00:00 | 2,809 |
| (Full test, for reference) | 2020-01-01 00:00:00 → 2020-06-26 00:00:00 | 4,249 |

1,440 + 2,809 = 4,249 — the two periods exactly partition the full test set.

---

## 1. Metrics by period

| Period | Model | MAE (MW) | RMSE (MW) | MAPE (%) |
|---|---|---|---|---|
| Pre-COVID | Persistence baseline | 84.89 | 126.08 | 6.56 |
| Pre-COVID | XGBoost | 50.30 | 69.63 | 3.82 |
| COVID-onset | Persistence baseline | 56.31 | 86.15 | 5.00 |
| COVID-onset | XGBoost | 68.31 | 94.31 | 6.11 |
| Full test (reference) | Persistence baseline | 65.99 | 101.46 | 5.53 |
| Full test (reference) | XGBoost | 62.21 | 86.73 | 5.33 |

## 2. XGBoost improvement over persistence baseline, by period

| Period | MAE improvement | RMSE improvement | MAPE improvement |
|---|---|---|---|
| Pre-COVID | **+40.7%** | +44.8% | +41.7% |
| COVID-onset | **−21.3%** | −9.5% | −22.2% |
| Full test (reference) | +5.7% | +14.5% | +3.5% |

A negative value means XGBoost is **worse than the naive persistence baseline** on that metric/period.

**Pre-COVID performance (40.7% / 44.8% / 41.7% MAE/RMSE/MAPE improvement) is closely in line with the validation-set improvement reported in `model_evaluation.md` (46.1% / 52.4% / 44.2%).** COVID-onset performance is not just weaker — XGBoost actually **underperforms** the persistence baseline on every metric in that window. The blended full-test figure (+5.7% MAE) is a weighted average that masks a large, real split: a strongly positive pre-COVID result dragged down by a negative COVID-onset result.

## 3. Error-pattern breakdowns by period

### Hour of day (mean absolute error, XGBoost)

| Hour | Pre-COVID MAE | COVID-onset MAE |
|---|---|---|
| 00 | 55.2 | 36.5 |
| 03 | 39.0 | 30.4 |
| 06 | 39.3 | 31.1 |
| 09 | 39.4 | 107.1 |
| 10 | 51.1 | 126.1 |
| 12 | 56.4 | 111.0 |
| 14 | 80.7 | 116.3 |
| 15 | 69.4 | 116.9 |
| 18 | 46.5 | 67.0 |
| 21 | 48.7 | 43.1 |
| 23 | 46.0 | 39.0 |

(Full 24-hour table in the raw JSON.) In both periods, overnight hours (00–07) have the lowest error and daytime hours have the highest — consistent with the original full-test finding. But the **magnitude of the daytime peak roughly doubles** in the COVID-onset period: pre-COVID peaks around 81 MW (14:00), while COVID-onset peaks around 126 MW (10:00) and stays above 100 MW from roughly 10:00 to 15:00. Overnight-hour error is actually *lower* in the COVID-onset period than pre-COVID (e.g. hour 0: 55.2 vs 36.5), so the degradation is concentrated specifically in daytime hours, not uniform across the day.

### Weekday vs. weekend (mean absolute error, XGBoost)

| Period | Weekday MAE | Weekend MAE |
|---|---|---|
| Pre-COVID | 49.1 | 53.2 |
| COVID-onset | 77.6 | 43.6 |

This is a notable reversal: pre-COVID, weekend error is slightly *higher* than weekday error. In the COVID-onset period, this flips sharply — weekday error (77.6) becomes much larger than weekend error (43.6), and weekend error even improves relative to pre-COVID. The original full-test finding ("weekday errors clearly larger than weekend") is therefore driven almost entirely by the COVID-onset period, not a stable property of the whole test set.

### Demand tercile (mean absolute error, XGBoost)

Two tercile definitions are reported: period-specific terciles (each period split into its own low/mid/high thirds) and fixed terciles (using the full test set's demand edges, so "high" means the same MW range in both periods).

**Period-specific terciles:**

| Period | Low | Mid | High |
|---|---|---|---|
| Pre-COVID | 31.1 | 50.6 | 69.2 |
| COVID-onset | 46.6 | 86.2 | 72.2 |

**Fixed (full-test) terciles:**

| Period | Low | Mid | High |
|---|---|---|---|
| Pre-COVID | 27.8 | 40.1 | 61.2 |
| COVID-onset | 51.4 | 90.6 | 60.4 |

Pre-COVID error is **monotonically increasing** with demand level (low < mid < high) under both tercile definitions — the intuitive pattern. COVID-onset error is **not monotonic** — the mid tercile has the highest error in both definitions, exceeding even the high tercile. This confirms the original full-test observation ("errors are not simply a function of demand magnitude, mid tercile is highest") is specifically a COVID-onset-period phenomenon, not a general pre-COVID property.

---

## 4. Is the reduced overall test improvement concentrated in March–June 2020?

**Yes — this is directly and quantitatively confirmed, not merely plausible.** The pre-COVID period alone shows XGBoost improvement (40.7% MAE, 44.8% RMSE, 41.7% MAPE) closely matching the validation-set result. The COVID-onset period alone shows XGBoost *losing* to the naive persistence baseline on every metric (−21.3% MAE, −9.5% RMSE, −22.2% MAPE). The weak blended full-test number (+5.7% MAE) is arithmetically explained by averaging a strong positive result over 1,440 rows with a negative result over 2,809 rows — it is not an intermediate, uniformly-mediocre performance across the whole test window.

All three previously-identified error patterns (hour-of-day concentration, weekday-worse-than-weekend, non-monotonic demand-tercile error) are present in the COVID-onset period specifically, and are weaker or reversed in the pre-COVID period. This further supports that a single, temporally-localized change in the underlying data around March 2020 is the dominant driver of the test-set weaknesses reported in `model_evaluation.md`, rather than a general property of 2020 data or of the model architecture.

## 5. Regime-shift hypothesis: supported, partially supported, or not supported

**Supported, as an observed temporal regime difference — not yet as a causal COVID attribution.**

What the data supports directly:
- A clear, large, and consistent behavioral discontinuity in model performance and error structure exists between the Jan–Feb 2020 and Mar–Jun 2020 windows of the test set.
- This discontinuity is coincident with the calendar period in which COVID-19 restrictions are widely reported to have begun in Panama (March 2020).

What the data does **not**, by itself, establish:
- That COVID-19 (as opposed to some other coincident factor — e.g. a data-collection change, a different seasonal effect, an unrelated demand event) is the cause. This dataset contains no COVID-related variable (case counts, mobility indices, lockdown-order dates), so causal attribution to COVID specifically would require external evidence (e.g. published Panamanian lockdown timelines, independent demand/mobility data for the same window) that is outside this dataset and was not consulted here.

**Conclusion: an observed regime shift around March 2020 is confirmed by the data; attributing it specifically to COVID-19 is a plausible but unverified interpretation pending external evidence.**

---

## Recommendation

**(C) Investigate another issue first — before any retraining or architecture change.**

Reasoning: the model isn't just "somewhat weaker" in the COVID-onset window — it actively underperforms a trivial persistence baseline there, which is a more serious and specific problem than the blended full-test metric suggested. Before making a targeted model improvement (option B), the underlying cause of the March 2020 discontinuity should be confirmed using evidence external to this dataset (e.g., cross-checking against known Panama lockdown/restriction dates, or comparing against demand in the same calendar months of prior years to rule out an ordinary seasonal effect rather than a one-off shock). Retraining or otherwise adjusting the model now, without that confirmation, risks fitting to a temporary anomaly or misdiagnosing a data issue as a genuine long-term regime change. No such investigation, retraining, or architecture change has been performed as part of this task, per the instructions.
