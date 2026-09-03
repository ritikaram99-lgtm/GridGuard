# GridGuard AI — Model Evaluation: 24-Hour-Ahead Demand Forecast

**Script:** [ml/src/train_xgboost.py](../src/train_xgboost.py)
**Model artifact:** [ml/models/demand_xgboost.pkl](../models/demand_xgboost.pkl)
**Metadata:** [ml/models/model_metadata.json](../models/model_metadata.json)
**Data used:** only the verified processed files (`ml/data/processed/{train,val,test}.csv`), no re-derivation of features here.

---

## Pre-training input verification

Before fitting, the script asserts (not just checks-and-continues — these are hard `assert`s that would halt the run):

- Model input has **exactly 50 feature columns**, in the exact order recorded in `feature_metadata.json`.
- None of `datetime`, `origin_datetime`, `target_datetime`, `target_nat_demand_t_plus_24h` are present among the feature columns.
- All 50 feature columns are numeric (no raw timestamp/object dtype columns).
- No missing values in `X_train` / `X_val` / `X_test`.

All assertions passed — `X_train` (34,847, 50), `X_val` (8,760, 50), `X_test` (4,249, 50).

## Post-training verification

After saving `demand_xgboost.pkl`, the script reloads it from disk and checks the booster's `feature_names` and the sklearn wrapper's `feature_names_in_` against the recorded `feature_metadata.json` feature list. **Both matched exactly, in the same order.**

---

## 1. Persistence baseline

`prediction(t+24) = nat_demand(t)`

| Split | MAE (MW) | RMSE (MW) | MAPE (%) |
|---|---|---|---|
| Validation (2019) | 79.63 | 125.85 | 6.56 |
| Test (2020 H1) | 65.99 | 101.46 | 5.53 |

## 2. XGBoost

**Hyperparameters** (fixed, sensible baseline config — no large search; selected best iteration via early stopping on the validation set):

```json
{
  "n_estimators": 500,
  "max_depth": 6,
  "learning_rate": 0.05,
  "subsample": 0.8,
  "colsample_bytree": 0.8,
  "min_child_weight": 5,
  "reg_lambda": 1.0,
  "reg_alpha": 0.0,
  "objective": "reg:squarederror",
  "eval_metric": "mae",
  "random_state": 42,
  "early_stopping_rounds": 30,
  "best_iteration": 120
}
```

Training used `train.csv` only; `val.csv` was used exclusively for early stopping (best iteration = 120 of 500, selected by validation MAE); `test.csv` was touched only for final evaluation below, never for tuning.

| Split | MAE (MW) | RMSE (MW) | MAPE (%) |
|---|---|---|---|
| Validation (2019) | 42.91 | 59.93 | 3.66 |
| Test (2020 H1) | 62.21 | 86.73 | 5.33 |

## 3. Relative improvement over persistence baseline

| Split | MAE improvement | RMSE improvement | MAPE improvement |
|---|---|---|---|
| Validation | 46.1% | 52.4% | 44.2% |
| Test | 5.7% | 14.5% | 3.5% |

**XGBoost beats the persistence baseline on both splits, on all three metrics — but the margin is much smaller on test than on validation.** This gap is a genuine finding, not noise (see Weaknesses below): the test period (2020-01-01 to 2020-06-26) includes the onset of COVID-19 restrictions in Panama (~March 2020), which is a known real-world demand-pattern shift not represented anywhere in the training data (2015–2018) or validation data (2019). The persistence baseline, which simply tracks whatever the demand level currently is, is naturally more robust to this kind of regime shift than a model trained on pre-shift patterns — which narrows XGBoost's advantage on test even though it still wins.

---

## 4. Error analysis (test set, 2020 H1)

### Plots

- [Actual vs predicted — representative 14-day period](figures/actual_vs_predicted_period.png)
- [Actual vs predicted — full single week](figures/actual_vs_predicted_week.png)
- [Residual distribution](figures/residual_distribution.png)
- [Predicted vs actual scatter](figures/predicted_vs_actual_scatter.png)

### Observed error patterns (test set only, mean absolute error)

**By demand level (terciles):**

| Demand tercile | Mean AE (MW) | n |
|---|---|---|
| Low | 47.1 | 1,417 |
| Mid | 78.6 | 1,416 |
| High | 60.9 | 1,416 |

Error is **not monotonic with demand level** — the mid tercile has the highest error, not the high tercile. This does not support a simple "errors grow with demand" narrative; the pattern is more consistent with errors being driven by *when* (see hour-of-day below) rather than purely *how much*.

**By weekend flag:**

