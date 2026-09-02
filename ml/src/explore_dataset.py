"""
GridGuard AI - Dataset validation and exploration for the Panama National
Electricity Load dataset (Mendeley DOI 10.17632/byx7sztj59.1).

This script performs read-only inspection of ml/data/raw/continuous dataset.csv.
It does not modify the raw file. Outputs (plots, stats) are written to
ml/reports/figures/ and printed to stdout for use in the audit report and
the exploration notebook.
"""
import os
import pandas as pd
import numpy as np

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
FIG_DIR = os.path.join(os.path.dirname(__file__), "..", "reports", "figures")
os.makedirs(FIG_DIR, exist_ok=True)

CSV_PATH = os.path.join(RAW_DIR, "continuous dataset.csv")

def section(title):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)

# ---------------------------------------------------------------------------
section("1-6. Load raw file, shape, columns, dtypes")
# ---------------------------------------------------------------------------
df_raw = pd.read_csv(CSV_PATH)
print("Filename:", os.path.basename(CSV_PATH))
print("Shape (rows, cols):", df_raw.shape)
print("\nColumns:")
for c in df_raw.columns:
    print(" -", c)
print("\nDtypes (as parsed by pandas, before any casting):")
print(df_raw.dtypes)

print("\nFirst 3 rows:")
print(df_raw.head(3).to_string())

# ---------------------------------------------------------------------------
section("6-7. Timestamp parsing and sampling frequency")
# ---------------------------------------------------------------------------
raw_dt_sample = df_raw["datetime"].iloc[:5].tolist()
print("Raw datetime string samples:", raw_dt_sample)

df = df_raw.copy()
df["datetime"] = pd.to_datetime(df["datetime"], errors="raise")
print("Parsed OK with pd.to_datetime, no coercion errors forced (errors='raise').")

deltas = df["datetime"].diff().dropna()
print("\nTimestamp delta value counts (top 10):")
print(deltas.value_counts().head(10))
inferred_freq = pd.infer_freq(df["datetime"])
print("\npandas.infer_freq result:", inferred_freq)

# ---------------------------------------------------------------------------
section("8. Min / max timestamp, span")
# ---------------------------------------------------------------------------
tmin, tmax = df["datetime"].min(), df["datetime"].max()
print("Min timestamp:", tmin)
print("Max timestamp:", tmax)
span_days = (tmax - tmin).days
print(f"Span: {span_days} days (~{span_days/365.25:.2f} years)")

# ---------------------------------------------------------------------------
section("9. Missing values per column")
# ---------------------------------------------------------------------------
missing = df.isna().sum()
missing_pct = (missing / len(df) * 100).round(4)
missing_report = pd.DataFrame({"missing_count": missing, "missing_pct": missing_pct})
print(missing_report)

# ---------------------------------------------------------------------------
section("10. Duplicate rows / timestamps")
# ---------------------------------------------------------------------------
dup_rows = df.duplicated().sum()
dup_timestamps = df["datetime"].duplicated().sum()
print("Fully duplicated rows:", dup_rows)
print("Duplicated timestamp values:", dup_timestamps)
if dup_timestamps > 0:
    print(df[df["datetime"].duplicated(keep=False)].sort_values("datetime").head(20))

# ---------------------------------------------------------------------------
section("11-13. Load column (nat_demand): units, descriptive stats, anomalies")
# ---------------------------------------------------------------------------
load_col = "nat_demand"
print(f"Load column: '{load_col}' (units per Mendeley documentation: MW, national demand)")
desc = df[load_col].describe()
print(desc)
print("Skew:", df[load_col].skew())
print("Kurtosis:", df[load_col].kurt())

zero_or_neg = (df[load_col] <= 0).sum()
print("\nRows with load <= 0:", zero_or_neg)

q1, q3 = df[load_col].quantile([0.25, 0.75])
iqr = q3 - q1
lower_fence, upper_fence = q1 - 3 * iqr, q3 + 3 * iqr
extreme_outliers = df[(df[load_col] < lower_fence) | (df[load_col] > upper_fence)]
print(f"Extreme outliers (3xIQR fence [{lower_fence:.1f}, {upper_fence:.1f}]):", len(extreme_outliers))
if len(extreme_outliers):
    print(extreme_outliers[["datetime", load_col]].head(20).to_string())

large_jumps = df[load_col].diff().abs()
jump_threshold = large_jumps.quantile(0.999)
print(f"\n99.9th percentile of abs(hour-to-hour load change): {jump_threshold:.2f}")
print("Rows exceeding it:", (large_jumps > jump_threshold).sum())

# ---------------------------------------------------------------------------
section("14. Weather variables available")
# ---------------------------------------------------------------------------
weather_cols = [c for c in df.columns if any(c.startswith(p) for p in ["T2M", "QV2M", "TQL", "W2M"])]
print("Weather-related columns found:", weather_cols)
print("\nInterpretation of suffixes per column metadata PDF: _toc = Tocumen, _san = Santiago, _dav = David")
print("T2M = temperature at 2m, QV2M = specific humidity at 2m, TQL = liquid precip water, W2M = wind speed at 2m")
print(df[weather_cols].describe().T)

# ---------------------------------------------------------------------------
section("15. Calendar variables available")
# ---------------------------------------------------------------------------
cal_cols = ["Holiday_ID", "holiday", "school"]
print("Calendar columns:", cal_cols)
for c in cal_cols:
    print(f"\n{c} value counts:")
    print(df[c].value_counts().sort_index())

# ---------------------------------------------------------------------------
section("16-17. Continuity check: is it truly hourly with no gaps?")
# ---------------------------------------------------------------------------
full_range = pd.date_range(start=tmin, end=tmax, freq="h")
missing_timestamps = full_range.difference(df["datetime"])
print(f"Expected hourly timestamps in [{tmin}, {tmax}]: {len(full_range)}")
print(f"Actual rows: {len(df)}")
print(f"Missing timestamps (gaps): {len(missing_timestamps)}")
if len(missing_timestamps) > 0:
    print("First 20 missing timestamps:")
    print(missing_timestamps[:20].tolist())
    # group consecutive gaps into blocks
    gap_series = pd.Series(missing_timestamps)
    gap_diff = gap_series.diff().dt.total_seconds().fillna(3600)
    block_id = (gap_diff != 3600).cumsum()
    blocks = gap_series.groupby(block_id).agg(["first", "last", "count"])
    print(f"\nNumber of contiguous gap blocks: {len(blocks)}")
    print(blocks.head(30).to_string())
    blocks.to_csv(os.path.join(FIG_DIR, "..", "gap_blocks.csv"), index=False)

# ---------------------------------------------------------------------------
# Correlation matrix
# ---------------------------------------------------------------------------
section("Correlation matrix (numeric columns)")
numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
corr = df[numeric_cols].corr()
print(corr.round(2))

print("\nDone. See ml/reports/figures/ for plots generated by the notebook.")
