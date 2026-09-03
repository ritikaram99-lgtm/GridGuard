"""
GridGuard AI - Regime-shift investigation: historical seasonal comparison +
data integrity check for March-June 2020 vs. the same months in 2017-2019.

Source: ml/data/raw/continuous dataset.csv (read-only, never modified).
Does NOT retrain the model or touch the feature pipeline.
"""
import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

RAW_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "continuous dataset.csv")
FIG_DIR = os.path.join(os.path.dirname(__file__), "..", "reports", "figures", "regime_shift")
os.makedirs(FIG_DIR, exist_ok=True)

df = pd.read_csv(RAW_PATH)
df["datetime"] = pd.to_datetime(df["datetime"])
df = df.sort_values("datetime").reset_index(drop=True)

YEARS = [2017, 2018, 2019, 2020]

def mar_jun_slice(d, year):
    start = pd.Timestamp(f"{year}-03-01 00:00:00")
    end = pd.Timestamp(f"{year}-06-30 23:00:00")
    return d[(d["datetime"] >= start) & (d["datetime"] <= end)].copy()

slices = {y: mar_jun_slice(df, y) for y in YEARS}
for y, s in slices.items():
    print(f"{y}: {len(s)} rows, {s['datetime'].min()} -> {s['datetime'].max()}")

# ---------------------------------------------------------------------------
# 1. Descriptive statistics per year (Mar-Jun window)
# ---------------------------------------------------------------------------
print("\n" + "=" * 80)
print("1. Descriptive statistics, nat_demand, March-June by year")
print("=" * 80)

stats_rows = []
for y in YEARS:
    s = slices[y]["nat_demand"]
    stats_rows.append({
        "year": y,
        "n": len(s),
        "mean": s.mean(),
        "median": s.median(),
        "std": s.std(),
        "min": s.min(),
        "max": s.max(),
    })
stats_df = pd.DataFrame(stats_rows).set_index("year")
print(stats_df.round(2))

# weekday vs weekend
print("\nWeekday vs weekend mean nat_demand, March-June by year:")
wk_rows = []
for y in YEARS:
    s = slices[y].copy()
    s["is_weekend"] = s["datetime"].dt.dayofweek.isin([5, 6])
    weekday_mean = s.loc[~s["is_weekend"], "nat_demand"].mean()
    weekend_mean = s.loc[s["is_weekend"], "nat_demand"].mean()
    wk_rows.append({"year": y, "weekday_mean": weekday_mean, "weekend_mean": weekend_mean,
                     "weekday_minus_weekend": weekday_mean - weekend_mean})
wk_df = pd.DataFrame(wk_rows).set_index("year")
print(wk_df.round(2))

# ---------------------------------------------------------------------------
# 2. Average demand by hour of day, per year (Mar-Jun)
# ---------------------------------------------------------------------------
print("\n" + "=" * 80)
print("2. Average demand by hour of day, March-June, by year")
print("=" * 80)

hourly_by_year = {}
for y in YEARS:
    s = slices[y].copy()
    s["hour"] = s["datetime"].dt.hour
    hourly_by_year[y] = s.groupby("hour")["nat_demand"].mean()

hourly_table = pd.DataFrame(hourly_by_year)
print(hourly_table.round(1))

fig, ax = plt.subplots(figsize=(10, 5))
for y in YEARS:
    ax.plot(hourly_table.index, hourly_table[y], label=str(y), linewidth=2 if y == 2020 else 1.2)
ax.set_title("Average Demand by Hour of Day, March-June (2017-2020)")
ax.set_xlabel("Hour of day")
ax.set_ylabel("Avg nat_demand (MW)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "avg_demand_by_hour_by_year.png"), dpi=120)
plt.close(fig)

# ---------------------------------------------------------------------------
# 3. Monthly average demand, per year
# ---------------------------------------------------------------------------
print("\n" + "=" * 80)
print("3. Monthly average demand, March-June, by year")
print("=" * 80)

monthly_by_year = {}
for y in YEARS:
    s = slices[y].copy()
    s["month"] = s["datetime"].dt.month
    monthly_by_year[y] = s.groupby("month")["nat_demand"].mean()

monthly_table = pd.DataFrame(monthly_by_year)
monthly_table.index = ["March", "April", "May", "June"]
print(monthly_table.round(1))

fig, ax = plt.subplots(figsize=(8, 5))
monthly_table.plot(kind="bar", ax=ax)
ax.set_title("Monthly Average Demand, March-June (2017-2020)")
ax.set_ylabel("Avg nat_demand (MW)")
ax.legend(title="Year")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "monthly_avg_demand_by_year.png"), dpi=120)
plt.close(fig)

# ---------------------------------------------------------------------------
# 4. Full daily-mean time series overlay (Mar 1 - Jun 30, day-of-window x-axis)
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(14, 5))
for y in YEARS:
    s = slices[y].copy()
    daily = s.set_index("datetime")["nat_demand"].resample("D").mean()
    day_offset = (daily.index - daily.index[0]).days
    ax.plot(day_offset, daily.values, label=str(y), linewidth=2 if y == 2020 else 1.2)
