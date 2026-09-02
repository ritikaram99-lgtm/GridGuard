"""Feeder API route handlers."""

from fastapi import APIRouter, HTTPException
from app.schemas.feeder import FeederResponse, FeederIntelligenceResponse
from app.services import feeder_service, intelligence_service

router = APIRouter(
    prefix="/api/feeders",
    tags=["Feeders"],
)


@router.get("", response_model=list[FeederResponse])
@router.get("/", response_model=list[FeederResponse], include_in_schema=False)
def list_feeders() -> list[FeederResponse]:
    """Retrieve all available grid feeders."""
    return feeder_service.get_all_feeders()


@router.get("/{feeder_id}/intelligence", response_model=FeederIntelligenceResponse)
def get_feeder_intelligence(feeder_id: str) -> FeederIntelligenceResponse:
    """Retrieve consolidated feeder intelligence including current status, forecast, risk, and recommendations."""
    intelligence = intelligence_service.get_feeder_intelligence(feeder_id)
    if not intelligence:
        raise HTTPException(
            status_code=404,
            detail=f"Feeder {feeder_id} not found",
        )
    return intelligence


@router.get("/{feeder_id}", response_model=FeederResponse)
def get_feeder(feeder_id: str) -> FeederResponse:
    """Retrieve details for a specific grid feeder by ID."""
    feeder = feeder_service.get_feeder_by_id(feeder_id)
    if not feeder:
        raise HTTPException(
            status_code=404,
            detail=f"Feeder {feeder_id} not found",
        )
    return feeder
