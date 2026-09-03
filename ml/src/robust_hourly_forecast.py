"""
GridGuard AI - Regime-aware hourly forecasting interface.

    Current data
        v
    Regime detector (ml/src/regime_detector.py)
        v
    NORMAL -> Direct multi-horizon XGBoost (ml/src/direct_hourly_forecast.py)
    SHIFT  -> Same-hour-previous-day fallback: forecast(t+h) = demand(t+h-24h)
        v
    24 genuine hourly forecasts (h=1..24)

Does not modify the direct XGBoost models, stress_engine.py,
feeder_generator.py, rolling_integration.py, or any existing pipeline.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import regime_detector as rd
import direct_hourly_forecast as dhf

MAX_HORIZON = 24


def previous_day_fallback(origin_datetime: pd.Timestamp, df: pd.DataFrame) -> pd.Series:
    """forecast(t+h) = demand(t+h-24h) for h=1..24. Every source timestamp
    (t+h-24 for h=1..24, i.e. t-23..t) is <= origin t -- verified below."""
    demand_by_dt = df.set_index("datetime")["nat_demand"]
    preds, target_times, source_times = [], [], []
    for h in range(1, MAX_HORIZON + 1):
        target_dt = origin_datetime + pd.Timedelta(hours=h)
        source_dt = origin_datetime + pd.Timedelta(hours=h - 24)
        assert source_dt <= origin_datetime, (
            f"Fallback source timestamp {source_dt} is after origin {origin_datetime} -- leakage!"
        )
        if source_dt not in demand_by_dt.index:
            raise ValueError(f"Fallback source timestamp {source_dt} not found in raw data "
                              f"(insufficient history before origin {origin_datetime})")
        preds.append(float(demand_by_dt.loc[source_dt]))
        target_times.append(target_dt)
        source_times.append(source_dt)
    return pd.Series(preds, index=pd.DatetimeIndex(target_times, name="target_datetime"), name="predicted_nat_demand_mw")


def robust_hourly_forecast(origin_datetime, detector: rd.RegimeDetector = None,
                            direct_models=None, direct_metadata=None, df=None) -> list:
    """
    Returns a list of 24 dicts (h=1..24), each with:
      forecast_horizon, forecast_timestamp, forecast_mw, method
      (DIRECT_XGBOOST or PREVIOUS_DAY_FALLBACK), regime_status, detector
      score/signals.

    The regime decision is made ONCE per origin (using only information at
    or before origin t) and applied to all 24 horizons uniformly -- i.e. if
    SHIFT is detected, the fallback is used for the entire 24h forecast, not
    decided per-horizon (the detector describes the state of the system at
    the moment of forecasting, not a per-horizon property).
    """
    if df is None:
        df = dhf.load_raw_demand()
    if detector is None:
        detector = rd.RegimeDetector(df)
    if direct_models is None or direct_metadata is None:
        direct_models, direct_metadata = dhf.load_models_and_metadata()

    origin_datetime = pd.Timestamp(origin_datetime)
    detector_status = detector.status_at(origin_datetime)
    regime_status = detector_status["regime_status"]

    if regime_status == "NORMAL":
        trajectory = dhf.predict_hourly_trajectory(origin_datetime, direct_models, direct_metadata, df)
        method = "DIRECT_XGBOOST"
    else:
        trajectory = previous_day_fallback(origin_datetime, df)
        method = "PREVIOUS_DAY_FALLBACK"

    assert len(trajectory) == MAX_HORIZON
    assert np.isfinite(trajectory.values).all(), "Forecast trajectory contains NaN/inf"

    results = []
    for h in range(1, MAX_HORIZON + 1):
        target_dt = origin_datetime + pd.Timedelta(hours=h)
        assert target_dt == trajectory.index[h - 1] == origin_datetime + pd.Timedelta(hours=h)
        results.append({
            "forecast_horizon": h,
            "forecast_timestamp": str(target_dt),
            "forecast_mw": float(trajectory.iloc[h - 1]),
            "method": method,
            "regime_status": regime_status,
            "detector_primary_score": detector_status["primary_score"],
            "detector_secondary_score": detector_status["secondary_score"],
            "detector_lower_threshold": detector_status["lower_threshold"],
        })
    return results


if __name__ == "__main__":
    df = dhf.load_raw_demand()
    detector = rd.RegimeDetector(df)
    direct_models, direct_metadata = dhf.load_models_and_metadata()

    for example_origin in ["2020-01-15 12:00:00", "2020-04-15 12:00:00"]:
        print(f"\n=== Origin {example_origin} ===")
        result = robust_hourly_forecast(example_origin, detector, direct_models, direct_metadata, df)
        print(f"regime_status={result[0]['regime_status']}, method={result[0]['method']}, "
              f"primary_score={result[0]['detector_primary_score']:.3f}")
        for r in result[:3]:
            print(f"  h={r['forecast_horizon']}: {r['forecast_timestamp']} -> {r['forecast_mw']:.1f} MW")