ax.set_title("Daily Mean Demand, March-June (2017-2020), aligned by day-of-window")
ax.set_xlabel("Day since March 1")
ax.set_ylabel("Daily mean nat_demand (MW)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "daily_mean_demand_overlay.png"), dpi=120)
plt.close(fig)

# ---------------------------------------------------------------------------
# 5. One representative week overlay (first full Mon-Sun week of each March-June window)
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(14, 5))
for y in YEARS:
    s = slices[y].copy()
    s = s.set_index("datetime")
    # find first Monday on/after March 1
    first_monday = s.index[s.index.dayofweek == 0][0]
    week = s.loc[first_monday: first_monday + pd.Timedelta(days=7)]["nat_demand"]
    hours_offset = (week.index - first_monday).total_seconds() / 3600
    ax.plot(hours_offset, week.values, label=f"{y} (week of {first_monday.date()})", linewidth=2 if y == 2020 else 1.2)
ax.set_title("Representative Week (first full week of March), Hourly Demand by Year")
ax.set_xlabel("Hours since week start (Monday 00:00)")
ax.set_ylabel("nat_demand (MW)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "representative_week_overlay.png"), dpi=120)
plt.close(fig)

# ---------------------------------------------------------------------------
# 6. Quantify the 2020 shift vs. 2017-2019 average
# ---------------------------------------------------------------------------
print("\n" + "=" * 80)
print("6. Quantify 2020 vs. 2017-2019 average (March-June)")
print("=" * 80)

baseline_years = [2017, 2018, 2019]
baseline_concat = pd.concat([slices[y] for y in baseline_years])
mean_baseline = baseline_concat["nat_demand"].mean()
mean_2020 = slices[2020]["nat_demand"].mean()
abs_diff = mean_2020 - mean_baseline
pct_diff = abs_diff / mean_baseline * 100
print(f"Mean nat_demand, 2017-2019 avg (Mar-Jun): {mean_baseline:.2f} MW")
print(f"Mean nat_demand, 2020 (Mar-Jun):          {mean_2020:.2f} MW")
print(f"Absolute difference: {abs_diff:.2f} MW")
print(f"Percentage difference: {pct_diff:.2f}%")

# by hour
baseline_hourly = baseline_concat.assign(hour=baseline_concat["datetime"].dt.hour).groupby("hour")["nat_demand"].mean()
hourly_2020 = hourly_by_year[2020]
hourly_diff = hourly_2020 - baseline_hourly
hourly_pct_diff = hourly_diff / baseline_hourly * 100
print("\nBy hour (2020 minus 2017-2019 avg):")
hourly_compare = pd.DataFrame({"baseline_2017_19": baseline_hourly, "y2020": hourly_2020,
                                 "abs_diff": hourly_diff, "pct_diff": hourly_pct_diff})
print(hourly_compare.round(2))

# by day type (weekday/weekend)
baseline_concat["is_weekend"] = baseline_concat["datetime"].dt.dayofweek.isin([5, 6])
y2020 = slices[2020].copy()
y2020["is_weekend"] = y2020["datetime"].dt.dayofweek.isin([5, 6])

for label, is_we in [("weekday", False), ("weekend", True)]:
    b_mean = baseline_concat.loc[baseline_concat["is_weekend"] == is_we, "nat_demand"].mean()
    y_mean = y2020.loc[y2020["is_weekend"] == is_we, "nat_demand"].mean()
    d = y_mean - b_mean
    p = d / b_mean * 100
    print(f"{label}: 2017-2019 avg={b_mean:.2f} MW, 2020={y_mean:.2f} MW, diff={d:.2f} MW ({p:.2f}%)")

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(hourly_compare.index, hourly_compare["pct_diff"], marker="o")
ax.axhline(0, color="black", linewidth=1)
ax.set_title("2020 vs. 2017-2019 Average: % Difference in Demand by Hour (March-June)")
ax.set_xlabel("Hour of day")
ax.set_ylabel("% difference (2020 vs 2017-2019 avg)")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "pct_diff_by_hour_2020_vs_baseline.png"), dpi=120)
plt.close(fig)

# ---------------------------------------------------------------------------
# 7. Data integrity check specifically for March-June 2020
# ---------------------------------------------------------------------------
print("\n" + "=" * 80)
print("7. Data integrity check, March-June 2020")
print("=" * 80)

s2020 = slices[2020]
integrity = {}
integrity["n_rows"] = int(len(s2020))
integrity["missing_values_per_column"] = s2020.isna().sum().to_dict()
integrity["duplicate_timestamps"] = int(s2020["datetime"].duplicated().sum())
integrity["duplicate_rows"] = int(s2020.duplicated().sum())

expected_range = pd.date_range(start=s2020["datetime"].min(), end=s2020["datetime"].max(), freq="h")
missing_ts = expected_range.difference(s2020["datetime"])
integrity["expected_hourly_timestamps"] = int(len(expected_range))
integrity["actual_rows"] = int(len(s2020))
integrity["missing_timestamps_gaps"] = int(len(missing_ts))
integrity["missing_timestamps_list"] = [str(t) for t in missing_ts]

