"""
GridGuard AI - Inference wrapper for the direct multi-horizon hourly
forecasting experiment (24 independent XGBoost models, one per horizon,
trained by ml/src/train_direct_hourly_xgboost.py).

Each of the 24 hourly predictions is produced by a DIFFERENT model file
(ml/models/direct_hourly/horizon_NN.pkl), each trained to predict exactly
its own fixed horizon -- not a shared model with a horizon feature, and not
an interpolation.

Does not modify the existing dedicated 24h model, the existing pooled hourly
model, stress_engine.py, feeder_generator.py, or rolling_integration.py.
"""
import os
import json
import pickle

import numpy as np
import pandas as pd

MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "direct_hourly")
RAW_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "continuous dataset.csv")

WEATHER_COLS = ["T2M_toc", "QV2M_toc", "TQL_toc", "W2M_toc",
                 "T2M_san", "QV2M_san", "TQL_san", "W2M_san",
                 "T2M_dav", "QV2M_dav", "TQL_dav", "W2M_dav"]
LAG_HOURS = [0, 1, 2, 3, 24, 48, 168]
MAX_HORIZON = 24


def load_models_and_metadata():
    with open(os.path.join(MODELS_DIR, "direct_hourly_metadata.json"), encoding="utf-8") as f:
        metadata = json.load(f)
    models = {}
    for h in range(1, MAX_HORIZON + 1):
        with open(os.path.join(MODELS_DIR, f"horizon_{h:02d}.pkl"), "rb") as f:
            models[h] = pickle.load(f)
        assert list(models[h].get_booster().feature_names) == metadata["feature_list"], \
            f"horizon_{h:02d}.pkl feature names do not match direct_hourly_metadata.json"
    return models, metadata


def load_raw_demand():
    df = pd.read_csv(RAW_PATH)
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df.sort_values("datetime").reset_index(drop=True)


def _build_origin_feature_row(df: pd.DataFrame, origin_datetime: pd.Timestamp) -> dict:
    idx = df.index[df["datetime"] == origin_datetime]
    assert len(idx) == 1, f"origin_datetime {origin_datetime} not found (uniquely) in raw data"
    i = idx[0]
    assert i >= 168, f"Insufficient history before {origin_datetime} (need >=168h)"

    row = {}
    for h in LAG_HOURS:
        row[f"lag_{h}h_nat_demand"] = float(df["nat_demand"].iloc[i - h])
    for w in [24, 168]:
        window = df["nat_demand"].iloc[i - w + 1: i + 1]
        row[f"roll_mean_{w}h_nat_demand"] = float(window.mean())
        row[f"roll_std_{w}h_nat_demand"] = float(window.std())
    for w in [3, 6]:
        row[f"roll_mean_{w}h_nat_demand"] = float(df["nat_demand"].iloc[i - w + 1: i + 1].mean())
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
    if target_dt not in calendar_by_dt.index:
        raise ValueError(f"target_datetime {target_dt} is outside the raw data's calendar range")
    cal = calendar_by_dt.loc[target_dt]
    row["target_holiday_id"] = float(cal["Holiday_ID"])
    row["target_holiday_flag"] = float(cal["holiday"])
    row["target_school_flag"] = float(cal["school"])
    return row


def predict_hourly_trajectory(origin_datetime, models=None, metadata=None, df=None) -> pd.Series:
    """
    Returns a genuine 24-point hourly forecast (h=1..24) for the given origin
    timestamp, indexed by target_datetime. Each point comes from a DIFFERENT
    model (models[h]), each trained to predict exactly that fixed horizon.
    """
    if models is None or metadata is None:
        models, metadata = load_models_and_metadata()
    if df is None:
        df = load_raw_demand()

    origin_datetime = pd.Timestamp(origin_datetime)
    calendar_by_dt = df.set_index("datetime")[["Holiday_ID", "holiday", "school"]]
    origin_feats = _build_origin_feature_row(df, origin_datetime)

    preds, target_times = [], []
    for h in range(1, MAX_HORIZON + 1):
        target_dt = origin_datetime + pd.Timedelta(hours=h)
        feats = dict(origin_feats)
        feats.update(_target_time_features(target_dt, calendar_by_dt))
        X = pd.DataFrame([feats])[metadata["feature_list"]].astype(float)
        pred = models[h].predict(X)[0]
        preds.append(pred)
        target_times.append(target_dt)

    preds = np.array(preds)
    assert np.isfinite(preds).all(), "Direct hourly forecast produced NaN/inf"
    return pd.Series(preds, index=pd.DatetimeIndex(target_times, name="target_datetime"), name="predicted_nat_demand_mw")


if __name__ == "__main__":
    models, metadata = load_models_and_metadata()
    df = load_raw_demand()
    example_origin = df["datetime"].iloc[-25]
    forecast = predict_hourly_trajectory(example_origin, models, metadata, df)
    print(f"Genuine 24h direct multi-horizon forecast from origin {example_origin}:")
    print(forecast)
