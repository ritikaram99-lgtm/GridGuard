"""
GridGuard AI - Regime-shift detector.

A simple, explainable STATISTICAL detector (not another ML model) that
flags whether national demand at forecast origin t looks like it belongs to
the "normal" regime the direct XGBoost models were trained on, or looks like
an out-of-regime shift (such as the documented 2020 COVID-period demand
suppression -- see regime_shift_analysis.md / regime_shift_investigation.md).

*** USES ONLY INFORMATION AVAILABLE AT ORIGIN TIME t. ***
Every signal below is a causal (backward-looking) function of demand at or
before t. Never uses future actual demand, future weather, or future
forecast errors. See leakage checks in ml/tests/test_regime_detector.py.

METHODOLOGY
-----------
1. Reference distribution: for each (month, is_weekend, hour-of-day) cell,
   the mean and std of nat_demand computed ONLY from the TRAIN period
   (<=2018-12-31) -- frozen once, never recomputed on validation or test
   data. This is a simple seasonal-naive expectation of "what demand should
   look like at this calendar position," learned only from pre-2019 data.

2. Primary detector signal -- seasonal z-score, smoothed:
   For each hour, z(t) = (nat_demand(t) - ref_mean[cell(t)]) / ref_std[cell(t)].
   The PRIMARY DETECTOR SCORE is a trailing 168-hour (7-day) causal rolling
   mean of z(t), ending at t: score(t) = mean(z(t-167..t)). Smoothing over a
   full week suppresses single-day noise and holiday effects, and reflects a
   *persistent* regime-level deviation rather than a one-off event -- exactly
   the kind of change a real regime shift produces.

3. Secondary (diagnostic, not decision-gating) signal -- recent day-over-day
   deviation: trailing 24h causal rolling mean of
   (nat_demand(t) - nat_demand(t-24)) / nat_demand(t-24). Reported alongside
   the primary score for interpretability ("is demand also behaving
   erratically day-to-day right now"), but the SHIFT/NORMAL decision is
   based on the primary score alone, to keep the detector simple and avoid
   compounding threshold-tuning risk across multiple signals.

4. Threshold: ONE-SIDED, lower-tail only. The primary score's 1st
   percentile, computed ONLY over the TRAIN+VALIDATION period
   (2015-01-10 .. 2019-12-31 -- a period with no documented regime shift).
   Frozen once and never recomputed or tuned against the 2020 test period.

   WHY ONE-SIDED, NOT TWO-SIDED (evidence from train/val data only, not
   test): an earlier two-sided version of this detector (with a symmetric
   99th-percentile upper threshold) was checked against the VALIDATION
   period alone (2019 -- a year with no documented regime shift) and found
   that ~5% of 2019 hours already exceeded that upper threshold. This is
   because Panama's national demand has an ordinary secular growth trend
   (documented in the dataset audit), so a seasonal reference frozen at the
   2015-2018 level reads increasingly "high" for every later year purely
   from organic growth -- not a regime shift. A fixed upper bound against a
   reference frozen years earlier is therefore not a reliable signal and
   would misclassify ordinary growth as a shift. This was discovered and
   corrected using only train/validation evidence, before any evaluation
   against the 2020 test period. The single remaining lower-tail threshold
   flags only the most extreme ~1% of train+val hours as SHIFT by
   construction -- an explicit, documented, conservative false-positive
   budget, not an arbitrary round number -- and directly matches the actual
   phenomenon of concern (demand SUPPRESSION, a lower-tail event).
"""
import os

import numpy as np
import pandas as pd

RAW_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "continuous dataset.csv")

TRAIN_END = pd.Timestamp("2018-12-31 23:00:00")
VAL_END = pd.Timestamp("2019-12-31 23:00:00")

PRIMARY_WINDOW_HOURS = 168   # 7-day causal smoothing window for the primary signal
SECONDARY_WINDOW_HOURS = 24  # 1-day causal smoothing window for the secondary (diagnostic) signal
THRESHOLD_LOWER_PERCENTILE = 1.0   # frozen from train+val only; one-sided (see module docstring for why)


def load_raw_demand():
    df = pd.read_csv(RAW_PATH)
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df.sort_values("datetime").reset_index(drop=True)


def build_seasonal_reference(df: pd.DataFrame, train_end: pd.Timestamp = TRAIN_END) -> pd.DataFrame:
    """Frozen (month, is_weekend, hour) -> (mean, std) of nat_demand, computed
    ONLY from rows with datetime <= train_end. Never touches validation or
    test data."""
    train = df[df["datetime"] <= train_end].copy()
    train["month"] = train["datetime"].dt.month
    train["is_weekend"] = train["datetime"].dt.dayofweek.isin([5, 6])
    train["hour"] = train["datetime"].dt.hour
    ref = train.groupby(["month", "is_weekend", "hour"])["nat_demand"].agg(["mean", "std"]).reset_index()
    ref = ref.rename(columns={"mean": "ref_mean", "std": "ref_std"})
    assert (ref["ref_std"] > 0).all(), "Reference std must be positive in every cell"
    return ref


