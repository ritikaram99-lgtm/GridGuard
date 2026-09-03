"""
GridGuard AI - Inference wrapper for the genuine hourly (t+1h..t+24h) demand
forecasting model trained by ml/src/train_hourly_xgboost.py.

Produces GENUINE per-horizon XGBoost predictions -- each of the 24 hourly
values is an independent model.predict() call with a different
forecast_horizon feature value, not an interpolation between two points.

Does not modify the existing 24h model, feature pipeline, stress_engine.py,
or feeder_generator.py. Not yet wired into feeder_generator/rolling_integration
-- this is a standalone, validated forecasting component pending a decision
on how (or whether) to replace the existing interpolation with it, given the
accuracy limitations documented in ml/reports/hourly_forecast_evaluation.md.
"""
import os
import json
import pickle

import numpy as np
import pandas as pd

MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
RAW_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "continuous dataset.csv")

WEATHER_COLS = ["T2M_toc", "QV2M_toc", "TQL_toc", "W2M_toc",
                 "T2M_san", "QV2M_san", "TQL_san", "W2M_san",
                 "T2M_dav", "QV2M_dav", "TQL_dav", "W2M_dav"]
MAX_HORIZON = 24


def load_model_and_metadata():
    with open(os.path.join(MODELS_DIR, "hourly_model_metadata.json"), encoding="utf-8") as f:
        metadata = json.load(f)
    with open(os.path.join(MODELS_DIR, "hourly_demand_xgboost.pkl"), "rb") as f:
        model = pickle.load(f)
    assert list(model.get_booster().feature_names) == metadata["feature_list"], \
        "Loaded model's feature names do not match hourly_model_metadata.json"
    return model, metadata


def load_raw_demand():
    df = pd.read_csv(RAW_PATH)
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df.sort_values("datetime").reset_index(drop=True)


def _build_origin_feature_row(df: pd.DataFrame, origin_datetime: pd.Timestamp) -> dict:
    """Rebuilds the same origin-time (horizon-independent) features used in
    training, for a single origin timestamp. Requires `origin_datetime` to
    exist in `df` with at least 168h of prior history in the same frame."""
    idx = df.index[df["datetime"] == origin_datetime]
    assert len(idx) == 1, f"origin_datetime {origin_datetime} not found (uniquely) in raw data"
    i = idx[0]
    assert i >= 168, f"Insufficient history before {origin_datetime} (need >=168h)"

    row = {}
    for h in [1, 24, 48, 168]:
        row[f"lag_{h}h_nat_demand"] = float(df["nat_demand"].iloc[i - h])
    row["lag_0h_nat_demand"] = float(df["nat_demand"].iloc[i])

    for w in [24, 168]:
        window = df["nat_demand"].iloc[i - w + 1: i + 1]
        row[f"roll_mean_{w}h_nat_demand"] = float(window.mean())
        row[f"roll_std_{w}h_nat_demand"] = float(window.std())

    for c in WEATHER_COLS:
        row[f"origin_{c}"] = float(df[c].iloc[i])
        row[f"lag_24h_{c}"] = float(df[c].iloc[i - 24])

    row["origin_hour_of_day"] = int(df["datetime"].iloc[i].hour)
    row["origin_day_of_week"] = int(df["datetime"].iloc[i].dayofweek)
    row["origin_holiday_flag"] = float(df["holiday"].iloc[i])
    row["origin_school_flag"] = float(df["school"].iloc[i])
    return row


def _target_time_features(target_dt: pd.Timestamp, calendar_by_dt: pd.DataFrame) -> dict:
    row = {
        "target_hour_of_day": target_dt.hour,
        "target_day_of_week": target_dt.dayofweek,
        "target_month": target_dt.month,
        "target_is_weekend": int(target_dt.dayofweek in (5, 6)),
        "target_hour_sin": np.sin(2 * np.pi * target_dt.hour / 24),
        "target_hour_cos": np.cos(2 * np.pi * target_dt.hour / 24),
        "target_dow_sin": np.sin(2 * np.pi * target_dt.dayofweek / 7),
        "target_dow_cos": np.cos(2 * np.pi * target_dt.dayofweek / 7),
        "target_month_sin": np.sin(2 * np.pi * target_dt.month / 12),
        "target_month_cos": np.cos(2 * np.pi * target_dt.month / 12),
    }
    if target_dt in calendar_by_dt.index:
        cal = calendar_by_dt.loc[target_dt]
        row["target_holiday_id"] = float(cal["Holiday_ID"])
        row["target_holiday_flag"] = float(cal["holiday"])
        row["target_school_flag"] = float(cal["school"])
    else:
        raise ValueError(f"target_datetime {target_dt} is outside the raw data's calendar range "
                          f"(holiday/school flags are only known within the raw dataset's own coverage)")
    return row


def predict_hourly_trajectory(origin_datetime, model=None, metadata=None, df=None) -> pd.Series:
    """
    Returns a genuine 24-point hourly forecast (h=1..24) for the given
    origin timestamp, indexed by target_datetime, produced by 24 independent
    calls into the trained hourly XGBoost model (each with its own
    forecast_horizon feature value) -- NOT an interpolation.
    """
    if model is None or metadata is None:
        model, metadata = load_model_and_metadata()
    if df is None:
        df = load_raw_demand()

    origin_datetime = pd.Timestamp(origin_datetime)
    calendar_by_dt = df.set_index("datetime")[["Holiday_ID", "holiday", "school"]]

    origin_feats = _build_origin_feature_row(df, origin_datetime)

    rows = []
    target_times = []
    for h in range(1, MAX_HORIZON + 1):
        target_dt = origin_datetime + pd.Timedelta(hours=h)
        feats = dict(origin_feats)
        feats["forecast_horizon"] = h
        feats.update(_target_time_features(target_dt, calendar_by_dt))
        rows.append(feats)
        target_times.append(target_dt)

    X = pd.DataFrame(rows)[metadata["feature_list"]].astype(float)
    preds = model.predict(X)

    assert np.isfinite(preds).all(), "Hourly forecast produced NaN/inf"
    return pd.Series(preds, index=pd.DatetimeIndex(target_times, name="target_datetime"), name="predicted_nat_demand_mw")


if __name__ == "__main__":
    model, metadata = load_model_and_metadata()
    df = load_raw_demand()
    example_origin = df["datetime"].iloc[-25]  # an origin with a full 24h of real future data for comparison
    forecast = predict_hourly_trajectory(example_origin, model, metadata, df)
    print(f"Genuine 24h hourly forecast from origin {example_origin}:")
    print(forecast)
