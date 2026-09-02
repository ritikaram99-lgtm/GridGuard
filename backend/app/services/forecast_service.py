"""Forecast service providing load forecasts for grid feeders.

Orchestrates forecast retrieval via the ML Forecast Service when a trained model artifact is available,
or falls back to deterministic mock data when no model artifact is present. Persists predictions to PostgreSQL when connected.
"""

from typing import Optional
from app.schemas.forecast import ForecastResponse
from app.services.feeder_service import get_feeder_by_id
from app.services.ml_forecast_service import ml_service
from app.services.db_service import record_predictions

# Mock forecast dataset mapped by feeder ID
MOCK_FORECASTS: dict[str, dict[str, float]] = {
    "F01": {
        "15m": 53.0,
        "30m": 54.0,
        "45m": 55.0,
        "60m": 56.0,
    },
    "F04": {
        "15m": 87.0,
        "30m": 89.0,
        "45m": 92.0,
        "60m": 95.0,
    },
    "F07": {
        "15m": 99.0,
        "30m": 103.0,
        "45m": 108.0,
        "60m": 110.0,
    },
    "F12": {
        "15m": 112.0,
        "30m": 115.0,
        "45m": 118.0,
        "60m": 120.0,
    },
}


def get_forecast(feeder_id: str) -> Optional[ForecastResponse]:
    """Retrieve 15m, 30m, 45m, and 60m load forecast for a specified feeder.

    Tries ML model inference if available; falls back to deterministic mock values with source='mock'.

    Args:
        feeder_id (str): Unique feeder identifier (e.g. 'F07').

    Returns:
        Optional[ForecastResponse]: Forecast schema model if feeder exists, else None.
    """
    # Verify feeder existence using feeder_service
    feeder = get_feeder_by_id(feeder_id)
    if not feeder:
        return None

    fid = feeder.id.upper()
    res: Optional[ForecastResponse] = None

    # Attempt ML model inference if available
    if ml_service.is_available():
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