def compute_detector_signals(df: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    """Computes the primary and secondary detector signals for every row of
    df, using only causal (backward-looking) rolling windows -- safe for use
    at any origin t using only data at or before t. Returns a DataFrame
    indexed by datetime with columns: seasonal_zscore, primary_score,
    secondary_score."""
    d = df.copy()
    d["month"] = d["datetime"].dt.month
    d["is_weekend"] = d["datetime"].dt.dayofweek.isin([5, 6])
    d["hour"] = d["datetime"].dt.hour
    d = d.merge(reference, on=["month", "is_weekend", "hour"], how="left")
    assert d["ref_mean"].isna().sum() == 0, "Reference lookup failed for some (month, is_weekend, hour) cell"

    d["seasonal_zscore"] = (d["nat_demand"] - d["ref_mean"]) / d["ref_std"]
    # causal rolling mean: value at row i depends only on rows i-window+1..i
    d["primary_score"] = d["seasonal_zscore"].rolling(window=PRIMARY_WINDOW_HOURS, min_periods=PRIMARY_WINDOW_HOURS).mean()

    day_over_day = (d["nat_demand"] - d["nat_demand"].shift(24)) / d["nat_demand"].shift(24)
    d["secondary_score"] = day_over_day.rolling(window=SECONDARY_WINDOW_HOURS, min_periods=SECONDARY_WINDOW_HOURS).mean()

    return d[["datetime", "seasonal_zscore", "primary_score", "secondary_score"]].set_index("datetime")


def freeze_thresholds(signals: pd.DataFrame, train_end: pd.Timestamp = TRAIN_END,
                       val_end: pd.Timestamp = VAL_END) -> dict:
    """Selects (and freezes) the one-sided lower detector threshold using
    ONLY the train+validation period's primary_score distribution. Must
    never be called with test-period data included. See module docstring
    for why this is one-sided (lower tail only), not symmetric."""
    train_val = signals[signals.index <= val_end]["primary_score"].dropna()
    assert train_val.index.max() <= val_end
    lower = float(np.percentile(train_val, THRESHOLD_LOWER_PERCENTILE))
    return {
        "lower_threshold": lower,
        "lower_percentile": THRESHOLD_LOWER_PERCENTILE,
        "n_train_val_hours_used": int(len(train_val)),
        "train_val_range": [str(signals.index.min()), str(val_end)],
    }


def classify_regime(primary_score: float, thresholds: dict) -> str:
    if not np.isfinite(primary_score):
        raise ValueError(f"primary_score must be finite, got {primary_score}")
    if primary_score < thresholds["lower_threshold"]:
        return "SHIFT"
    return "NORMAL"


class RegimeDetector:
    """Convenience wrapper bundling the frozen reference, thresholds, and
    precomputed causal signal series, for repeated lookups by origin
    timestamp without recomputation."""

    def __init__(self, df: pd.DataFrame = None):
        if df is None:
            df = load_raw_demand()
        self.reference = build_seasonal_reference(df)
        self.signals = compute_detector_signals(df, self.reference)
        self.thresholds = freeze_thresholds(self.signals)

    def status_at(self, origin_datetime) -> dict:
        origin_datetime = pd.Timestamp(origin_datetime)
        if origin_datetime not in self.signals.index:
            raise ValueError(f"No signal computed for origin_datetime {origin_datetime}")
        row = self.signals.loc[origin_datetime]
        primary = float(row["primary_score"])
        if not np.isfinite(primary):
            raise ValueError(f"primary_score is not finite at {origin_datetime} "
                              f"(insufficient {PRIMARY_WINDOW_HOURS}h history before this origin)")
        status = classify_regime(primary, self.thresholds)
        return {
            "origin_datetime": str(origin_datetime),
            "regime_status": status,
            "primary_score": primary,
            "secondary_score": float(row["secondary_score"]) if np.isfinite(row["secondary_score"]) else None,
            "seasonal_zscore_instantaneous": float(row["seasonal_zscore"]),
            "lower_threshold": self.thresholds["lower_threshold"],
        }


if __name__ == "__main__":
    detector = RegimeDetector()
    print("Frozen thresholds (from train+val only):")
    print(detector.thresholds)
    for example_dt in ["2020-01-15 12:00:00", "2020-04-15 12:00:00", "2020-06-15 12:00:00"]:
        print(detector.status_at(example_dt))
