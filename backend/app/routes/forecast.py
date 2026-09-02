"""Forecast API route handlers."""

from fastapi import APIRouter, HTTPException
from app.schemas.forecast import ForecastResponse
from app.services import forecast_service

router = APIRouter(
    prefix="/api/forecast",
    tags=["Forecast"],
)


@router.get("/{feeder_id}", response_model=ForecastResponse)
def get_feeder_forecast(feeder_id: str) -> ForecastResponse:
    """Retrieve 15m, 30m, 45m, and 60m load forecast for a specific grid feeder."""
    forecast = forecast_service.get_forecast(feeder_id)
    if not forecast:
        raise HTTPException(
            status_code=404,
            detail=f"Feeder {feeder_id} not found",
        )
    return forecast
