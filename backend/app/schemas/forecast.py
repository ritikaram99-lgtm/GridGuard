from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class HourlyForecastPoint(BaseModel):
    """One genuine hourly ML forecast point. NOT interpolated -- each point
    is an independent prediction from its own dedicated per-horizon XGBoost
    model (ml/models/direct_hourly/horizon_NN.pkl)."""

    horizon: int = Field(..., ge=1, le=24, description="Forecast horizon in hours ahead of origin_timestamp (1-24)")
    timestamp: str = Field(..., description="Target timestamp for this horizon (origin_timestamp + horizon hours)")
    load_mw: float = Field(..., ge=0, description="Predicted NATIONAL demand at this horizon, in MW")


class ForecastResponse(BaseModel):
    """Load forecast schema.

    Legacy 15/30/45/60-minute fields (`m15`..`m60`) are preserved for
    backward compatibility but are NULL whenever a real hourly ML forecast
    is served (source='ml'): the underlying models are genuinely hourly, no
    sub-hourly values exist anywhere in the ML pipeline, and none are
    fabricated here. They remain populated only for source='mock'. Real ML
    forecasts populate `hourly` (24 genuine points) instead.
    """

    m15: Optional[float] = Field(None, alias="15m", ge=0, description="Mock-only: predicted load at 15-minute horizon. Null when source='ml'.")
    m30: Optional[float] = Field(None, alias="30m", ge=0, description="Mock-only: predicted load at 30-minute horizon. Null when source='ml'.")
    m45: Optional[float] = Field(None, alias="45m", ge=0, description="Mock-only: predicted load at 45-minute horizon. Null when source='ml'.")
    m60: Optional[float] = Field(None, alias="60m", ge=0, description="Mock-only: predicted load at 60-minute horizon. Null when source='ml'.")
    source: Optional[str] = Field("mock", description="Source of forecast values ('ml' or 'mock')")

    hourly: Optional[List[HourlyForecastPoint]] = Field(
        None,
        description=(
            "Genuine 24-hour ML forecast (t+1h..t+24h), Panama NATIONAL demand in MW "
            "(not feeder-specific). Populated only when source='ml'."
        ),
    )
    origin_timestamp: Optional[str] = Field(
        None, description="Forecast origin timestamp used to produce `hourly` (within the ML dataset's 2015-2020 historical coverage)"
    )
    forecast_method: Optional[str] = Field(
        None, description="'BIAS_CORRECTED_DIRECT_XGBOOST' or 'PREVIOUS_DAY_FALLBACK', from the regime-aware ML forecasting pipeline"
    )
    regime_status: Optional[str] = Field(None, description="'NORMAL' or 'SHIFT', from ml/src/regime_detector.py")
    regime_score: Optional[float] = Field(
        None, description="Regime detector's primary score (unbounded, e.g. -3..+3 seasonal z-score); NOT a confidence value"
    )
    scope: Optional[str] = Field(
        None, description="Data scope disclosure. 'national' means these values are Panama national demand, not feeder-specific (Phase 1 limitation)."
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "15m": None,
                "30m": None,
                "45m": None,
                "60m": None,
                "source": "ml",
                "hourly": [
                    {"horizon": 1, "timestamp": "2020-06-26 01:00:00", "load_mw": 1004.3},
                    {"horizon": 2, "timestamp": "2020-06-26 02:00:00", "load_mw": 974.4},
                ],
                "origin_timestamp": "2020-06-26 00:00:00",
                "forecast_method": "BIAS_CORRECTED_DIRECT_XGBOOST",
                "regime_status": "NORMAL",
                "regime_score": 1.23,
                "scope": "national",
            }
        },
    )