deltas = s2020["datetime"].diff().dropna()
integrity["all_deltas_1h"] = bool((deltas == pd.Timedelta(hours=1)).all())
integrity["delta_value_counts"] = {str(k): int(v) for k, v in deltas.value_counts().items()}

# impossible values
integrity["nat_demand_le_0"] = int((s2020["nat_demand"] <= 0).sum())
integrity["nat_demand_min"] = float(s2020["nat_demand"].min())
integrity["nat_demand_max"] = float(s2020["nat_demand"].max())

# outliers relative to the FULL series distribution (not just this window),
# to check if 2020 Mar-Jun contains unusual values relative to all history
full_q1, full_q3 = df["nat_demand"].quantile([0.25, 0.75])
full_iqr = full_q3 - full_q1
full_lower, full_upper = full_q1 - 3 * full_iqr, full_q3 + 3 * full_iqr
outliers_2020 = s2020[(s2020["nat_demand"] < full_lower) | (s2020["nat_demand"] > full_upper)]
integrity["outliers_vs_full_series_fence"] = {
    "fence": [float(full_lower), float(full_upper)],
    "n_outliers": int(len(outliers_2020)),
    "outlier_rows": outliers_2020[["datetime", "nat_demand"]].astype(str).to_dict(orient="records"),
}

# abrupt level shift detection: rolling 24h mean, look at biggest day-over-day jump
daily_mean_2020 = s2020.set_index("datetime")["nat_demand"].resample("D").mean()
daily_diff = daily_mean_2020.diff().dropna()
biggest_jump_date = daily_diff.abs().idxmax()
integrity["biggest_daily_mean_jump"] = {
    "date": str(biggest_jump_date),
    "jump_mw": float(daily_diff.loc[biggest_jump_date]),
    "mean_before": float(daily_mean_2020.loc[biggest_jump_date - pd.Timedelta(days=1)]),
    "mean_after": float(daily_mean_2020.loc[biggest_jump_date]),
}

# check whether other raw columns (weather, calendar) show sudden format/range changes
weather_cols = ["T2M_toc", "QV2M_toc", "TQL_toc", "W2M_toc", "T2M_san", "QV2M_san",
                 "TQL_san", "W2M_san", "T2M_dav", "QV2M_dav", "TQL_dav", "W2M_dav"]
weather_ranges_2020 = s2020[weather_cols].describe().T[["min", "max", "mean", "std"]]
weather_ranges_full = df[weather_cols].describe().T[["min", "max", "mean", "std"]]
print("\nWeather variable ranges, March-June 2020 vs full series:")
compare_weather = weather_ranges_2020.add_suffix("_2020_marjun").join(weather_ranges_full.add_suffix("_full_series"))
print(compare_weather.round(3))

print("\nIntegrity summary:")
print(json.dumps({k: v for k, v in integrity.items() if k not in ("missing_timestamps_list",)}, indent=2, default=str))

# ---------------------------------------------------------------------------
# 8. Daily mean demand plot for 2020 with a marker at the biggest jump / key dates
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(14, 4))
ax.plot(daily_mean_2020.index, daily_mean_2020.values, linewidth=1.2)
key_dates = {
    "2020-03-09 First case": "2020-03-09",
    "2020-03-13 State of emergency": "2020-03-13",
    "2020-03-18 Curfew begins": "2020-03-18",
    "2020-03-25 Nationwide quarantine": "2020-03-25",
}
for label, d in key_dates.items():
    ax.axvline(pd.Timestamp(d), color="red", linestyle="--", alpha=0.5)
    ax.text(pd.Timestamp(d), ax.get_ylim()[1], label, rotation=90, fontsize=7, va="top", ha="right", color="red")
ax.set_title("Daily Mean Demand, March-June 2020, with Documented COVID-19 Restriction Dates")
ax.set_ylabel("Daily mean nat_demand (MW)")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "daily_mean_2020_with_covid_dates.png"), dpi=120)
plt.close(fig)

# ---------------------------------------------------------------------------
# Save all numeric outputs
# ---------------------------------------------------------------------------
out = {
    "descriptive_stats_by_year": stats_df.round(4).to_dict(orient="index"),
    "weekday_weekend_by_year": wk_df.round(4).to_dict(orient="index"),
    "hourly_avg_by_year": hourly_table.round(4).to_dict(),
    "monthly_avg_by_year": monthly_table.round(4).to_dict(),
    "shift_2020_vs_2017_2019": {
        "mean_baseline_2017_2019": float(mean_baseline),
        "mean_2020": float(mean_2020),
        "abs_diff_mw": float(abs_diff),
        "pct_diff": float(pct_diff),
    },
    "hourly_diff_2020_vs_baseline": hourly_compare.round(4).to_dict(orient="index"),
    "data_integrity_march_june_2020": integrity,
}
out_path = os.path.join(os.path.dirname(__file__), "..", "reports", "regime_shift_investigation_raw.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, default=str)
print(f"\nSaved: {out_path}")
print(f"Saved plots under: {FIG_DIR}")
