# GridGuard AI — Feature Engineering Report

**Source:** `ml/data/raw/continuous dataset.csv` (read-only, unmodified — verified in the [dataset audit](dataset_audit.md))
**Script:** [ml/src/build_features.py](../src/build_features.py)
**Task:** 24-hour-ahead hourly national demand forecasting (feature prep only — no model training)

---

## Bug fix: raw `datetime` column excluded from model features

An earlier version of this pipeline computed an internal `datetime` column (identical to `origin_datetime`, used only for an internal leakage self-check) but did not add it to `non_feature_columns`. As a result it was incorrectly included in `feature_metadata.json`'s `feature_columns` list and would have been usable as a raw pandas `Timestamp` feature — a bookkeeping bug, not a future-information leak (its value at row `t` never exceeds `t`), but harmful for a fair evaluation: coerced to a numeric epoch, it would hand the model an absolute-time signal that trivially separates train (≤2018) / val (2019) / test (2020) periods without reflecting any real predictive relationship, undermining generalization.

**Fix applied:** `"datetime"` added to `non_feature_columns` in `build_features.py` (both the metadata dict and the actual `feature_cols` list computed from `feat_clean.columns`), and the full pipeline was regenerated. No other feature-engineering logic was changed.

**Post-fix verification (all passed):**
1. `"datetime"` not present in `feature_columns` ✓
2. `"origin_datetime"` not present in `feature_columns` ✓
3. No object/datetime-dtype column present among feature columns in `train.csv`/`val.csv`/`test.csv` ✓
4. Target remains `target_nat_demand_t_plus_24h` ✓
5. Row counts and split date boundaries unchanged (34,847 / 8,760 / 4,249; same boundaries as before) ✓
6. Target horizon remains exactly 24h for all rows ✓
7. Maximum feature lookback remains 168 hours ✓
8. No new missing values or duplicate rows/timestamps introduced ✓

Final feature count: **50** (was 51 before the fix, i.e. exactly one column — the redundant `datetime` — removed).

---

## Target definition

**Target column:** `target_nat_demand_t_plus_24h`
**Definition:** `nat_demand` value at `origin_datetime + 24 hours`, where `origin_datetime` is the forecast origin (the "now" of each row).

Each row represents standing at time `t` and forecasting demand at `t+24h`. The target is excluded from the feature set at model-training time (see Leakage checks).

## Feature groups (50 feature columns total — full descriptions in `feature_metadata.json`)

| Group | Columns | Notes |
|---|---|---|
| **Demand lags** | `lag_0h`, `lag_1h`, `lag_24h`, `lag_48h`, `lag_168h_nat_demand` | Values known at or before origin `t`. `lag_168h` = same hour, 1 week prior. |
| **Demand rolling stats** | `roll_mean_24h`, `roll_std_24h`, `roll_mean_168h`, `roll_std_168h_nat_demand` | Trailing windows ending at (and including) `t`; `min_periods=window` so no partially-filled window is used. |
| **Weather (origin)** | `origin_{T2M,QV2M,TQL,W2M}_{toc,san,dav}` (12 cols) | Actual reading at `t`, known at prediction time. |
| **Weather (24h lag)** | `lag_24h_{T2M,QV2M,TQL,W2M}_{toc,san,dav}` (12 cols) | Same-hour-yesterday weather; captures short-term weather persistence. |
| **Calendar (target time)** | `target_hour_of_day`, `target_day_of_week`, `target_month`, `target_is_weekend`, `target_hour_sin/cos`, `target_dow_sin/cos`, `target_month_sin/cos` | Deterministic calendar arithmetic for `t+24h` — known arbitrarily far in advance. |
| **Holiday/school (target time)** | `target_holiday_id`, `target_holiday_flag`, `target_school_flag` | Looked up from the raw dataset's own calendar columns at `t+24h` — these are published-in-advance facts, not measurements. |
| **Calendar/holiday (origin time)** | `origin_hour_of_day`, `origin_day_of_week`, `origin_holiday_flag`, `origin_school_flag` | Context for the forecast origin itself. |

**Deliberate exclusion:** future (target-time) weather actuals are **not** used as features. This dataset only contains observed weather, not forecasts — including `t+24h` weather would leak the true future outcome rather than approximate a realistic forecast input. If real weather-forecast data becomes available later, that would be a separate, clearly-labeled feature source.

## Rows lost to lagging/horizon

| Cause | Rows lost |
|---|---|
| Warm-up for lag/rolling features (max lookback = 168h) | 168 (start of series) |
| Undefined target beyond raw data horizon (24h shift) | 24 (end of series) |
| **Total** | **192** |

Raw rows: 48,048 → Final feature rows after `dropna()`: **47,856**. No imputation, forward-fill, or back-fill was used across these boundaries — rows with any undefined feature or target are dropped outright, which is the safer choice to avoid introducing information from outside the valid observation window.

## Chronological train / validation / test split

No shuffling — split purely by `origin_datetime` to preserve temporal order and prevent look-ahead bias.

| Split | Date range (origin) | Rows |
|---|---|---|
| **Train** | 2015-01-10 01:00 → 2018-12-31 23:00 | 34,847 |
| **Validation** | 2019-01-01 00:00 → 2019-12-31 23:00 | 8,760 |
| **Test** | 2020-01-01 00:00 → 2020-05-26 23:00 (data ends 2020-06-27, minus 24h horizon) | 4,249 |

Split boundaries were chosen as full calendar years (train ≤ 2018, val = 2019, test = 2020 onward) for interpretability and to keep at least one full year in validation and test. Verified non-overlapping and strictly increasing in time (train max < val min < test min).

## Leakage checks performed (all passed)

1. **Target excluded from feature columns** — `target_nat_demand_t_plus_24h` is not in the feature list used for modeling.
2. **Manual spot-check** — a sampled row's `lag_1h_nat_demand` matches a direct lookup of `nat_demand` at `origin_datetime - 1h`.
3. **Chronological ordering** — train/val/test each verified monotonically increasing in `origin_datetime`.
4. **Non-overlapping, ordered splits** — `train.max(origin_datetime) < val.min(origin_datetime)` and `val.max(origin_datetime) < test.min(origin_datetime)`.
5. **Horizon consistency** — `target_datetime - origin_datetime == 24h` for every row, with no exceptions.
6. **Lookback bound** — maximum feature lookback is 168h (7 days); no feature reaches further back than the data supports, enforced via `min_periods=window` on rolling stats and natural `NaN` propagation on lags (rows dropped rather than filled).

## Outputs

| File | Description |
|---|---|
| `ml/data/processed/features_full.csv` | Full 47,856-row feature table (all splits combined, chronological) |
| `ml/data/processed/train.csv` | Chronological train split (34,847 rows) |
| `ml/data/processed/val.csv` | Chronological validation split (8,760 rows) |
| `ml/data/processed/test.csv` | Chronological test split (4,249 rows) |
| `ml/data/processed/feature_metadata.json` | Machine-readable description of every feature (name, definition, source columns, leakage note), split boundaries, row-loss accounting, and leakage-check results |

## Next step (not started — pending approval)

Baseline model training (e.g. XGBoost) on `train.csv`, tuned/selected against `val.csv`, with `test.csv` held out for final evaluation only. Still out of scope: synthetic feeders, risk scoring, backend/frontend, Gemini integration.
