"""Risk API route handlers."""

from fastapi import APIRouter, HTTPException
from app.schemas.risk import DetailedRiskResponse
from app.services import risk_service

router = APIRouter(
    prefix="/api/risk",
    tags=["Risk"],
)


@router.get("/{feeder_id}", response_model=DetailedRiskResponse)
def get_feeder_risk(feeder_id: str) -> DetailedRiskResponse:
    """Calculate and retrieve stress score, risk level, time to overload, and contributors for a feeder."""
    risk = risk_service.calculate_feeder_risk(feeder_id)
    if not risk:
        raise HTTPException(
            status_code=404,
            detail=f"Feeder {feeder_id} not found",
        )
    return risk
