"""Forecast service providing load forecasts for grid feeders.

Orchestrates forecast retrieval, preferring the real ML pipeline
(ml_adapter_service -> ml/src/ direct hourly XGBoost models, regime-aware,
bias-corrected) when available, falling back to the legacy joblib-based
MLForecastService (currently always unavailable -- no forecast_model.joblib
is produced by this project), and finally to deterministic mock data.
Persists predictions to PostgreSQL when connected.

FEEDER SCOPE: for the 10 real ML feeders (F01-F10), the ML pipeline's
synthetic feeder-allocation layer (ml/src/feeder_generator.py) is used, so
each feeder gets its OWN allocated hourly forecast derived from the real
national forecast (source='ml', scope='feeder') -- not a copy of the
national number. For any other feeder_id (the legacy mock feeder 'F12'),
the national forecast is served instead (scope='national'), same as before.

IDENTITY BOUNDARY: F01-F10 are reserved for the ML pipeline (see
feeder_service.py's module docstring) and are NEVER answered from
MOCK_FORECASTS, even if the ML adapter is unavailable or the requested
`origin` is invalid for that feeder -- get_forecast() raises ValueError for
a reserved id with a bad/out-of-range origin (callers/routes should surface
this as 400, distinct from "feeder truly doesn't exist" = 404) rather than
silently substituting unrelated legacy mock data.
"""

import logging
from typing import Optional
from app.schemas.forecast import ForecastResponse, HourlyForecastPoint
from app.services.feeder_service import get_feeder_by_id
from app.services.ml_forecast_service import ml_service
from app.services.ml_adapter_service import ml_adapter_service, is_reserved_ml_feeder_id
from app.services.db_service import record_predictions

logger = logging.getLogger(__name__)

# Mock forecast dataset for the one legacy, non-ML-reserved feeder id.
MOCK_FORECASTS: dict[str, dict[str, float]] = {
    "F12": {
        "15m": 112.0,
        "30m": 115.0,
        "45m": 118.0,
        "60m": 120.0,
    },
}


def get_forecast_peak(forecast: ForecastResponse) -> float:
    """Extract the peak forecasted MW from a ForecastResponse, regardless of
    whether it carries a real ML hourly forecast (`hourly`, 24 points) or a
    legacy mock/joblib 4-point forecast (`m15`..`m60`).

    COMPATIBILITY HELPER ONLY: added so existing risk/recommendation/
    simulation/dispatch/demo services (unchanged Phase 1 scope -- their
    formulas and decision logic are NOT modified) don't crash on the now-
    nullable m15..m60 fields when source='ml'. Does not alter any
    downstream business logic.
    """
    if forecast.hourly:
        return max(pt.load_mw for pt in forecast.hourly)
    values = [v for v in (forecast.m15, forecast.m30, forecast.m45, forecast.m60) if v is not None]
    if not values:
        raise ValueError("ForecastResponse has neither `hourly` nor any populated m15..m60 values")
    return max(values)


def _forecast_response_from_adapted(adapted: dict) -> ForecastResponse:
    return ForecastResponse(
        source="ml",
        hourly=[HourlyForecastPoint(**pt) for pt in adapted["hourly"]],
        origin_timestamp=adapted["origin_timestamp"],
        forecast_method=adapted["forecast_method"],
        regime_status=adapted["regime_status"],
        regime_score=adapted["regime_score"],
        scope=adapted["scope"],
    )


def get_forecast(feeder_id: str, origin: Optional[str] = None) -> Optional[ForecastResponse]:
    """Retrieve a load forecast for a specified feeder.

    For F01-F10 (reserved ML feeder ids): ALWAYS the real ML pipeline's
    feeder-level allocation (source='ml', scope='feeder'). Never falls back
    to legacy/mock data for these ids. Returns None if the ML adapter is
    unavailable; raises ValueError if `origin` is provided but invalid/
    out-of-range for that feeder (callers should surface this as HTTP 400,
    distinct from "feeder not found" = 404).

    For any other feeder_id (currently only legacy 'F12'): real ML NATIONAL
    forecast when available (source='ml', scope='national'), else legacy
    joblib model (currently always unavailable), else deterministic mock
    (source='mock').

    Args:
        feeder_id (str): Unique feeder identifier (e.g. 'F07').
        origin (Optional[str]): Optional ISO forecast-origin timestamp,
            forwarded to ml_adapter_service when using the real ML pipeline.
            Must fall within the ML dataset's historical coverage
            (2015-01-10 .. 2020-06-26); ignored for mock/legacy paths.

    Returns:
        Optional[ForecastResponse]: Forecast schema model if feeder exists, else None.

    Raises:
        ValueError: `origin` was given but is invalid/out-of-range, for a
            reserved ML feeder id (F01-F10) whose adapter is available.
    """
    fid = feeder_id.upper()

    if is_reserved_ml_feeder_id(fid):
        if not ml_adapter_service.is_available():
            return None
        # Reserved id: the ML pipeline is the ONLY source of truth. A bad
        # origin propagates as ValueError rather than being swallowed into a
        # legacy/mock substitute of the same id.
        adapted = ml_adapter_service.get_feeder_forecast(fid, origin)
        res = _forecast_response_from_adapted(adapted)
    else:
        feeder = get_feeder_by_id(feeder_id)
        if not feeder:
            return None
        res = None

        # 1. Real ML pipeline national forecast (non-reserved ids only).
        if ml_adapter_service.is_available():
            try:
                adapted = ml_adapter_service.get_national_forecast(origin)
                res = _forecast_response_from_adapted(adapted)
            except ValueError as err:
                logger.warning(f"ML adapter could not produce a national forecast for feeder '{fid}' (origin={origin}): {err}")
                res = None

        # 2. Legacy joblib-based model (kept for compatibility; no forecast_model.joblib
        #    is produced by this project, so this branch is currently always unavailable).
        if res is None and ml_service.is_available():
            res = ml_service.predict_forecast(fid)

        if res is None:
            forecast_data = MOCK_FORECASTS.get(fid)
            if not forecast_data:
                return None
            res = ForecastResponse(**forecast_data, source="mock")

    # Persist predictions to DB (non-blocking)
    try:
        record_predictions(fid, res)
    except Exception:
        pass

    return res
