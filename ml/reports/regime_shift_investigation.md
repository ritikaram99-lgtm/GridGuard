# GridGuard AI — Regime-Shift Investigation: Seasonal Comparison, External Timeline, Data Integrity

**Script:** [ml/src/regime_shift_investigation.py](../src/regime_shift_investigation.py)
**Raw output:** [ml/reports/regime_shift_investigation_raw.json](regime_shift_investigation_raw.json)
**Source:** `ml/data/raw/continuous dataset.csv` (read-only, never modified)
**Scope:** diagnostic only. **No retraining, no feature-pipeline changes, no architecture changes.**

This follows up on [regime_shift_analysis.md](regime_shift_analysis.md), which found the model's test-period performance collapse is concentrated in March–June 2020 and confirmed as an observed temporal discontinuity, with causal attribution to COVID explicitly left open pending external evidence. This report gathers that evidence.

---

## 1. Historical seasonal comparison (March–June, 2017 vs. 2018 vs. 2019 vs. 2020)

### Descriptive statistics, `nat_demand`

| Year | n | mean | median | std | min | max |
|---|---|---|---|---|---|---|
| 2017 | 2,928 | 1207.07 | 1198.57 | 191.28 | 380.59 | 1629.53 |
| 2018 | 2,928 | 1221.50 | 1211.50 | 188.64 | 846.71 | 1635.54 |
| 2019 | 2,928 | 1265.11 | 1253.90 | 190.42 | 871.50 | 1719.04 |
| **2020** | 2,833 | **1117.91** | **1103.46** | **140.47** | 821.85 | 1676.19 |

2017–2019 show a stable, gently rising trend (mean ~1207 → ~1265 MW, consistent with organic demand growth). **2020 breaks that trend: mean demand drops ~9% below the 2017–2019 average, and — notably — the standard deviation drops too (140 vs. ~190 in prior years), meaning 2020 wasn't just lower, it was also flatter/less variable.** A lower minimum is not present (2020's min of 822 MW is in fact higher than 2017's min of 381 MW — that 2017 low is a separate historical low unrelated to this comparison).

### Weekday vs. weekend

| Year | Weekday mean | Weekend mean | Weekday − Weekend |
|---|---|---|---|
| 2017 | 1241.83 | 1117.10 | 124.73 |
| 2018 | 1258.63 | 1129.20 | 129.43 |
| 2019 | 1302.41 | 1176.00 | 126.41 |
| **2020** | **1140.68** | **1059.31** | **81.37** |

The weekday/weekend gap — normally a stable ~125–129 MW across 2017–2019 — **shrinks to 81 MW in 2020 (a ~35% reduction in the gap itself)**. This is a distinctive signature: it's not just "less demand," it's demand that behaves *less like a normal workweek*, consistent with reduced commercial/office activity blurring the weekday/weekend distinction.

### Average demand by hour of day

See [avg_demand_by_hour_by_year.png](figures/regime_shift/avg_demand_by_hour_by_year.png). 2017–2019 hourly curves are nearly on top of each other (a consistent double-hump daytime pattern). **The 2020 curve visibly sits below all three prior years across every daytime hour, while the overnight hours (00:00–06:00) are much closer to prior years** — the gap opens during commercial/working hours and narrows overnight.

### Monthly average demand

| Month | 2017 | 2018 | 2019 | 2020 |
|---|---|---|---|---|
| March | 1201.1 | 1217.4 | 1238.6 | 1209.0 |
| April | 1213.9 | 1229.0 | 1277.9 | **1062.0** |
| May | 1212.5 | 1217.3 | 1277.9 | **1088.2** |
| June | 1200.8 | 1222.6 | 1266.6 | **1109.3** |

**March 2020 is close to, or even in line with, prior years (1209 vs. 1201–1239).** The sharp drop begins in **April** (1062, down from a 1214–1278 range in prior years) and persists through May and June. See [monthly_avg_demand_by_year.png](figures/regime_shift/monthly_avg_demand_by_year.png).