| | Mean AE (MW) | n |
|---|---|---|
| Weekday | 68.2 | 3,048 |
| Weekend | 47.0 | 1,201 |

Weekday forecasts have clearly larger errors than weekend forecasts.

**By holiday flag:**

| | Mean AE (MW) | n |
|---|---|---|
| Non-holiday | 63.3 | 3,985 |
| Holiday | 45.2 | 264 |

Holidays have *smaller* mean error than regular days in this test set — the opposite of a naive "holidays are harder" assumption. This is plausible given holidays are flat, low-variance demand days, and is only reported because it's what the data shows.

**By target hour of day:**

Errors are strongly hour-dependent: overnight hours (02:00–06:00) have the lowest error (~32–34 MW), while midday/afternoon hours (09:00–16:00) have the highest (peaking at **104.2 MW at 14:00**). This lines up with weekday daytime demand being the most variable and hardest-to-time part of the daily cycle (ramp-up/ramp-down transitions), while overnight demand is flat and easy to predict.

**Summary of genuinely observed patterns:** errors are larger on weekdays, larger during daytime/midday hours, and smaller on holidays — not simply larger at high demand levels.

---

## 5. SHAP explainability

TreeExplainer applied to the final model, evaluated on the full test set (4,249 rows).

### Top 10 features by mean |SHAP value|

| Rank | Feature | Mean |SHAP| (MW) |
|---|---|---|
| 1 | `target_hour_of_day` | 73.18 |
| 2 | `lag_0h_nat_demand` | 42.47 |
| 3 | `target_day_of_week` | 32.53 |
| 4 | `target_hour_cos` | 14.10 |
| 5 | `roll_mean_168h_nat_demand` | 11.12 |
| 6 | `target_holiday_id` | 9.97 |
| 7 | `origin_hour_of_day` | 9.97 |
| 8 | `target_is_weekend` | 8.90 |
| 9 | `lag_168h_nat_demand` | 5.81 |
| 10 | `lag_48h_nat_demand` | 5.64 |

Plots: [global top-10 bar chart](figures/shap_feature_importance_top10.png), [SHAP summary (beeswarm) plot](figures/shap_summary_plot.png).

### What actually drives the model's forecasts

The model relies overwhelmingly on **calendar/time-of-day structure at the target hour** (`target_hour_of_day`, `target_day_of_week`, `target_hour_cos`, `target_is_weekend`) and **recent/weekly demand history** (`lag_0h_nat_demand`, `roll_mean_168h_nat_demand`, `lag_168h_nat_demand`, `lag_48h_nat_demand`). **No weather variable appears in the top 10.** This means, contrary to what the raw correlation analysis in the dataset audit might suggest (temperature correlated ~0.65 with same-hour demand), weather at the 24-hour horizon used here is **not among the model's most influential inputs** — the dominant signal is "what time/day is it" plus "what was demand recently," not temperature. This is stated only because SHAP shows it directly, not assumed in advance.

---

## Weaknesses discovered

1. **Test-period improvement is much smaller than validation-period improvement** (5.7% vs 46.1% MAE reduction). Most plausible explanation: the test window (Jan–Jun 2020) includes a real-world demand regime shift (COVID-19 onset in Panama, ~March 2020) not present in training/validation data — the model was not trained on any comparable disruption.
2. **Errors are concentrated in weekday daytime hours** (peak ~104 MW MAE at 14:00) — the model is noticeably worse at capturing intraday ramp behavior than at forecasting flat overnight demand.
3. **Weather features are not influential drivers** of this model's 24h-ahead predictions per SHAP, despite temperature's raw correlation with same-hour demand — the model leans on calendar + demand-history features instead. This may mean 24h-ahead weather signal is too noisy/indirect at this horizon, or that the lag/calendar features already capture most of what weather would explain.
4. **Error is not simply a function of demand magnitude** — the mid demand tercile has the highest error, which suggests transition periods, not high-load periods per se, are hardest for the model.

## Recommendation for next ML step

Given XGBoost beats the baseline on every metric on both splits — but the test-period margin is thin and concentrated in a demand-shock window — the recommended next step is **not** to move on to feeder-level/synthetic work yet. Instead: (a) inspect whether the test-period gap narrows or widens if evaluated on pre-COVID test months only (e.g. Jan–Feb 2020) vs. the COVID-onset months, to confirm the regime-shift hypothesis rather than assume it, and (b) if confirmed, treat this as a known, documented limitation of the current single-national-aggregate model rather than something to fix by hyperparameter tuning. Only after that diagnostic should broader scope (synthetic feeders, risk scoring, etc.) begin.
