# GridGuard AI — Dataset Audit

**Dataset:** Short-term electricity load forecasting (Panama case study)
**Source:** Mendeley Data, DOI [10.17632/byx7sztj59.1](https://data.mendeley.com/datasets/byx7sztj59/1)
**Author:** Ernesto Aguilar Madrid (Universidade Nova de Lisboa), published 2021-03-02
**License:** CC BY 4.0
**Verification:** Downloaded via the Mendeley public API (`public-api/datasets/byx7sztj59`), which returned the dataset name, DOI, and a `files[]` manifest with per-file IDs, sizes and content types. All 5 downloaded files match the manifest's declared sizes exactly (byte-for-byte), confirming they came from the specified dataset and version 1. Files were saved unmodified into `ml/data/raw/`.
**Primary file analyzed:** `ml/data/raw/continuous dataset.csv`

---

## A. What the dataset actually contains

Files downloaded into `ml/data/raw/` (unmodified):

| File | Size | Role |
|---|---|---|
| `continuous dataset.csv` | 10.5 MB | **Primary time series** — merged load, weather, and calendar data on a single datetime index |
| `weekly pre-dispatch forecast.csv` | 929 KB | CND's own official weekly load forecast (useful as a benchmark to beat, not a training feature) |
| `train_dataframes.xlsx` | 45.3 MB | Author-suggested 14 train/test split pairs, pre-built |
| `test_dataframes.xlsx` | 196 KB | Corresponding test splits |
| `Columns metadata and train-test splits details.pdf` | 2.5 MB | Author's column documentation and split methodology |

**`continuous dataset.csv` — verified structure (measured directly, not assumed from the description):**

- **Rows:** 48,048 (+1 header row)
- **Columns:** 17
- **Timestamp column:** `datetime`, format `YYYY-MM-DD HH:MM:SS` (e.g. `2015-01-03 01:00:00`), parses cleanly with no coercion errors
- **Sampling frequency:** confirmed hourly — 48,047 of 48,047 consecutive deltas are exactly `1:00:00`; `pandas.infer_freq` returns `h`
- **Time range:** `2015-01-03 01:00:00` → `2020-06-27 00:00:00` (2,001 days, ≈5.48 years)
- **Continuity:** the expected hourly range over this span contains exactly 48,048 timestamps — **actual row count matches exactly. Zero missing timestamps, zero gaps.**
- **Missing values:** 0 across all 17 columns (0.0% everywhere)
- **Duplicates:** 0 fully-duplicated rows, 0 duplicated timestamps

**Columns (dtypes as read):**

| Column | Dtype | Description |
|---|---|---|
| `datetime` | string → parsed to datetime | Hourly timestamp |
| `nat_demand` | float64 | **National electricity demand (target/load)**, units MW per author documentation |
| `T2M_toc`, `T2M_san`, `T2M_dav` | float64 | Temperature at 2m (°C) — Tocumen, Santiago, David |
| `QV2M_toc`, `QV2M_san`, `QV2M_dav` | float64 | Specific humidity at 2m |
| `TQL_toc`, `TQL_san`, `TQL_dav` | float64 | Liquid precipitable water |
| `W2M_toc`, `W2M_san`, `W2M_dav` | float64 | Wind speed at 2m |
| `Holiday_ID` | int64 | Categorical ID of specific holiday (0 = none; 22 distinct holiday IDs observed) |
| `holiday` | int64 (binary) | 1 on 3,024 hourly rows (126 days) |
| `school` | int64 (binary) | 1 on 34,969 rows, 0 on 13,079 rows (school-in-session flag) |

**Load (`nat_demand`) descriptive statistics:**

| Stat | Value (MW) |
|---|---|
| min | 85.19 |
| 25% | 1020.06 |
| median | 1168.43 |
| mean | 1182.87 |
| 75% | 1327.56 |
| max | 1754.88 |
| std | 192.07 |

**Anomalies found:**
- One extreme low-side outlier: `85.19 MW` at `2019-01-20 12:00:00`, far below the 3×IQR fence (`[97.5, 2250.1]`). This is a single isolated hour, not a sustained drop — plausibly a real event (outage/data artifact) rather than a sensor glitch, but warrants a labeled sanity check before training, not deletion.
- 49 hour-to-hour changes exceed the 99.9th-percentile jump threshold (~213 MW) — consistent with normal daily ramp-up/ramp-down behavior at this sample size, not a red flag on their own.
- No non-positive load values.

**Weather variables available:** temperature, specific humidity, liquid precipitable water, and wind speed, each measured at three cities (Tocumen, Santiago, David) — 12 weather columns total. No wind direction, solar irradiance, or humidity-as-percentage variant.

**Calendar variables available:** `Holiday_ID` (categorical), `holiday` (binary), `school` (binary, school-in-session). No explicit day-of-week or hour-of-day columns — these must be derived from `datetime` (trivial, done in the notebook).

**Correlation highlights:** `nat_demand` correlates most strongly with Tocumen temperature (`T2M_toc`, r≈0.65) and the other two temperature series (r≈0.63–0.65); weakly negative with `holiday`/`Holiday_ID` (r≈-0.13 to -0.17) as expected (holidays reduce demand); weak positive with `school` (r≈0.04).

## B. What variables are useful for forecasting

- `nat_demand` — the target.
- Temperature at all three stations — strongest exogenous correlate of demand (cooling load).
- `holiday` / `Holiday_ID` — clear demand-suppression signal.
- `school` — weak but real signal, worth including.
- Time-derived features (hour of day, day of week, month) — the notebook's hour-of-day and day-of-week plots show strong, regular within-day and within-week demand cycles, so these are cheap, high-value engineered features.
- Humidity and precipitation (`QV2M_*`, `TQL_*`) and wind speed (`W2M_*`) are weaker correlates individually but may add marginal value or interact with temperature.

## C. What's missing compared with the original GridGuard architecture

GridGuard's architecture needs feeder-level stress detection, not just national demand:

- **No feeder-level or substation-level data** — this dataset is a single national aggregate (`nat_demand`) with no geographic/feeder disaggregation, so it cannot directly support "detect future feeder overload" without a synthetic feeder-allocation step later.
- **No EV load, battery storage, or DER (distributed energy resource) data** — nothing to directly model EV load shifting or battery discharge effects; those would need to be simulated on top of this dataset.
- **No grid topology / capacity/rating data** (feeder limits, transformer ratings) — required for defining "overload" thresholds; not present here and must come from elsewhere or be synthesized.
- **No real-time/streaming granularity** — hourly only, no sub-hourly (e.g. 5/15-minute) resolution some overload-detection use cases might want.
- **No price/tariff data.**

These gaps are expected and out of scope for this stage — they'll be addressed in later phases (synthetic feeder generation, risk model), not now.

## D. Whether the dataset is suitable for short-term load forecasting

**Yes, well-suited**, with the caveat that it forecasts *national* demand, not feeder-level demand:

- 5.48 years of hourly data (48,048 rows) is ample for training and backtesting short-term (hour-ahead to week-ahead) forecasting models.
- Zero missing values, zero duplicate timestamps, and perfect hourly continuity mean essentially no cleaning/imputation burden — a rare and valuable property.
- Real exogenous weather and calendar variables (not proxies) are already merged and aligned to the same index.
- The dataset even ships an official benchmark (`weekly pre-dispatch forecast.csv`) — CND's own forecast — enabling direct model-vs-incumbent comparison.

## E. Limitations

- Single national aggregate — no spatial/feeder granularity (see C).
- One confirmed outlier (85.19 MW) needs inspection before training; not removed here per instructions.
- Weather data is NASA Earthdata reanalysis-derived (per author documentation), not ground-station observations — likely smoothed/interpolated rather than raw sensor readings.
- Data ends 2020-06-27 — over 5 years old; no COVID-period demand-shock labeling, and any deployed model would need retraining/validation against more recent data eventually (out of scope now).
- Only 3 weather stations for an entire country — coarse spatial resolution if finer regional modeling is later needed.

## F. What we should do next

1. Report these findings (this document) before any further implementation.
2. On approval, proceed to feature engineering only (hour/day/month extraction, lag features, rolling stats) — still no model training.
3. Decide the target column and forecasting horizon (see recommendations below) and get sign-off.
4. Only after that: baseline model training (e.g. XGBoost) on a held-out time-based split, using the author's suggested train/test splits (`train_dataframes.xlsx` / `test_dataframes.xlsx`) as a starting reference rather than re-deriving splits from scratch.

---

## Summary Answers

1. **Dataset summary:** Panama national hourly electricity demand, 2015-01-03 to 2020-06-27 (48,048 hourly rows, 17 columns), merged with temperature/humidity/precipitation/wind for 3 cities and holiday/school calendar flags. No missing values, no duplicates, perfectly continuous hourly series. One isolated low-value outlier.
2. **Recommended target column:** `nat_demand` (national demand, MW).
3. **Recommended forecasting horizon:** Given true hourly sampling and the CND operational cadence noted in the dataset's own methodology (72-hour unseen-data gap before each weekly forecast), a **24-hour-ahead to 7-day-ahead (168-hour) hourly forecast** is the natural fit — short-term enough to be actionable for feeder-stress prevention, long enough to allow preventive action (EV shifting, battery dispatch) to be planned. Start with 24h-ahead as the primary horizon and treat 168h as a stretch goal.
4. **Recommended initial features:** `nat_demand` lags (t-1, t-24, t-168), rolling means/std over 24h and 168h windows, hour-of-day, day-of-week, month, `holiday`, `Holiday_ID`, `school`, and temperature (`T2M_toc` at minimum, all three optionally).
5. **Data-quality problems:** essentially none structurally (zero missing/duplicate/gap); one isolated extreme-low outlier at `2019-01-20 12:00:00` (85.19 MW) that should be visually/manually reviewed before training, not silently dropped.
6. **Proceed with XGBoost?** Yes — this is a clean, dense tabular time series with strong exogenous features (temperature, calendar), which is exactly the regime where gradient-boosted trees (XGBoost/LightGBM) tend to perform very well and are fast to iterate on. Reasonable choice for a hackathon baseline; an LSTM/temporal model could be a later comparison, not a prerequisite.
7. **Exact next implementation step:** Build a feature-engineering script (`ml/src/build_features.py`) that derives the lag/rolling/calendar features above from `continuous dataset.csv` into `ml/data/processed/`, without touching the raw file — **do not start this until you confirm you want to proceed past the audit stage.**