### Daily-mean overlay and representative week

[daily_mean_demand_overlay.png](figures/regime_shift/daily_mean_demand_overlay.png) shows the four years' daily-mean series aligned by day-since-March-1. 2020 tracks closely with 2017–2019 through roughly the first 3–4 weeks of the window, then visibly separates downward and stays separated for the rest of the window — it does not oscillate back up to the prior-years' band. [representative_week_overlay.png](figures/regime_shift/representative_week_overlay.png) shows the same divergence at hourly resolution for one representative week.

**Is 2020 an obvious departure from prior years? Yes.** The pattern (later onset within March, sharp April drop, persistent through June, flattened weekday/weekend and daytime/nighttime contrast) is not present in 2017, 2018, or 2019, which track each other closely.

---

## 2. External COVID-19 timeline for Panama (March 2020)

Verified via web search against Wikipedia's "COVID-19 pandemic in Panama" article, a U.S. Embassy Panama City health alert, and OSAC (U.S. government Overseas Security Advisory Council) health alerts on Panama.

| Date | Event |
|---|---|
| 2020-03-09 | First confirmed COVID-19 case in Panama (arrived via Tocumen International Airport) |
| 2020-03-13 | Panama declares a national state of emergency (US$50M allocated for 180 days) |
| 2020-03-18 | Nationwide curfew announced (9:00 p.m.–5:00 a.m.), effective same day |
| 2020-03-19 | Suspension of all incoming commercial flights announced (effective 2020-03-22) |
| 2020-03-22 | International commercial passenger flights suspended |
| 2020-03-25 | **Nationwide movement restrictions ("quarantine") enacted** — time-windowed essential-activity access based on national ID digit |
| 2020-03-26 | Nationwide suspension of domestic commercial/charter flights |
| (later, exact date not confirmed by sources consulted) | Gender-based movement restriction system introduced (alternating days by gender) |

