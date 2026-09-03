"""Forecast API route handlers."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.schemas.forecast import ForecastResponse
from app.services import forecast_service

router = APIRouter(
    prefix="/api/forecast",
    tags=["Forecast"],
)


@router.get("/{feeder_id}", response_model=ForecastResponse)
def get_feeder_forecast(
    feeder_id: str,
    origin: Optional[str] = Query(
        None,
        description=(
            "Optional ISO forecast-origin timestamp (e.g. '2020-06-25 00:00:00'), used only when "
            "source='ml'. Must fall within the ML dataset's historical coverage "
            "(2015-01-10 .. 2020-06-26 -- there is no live/real-time data source in this pipeline). "
            "Defaults to the latest valid origin when omitted."
        ),
    ),
) -> ForecastResponse:
    """Retrieve the load forecast for a specific grid feeder.

    Returns the real 24-hour genuine hourly ML forecast (source='ml') when
    the ML pipeline is available -- the feeder's own allocated forecast for
    the 10 ML feeders (F01-F10), otherwise a deterministic mock forecast
    (source='mock', legacy 15/30/45/60-minute fields).

    404 means the feeder id doesn't exist (or, for F01-F10, the ML adapter
    is currently unavailable). 400 means the feeder exists but the given
    `origin` is invalid/out-of-range for it.
    """
    try:
        forecast = forecast_service.get_forecast(feeder_id, origin=origin)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    if not forecast:
        raise HTTPException(
            status_code=404,
            detail=f"Feeder {feeder_id} not found",
        )
    return forecast
