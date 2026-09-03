"""Generates ml/notebooks/01_dataset_exploration.ipynb programmatically via nbformat."""
import nbformat as nbf
import os

nb = nbf.v4.new_notebook()
cells = []

def md(text):
    cells.append(nbf.v4.new_markdown_cell(text))

def code(text):
    cells.append(nbf.v4.new_code_cell(text))

md("""# GridGuard AI — Dataset Exploration (01)

**Dataset:** Panama National Electricity Load — Mendeley Data, DOI [10.17632/byx7sztj59.1](https://data.mendeley.com/datasets/byx7sztj59/1)
**Author:** Ernesto Aguilar Madrid, 2021
**Primary file analyzed:** `ml/data/raw/continuous dataset.csv`

Scope: read-only validation and exploration. No modeling, no synthetic data, no preprocessing of the raw file in this notebook (a copy is loaded into memory; the raw CSV on disk is never written to).
""")

code("""import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

RAW_PATH = os.path.join("..", "data", "raw", "continuous dataset.csv")
FIG_DIR = os.path.join("..", "reports", "figures")
os.makedirs(FIG_DIR, exist_ok=True)

pd.set_option("display.max_columns", None)
plt.rcParams["figure.figsize"] = (12, 4)
""")

md("## 1. Load raw file and inspect shape / columns / dtypes")
code("""df = pd.read_csv(RAW_PATH)
print("Shape:", df.shape)
df.dtypes
""")

code("""df.head()""")

md("## 2. Parse datetime and check sampling frequency")
code("""df["datetime"] = pd.to_datetime(df["datetime"])
deltas = df["datetime"].diff().dropna()
print(deltas.value_counts())
print("Inferred frequency:", pd.infer_freq(df["datetime"]))
print("Min timestamp:", df["datetime"].min())
print("Max timestamp:", df["datetime"].max())
""")

md("## 3. Missing values per column")
code("""missing = df.isna().sum()
missing_pct = (missing / len(df) * 100).round(4)
pd.DataFrame({"missing_count": missing, "missing_pct": missing_pct})
""")

md("## 4. Duplicate rows / duplicate timestamps")
code("""print("Fully duplicated rows:", df.duplicated().sum())
print("Duplicated timestamps:", df["datetime"].duplicated().sum())
""")

md("## 5. Continuity check — are all expected hourly timestamps present?")
code("""full_range = pd.date_range(start=df["datetime"].min(), end=df["datetime"].max(), freq="h")
missing_ts = full_range.difference(df["datetime"])
print(f"Expected hourly timestamps: {len(full_range)}")
print(f"Actual rows: {len(df)}")
print(f"Gaps (missing timestamps): {len(missing_ts)}")
""")

md("## 6. Descriptive statistics — load column (`nat_demand`)")
code("""df["nat_demand"].describe()""")

code("""fig, ax = plt.subplots()
df.set_index("datetime")["nat_demand"].plot(ax=ax, linewidth=0.5)
ax.set_title("National Demand (MW) Over Time — Full Series (2015-2020)")
ax.set_ylabel("nat_demand (MW)")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "load_over_time.png"), dpi=120)
plt.show()
""")

md("## 7. Anomaly check — outliers and large jumps")
code("""q1, q3 = df["nat_demand"].quantile([0.25, 0.75])
iqr = q3 - q1
lower, upper = q1 - 3*iqr, q3 + 3*iqr
outliers = df[(df["nat_demand"] < lower) | (df["nat_demand"] > upper)]
print(f"3xIQR fence: [{lower:.1f}, {upper:.1f}]")
print(f"Outlier rows: {len(outliers)}")
outliers[["datetime", "nat_demand"]]
""")

code("""jump = df["nat_demand"].diff().abs()
thresh = jump.quantile(0.999)
print("99.9th pct of |hour-to-hour change|:", round(thresh, 2))
df.loc[jump > thresh, ["datetime", "nat_demand"]].head(20)
""")

md("## 8. Average load by hour of day")
code("""df["hour"] = df["datetime"].dt.hour
hourly_avg = df.groupby("hour")["nat_demand"].mean()

fig, ax = plt.subplots()
hourly_avg.plot(kind="bar", ax=ax)
ax.set_title("Average National Demand by Hour of Day")
ax.set_xlabel("Hour of day")
ax.set_ylabel("Avg nat_demand (MW)")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "avg_load_by_hour.png"), dpi=120)
plt.show()
""")

md("## 9. Average load by day of week")
code("""df["dow"] = df["datetime"].dt.day_name()
order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
dow_avg = df.groupby("dow")["nat_demand"].mean().reindex(order)

fig, ax = plt.subplots()
dow_avg.plot(kind="bar", ax=ax, color="teal")
ax.set_title("Average National Demand by Day of Week")
ax.set_ylabel("Avg nat_demand (MW)")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "avg_load_by_dow.png"), dpi=120)
plt.show()
""")

md("## 10. Load distribution")
code("""fig, ax = plt.subplots()
df["nat_demand"].hist(bins=80, ax=ax)
ax.set_title("Distribution of National Demand (MW)")
ax.set_xlabel("nat_demand (MW)")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "load_distribution.png"), dpi=120)
plt.show()
""")

md("## 11. Temperature vs. load (Tocumen station, `T2M_toc`)")
code("""fig, ax = plt.subplots()
ax.scatter(df["T2M_toc"], df["nat_demand"], s=2, alpha=0.3)
ax.set_xlabel("T2M_toc (deg C, Tocumen)")
ax.set_ylabel("nat_demand (MW)")
ax.set_title("Temperature (Tocumen) vs. National Demand")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "temp_vs_load.png"), dpi=120)
plt.show()

print("Correlation T2M_toc vs nat_demand:", df["T2M_toc"].corr(df["nat_demand"]).round(3))
""")

md("## 12. Calendar variables — holiday and school flags")
code("""print(df["Holiday_ID"].value_counts().sort_index())
print()
print(df["holiday"].value_counts())
print()
print(df["school"].value_counts())
""")

md("## 13. Correlation matrix (numeric columns)")
code("""numeric_cols = df.select_dtypes(include=[np.number]).columns
corr = df[numeric_cols].corr()

fig, ax = plt.subplots(figsize=(10, 8))
im = ax.imshow(corr, cmap="coolwarm", vmin=-1, vmax=1)
ax.set_xticks(range(len(numeric_cols)))
ax.set_xticklabels(numeric_cols, rotation=90)
ax.set_yticks(range(len(numeric_cols)))
ax.set_yticklabels(numeric_cols)
fig.colorbar(im)
ax.set_title("Correlation Matrix — Numeric Variables")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "correlation_matrix.png"), dpi=120)
plt.show()

corr
""")

md("""## 14. Summary

See `ml/reports/dataset_audit.md` for the full written audit covering:
what the dataset contains, what's useful for forecasting, what's missing vs.
the GridGuard architecture, suitability, limitations, and next steps.
""")

nb["cells"] = cells
out_path = os.path.join(os.path.dirname(__file__), "..", "notebooks", "01_dataset_exploration.ipynb")
with open(out_path, "w", encoding="utf-8") as f:
    nbf.write(nb, f)
print("Notebook written to", out_path)