Sources:
- [COVID-19 pandemic in Panama — Wikipedia](https://en.wikipedia.org/wiki/COVID-19_pandemic_in_Panama)
- [Health Alert – U.S. Embassy Panama City, Panama (March 19, 2020)](https://pa.usembassy.gov/health-alert-u-s-embassy-panama-city-panama-march-19-2020/)
- [Health Alert: Panama, Increased Movement Restrictions, COVID-19 Situation Report, and Reminders — OSAC](https://www.osac.gov/Content/Report/21a7fe84-accc-4f34-8e2c-18942b7eded9)
- [Health Alert: Panama, Updated Regional and Nationwide COVID-19 Restrictions — OSAC](https://www.osac.gov/Country/Panama/Content/Detail/Report/0cdbf25b-dff7-44e9-a722-1a9dd9f34de8)

**These sources were not cross-verified against a primary Panamanian government source (e.g. Ministry of Health / Gaceta Oficial) or WHO/World Bank data directly** — they are secondary/reporting sources (Wikipedia, a U.S. Embassy alert, and OSAC advisories), which is a limitation of this verification, not a primary-source confirmation. School/business closure dates specifically were not found with a confirmed date in the sources consulted (Wikipedia's article did not include this detail).

### Temporal coincidence check (facts only, no causal claim yet)

- The nationwide quarantine took effect **2020-03-25**, in the final week of March.
- The seasonal comparison above shows March 2020 demand was close to prior years, with the sharp, sustained drop appearing in **April 2020 data** — i.e., in the first full month *after* the quarantine took effect, not before it.
- This ordering (restriction date precedes the month in which the largest demand drop appears) is consistent with the restrictions preceding, rather than following, the observed demand change.

---

## 3. Quantifying the 2020 shift vs. 2017–2019

**Overall (March–June):**
- 2017–2019 average: 1231.23 MW
- 2020: 1117.91 MW
- **Absolute difference: −113.32 MW**
- **Percentage difference: −9.20%**

**By day type:**

| | 2017–2019 avg | 2020 | Abs. diff | % diff |
|---|---|---|---|---|
| Weekday | 1267.39 MW | 1140.68 MW | −126.71 MW | −10.00% |
| Weekend | 1141.33 MW | 1059.31 MW | −82.02 MW | −7.19% |

**By hour (selected; full table in raw JSON and [pct_diff_by_hour_2020_vs_baseline.png](figures/regime_shift/pct_diff_by_hour_2020_vs_baseline.png)):**

| Hour | % diff (2020 vs. 2017–2019 avg) |
|---|---|
| 04:00 | −1.1% |
| 06:00 | −4.7% |
| 08:00 | −12.1% |
| 11:00 | **−17.0%** (largest deviation) |
| 14:00 | −15.7% |
| 17:00 | −12.5% |
| 20:00 | −6.5% |
| 23:00 | −1.7% |

**The demand reduction is heavily concentrated in working/business hours (roughly 08:00–18:00, peaking around 11:00 at −17%), and nearly absent overnight (00:00–05:00, within ~1–3%).** Weekday demand fell further than weekend demand, and the normal weekday/weekend gap itself compressed by about a third. This hour-of-day and day-type pattern — commercial/daytime demand suppressed, residential/nighttime demand largely intact — is the specific shape one would expect from business/office closures and reduced commuting, rather than from a generic across-the-board change (e.g. it does not look like a uniform sensor recalibration or a pure weather effect, which would not selectively hit business hours).

---

## 4. Data integrity check, March–June 2020

All checks performed only on this window, without modifying any data:

| Check | Result |
|---|---|
| Missing values (any column) | **0** |
| Duplicate timestamps | **0** |
| Duplicate rows | **0** |
| Expected hourly timestamps vs. actual rows | 2,833 expected, 2,833 actual — **0 gaps** |
| Sampling frequency | 100% of intervals are exactly 1 hour (`all_deltas_1h: true`) |
| Impossible values (`nat_demand` ≤ 0) | **0** |
| `nat_demand` range in window | 821.85–1676.19 MW (within the full series' plausible range) |
| Outliers vs. full-series 3×IQR fence | **0** — no 2020 Mar–Jun value is an outlier relative to the entire 2015–2020 series |
| Weather variable ranges (2020 Mar–Jun vs. full series) | Within the same min/max/mean/std envelope as the full series for all 12 weather columns — no sign of sensor/format change |

**Largest single-day jump in the daily-mean series:** +179.4 MW on 2020-03-09 (from 1147.2 MW on 2020-03-08 to 1326.6 MW). Investigated directly: **2020-03-08 was a Sunday and 2020-03-09 was a Monday** — this is an ordinary weekend→weekday step-up (consistent with the weekday/weekend gaps quantified in Section 1/3), not a data anomaly, and it happens to coincide with the date of Panama's first confirmed case only by calendar accident (the jump direction is *upward*, opposite to the demand-suppression pattern under investigation).

**No missingness, duplication, gaps, impossible values, outliers, sampling changes, or abrupt unexplained level shifts were found in the March–June 2020 window.** The demand reduction observed is not attributable to a data-quality artifact based on these checks.

---

## 5. Conclusion

**Classification: B — Clear 2020 regime shift with plausible COVID/restriction timing.**

Reasoning, separating observed facts from hypothesis:

**Observed facts:**
- 2020 March–June demand is ~9.2% below the 2017–2019 average for the same months, with a distinct hour-of-day and day-type shape: the reduction concentrates in daytime/business hours (up to −17%) and weekdays, while overnight and weekend demand are comparatively close to prior years.
- 2017, 2018, and 2019 track each other closely across every metric checked (mean, std, hourly shape, monthly pattern, weekday/weekend gap) — 2020 is the outlier among four comparable years, not just year-over-year noise.
- The sharpest drop appears in April 2020, immediately following documented major restrictions (state of emergency 2020-03-13, curfew 2020-03-18, nationwide quarantine 2020-03-25) that took effect in the second half of March 2020.
- No data-integrity issue (missingness, duplication, gaps, impossible values, outliers, sampling changes) was found in the March–June 2020 window that could otherwise explain the shift.

**Hypothesis (plausible but not proven by this dataset alone):**
- The timing and shape (daytime/commercial suppression, weekday/weekend blurring) are consistent with the behavioral effects of COVID-19 restrictions (business closures, reduced commuting, quarantine measures). This is a **plausible interpretation supported by temporal coincidence and a mechanistically consistent pattern**, not a proven causal claim — this dataset contains no COVID case counts, mobility indices, or business-closure records to directly link cause and effect, and the external sources consulted were secondary reporting rather than primary Panamanian government data.

This is not "insufficient evidence" (E) because the seasonal comparison and integrity check together rule out ordinary seasonality and data artifacts as the primary explanation, and it is not "possible data-quality issue" (D) because the integrity checks found nothing. It is not "mostly ordinary seasonal variation" (A) because 2017–2019 show no comparable divergence from each other. It goes beyond "cause remains unclear" (C) in that the timing, magnitude, and specific daytime/weekday shape of the shift line up coherently with documented restriction dates — but it stops short of a confirmed causal claim, hence "plausible COVID/restriction timing" rather than "confirmed."

---

## Summary

### 1. Key findings
- 2020 March–June demand is ~9.2% (−113 MW average) below the 2017–2019 average for the same months; 2017–2019 track each other closely, so 2020 is a clear outlier among comparable years.
- The reduction is concentrated in daytime/business hours (up to −17% around 11:00) and weekdays; overnight and weekend demand are comparatively close to prior years, and the normal weekday/weekend gap shrank by about a third.
- The sharpest drop occurs in April 2020 (not March), immediately after major restrictions took effect in late March 2020.
- No data-integrity issues were found in the March–June 2020 window.

### 2. Evidence for/against COVID-related disruption
**For:** timing (sharp drop follows, not precedes, documented restriction dates), magnitude and shape consistent with reduced commercial/commuting activity (daytime and weekday suppression, overnight/weekend relatively spared), and 2020 being an outlier against three internally-consistent prior years.
**Against / not established:** no direct COVID variable (cases, mobility, business-closure records) is present in this dataset to confirm mechanism; external sources used were secondary (Wikipedia, embassy/OSAC advisories), not primary Panamanian government data; some other unidentified 2020-specific factor cannot be fully ruled out from this dataset alone.

### 3. Evidence for/against ordinary seasonality
**Against ordinary seasonality:** 2017, 2018, and 2019 show a stable, mutually consistent seasonal pattern (mean, std, hourly shape, monthly trend, weekday/weekend gap all similar); 2020 diverges from all three on every one of these measures, which is not what "ordinary year-to-year seasonal variation" would look like among four comparable years.

### 4. Data-quality concerns
None identified for March–June 2020: zero missing values, zero duplicates, zero timestamp gaps, consistent hourly sampling, no impossible values, no outliers relative to the full 2015–2020 series, and weather-variable ranges consistent with the full series. The one large single-day jump found (2020-03-09) is an ordinary Sunday→Monday step, not an anomaly.

### 5. Recommendation for the forecasting model
Do not retrain yet (per scope), but the evidence supports treating the model's COVID-onset-period weakness as a **known, documented limitation stemming from a real, external demand-regime change** rather than a modeling defect to be tuned away. Practical next steps to consider (still no action taken here): (a) evaluate whether a regime/anomaly-aware approach (e.g., a flag feature or separate handling for detected regime shifts) is warranted before any retraining, (b) if retraining is eventually pursued, ensure validation/test design accounts for the possibility of future regime shifts rather than assuming stationarity, and (c) if available, incorporate mobility or policy-indicator data as a future feature source to make such shifts detectable in real time rather than only in hindsight.
