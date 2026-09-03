"""Risk API route handlers."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.schemas.risk import DetailedRiskResponse
from app.services import risk_service

router = APIRouter(
    prefix="/api/risk",
    tags=["Risk"],
)


@router.get("/{feeder_id}", response_model=DetailedRiskResponse)
def get_feeder_risk(
    feeder_id: str,
    origin: Optional[str] = Query(
        None,
        description=(
            "Optional ISO forecast-origin timestamp, used only for the real ML Stress Engine path "
            "(feeder ids F01-F10). Ignored for the legacy formula fallback."
        ),
    ),
) -> DetailedRiskResponse:
    """Calculate and retrieve stress score, risk level, time to overload, and contributors for a feeder.

    Uses the real Grid Stress Engine (source='ml_stress_engine') for the 10
    ML feeders (F01-F10), or the legacy formula (source='legacy_formula')
    otherwise.

    404 means the feeder id doesn't exist (or, for F01-F10, the ML adapter
    is currently unavailable). 400 means the feeder exists but the given
    `origin` is invalid/out-of-range for it.
    """
    try:
        risk = risk_service.calculate_feeder_risk(feeder_id, origin=origin)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    if not risk:
        raise HTTPException(
            status_code=404,
            detail=f"Feeder {feeder_id} not found",
        )
    return risk
