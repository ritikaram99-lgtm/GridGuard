"""Feeder API route handlers."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.schemas.feeder import FeederResponse, FeederIntelligenceResponse
from app.services import feeder_service, intelligence_service

router = APIRouter(
    prefix="/api/feeders",
    tags=["Feeders"],
)

_ORIGIN_DESC = "Optional ISO forecast-origin timestamp, forwarded to the ML pipeline for F01-F10. Ignored for legacy feeders."


@router.get("", response_model=list[FeederResponse])
@router.get("/", response_model=list[FeederResponse], include_in_schema=False)
def list_feeders(origin: Optional[str] = Query(None, description=_ORIGIN_DESC)) -> list[FeederResponse]:
    """Retrieve all available grid feeders."""
    try:
        return feeder_service.get_all_feeders(origin=origin)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.get("/{feeder_id}/intelligence", response_model=FeederIntelligenceResponse)
def get_feeder_intelligence(feeder_id: str, origin: Optional[str] = Query(None, description=_ORIGIN_DESC)) -> FeederIntelligenceResponse:
    """Retrieve consolidated feeder intelligence including current status, forecast, risk, and recommendations."""
    try:
        intelligence = intelligence_service.get_feeder_intelligence(feeder_id, origin=origin)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    if not intelligence:
        raise HTTPException(
            status_code=404,
            detail=f"Feeder {feeder_id} not found",
        )
    return intelligence


@router.get("/{feeder_id}", response_model=FeederResponse)
def get_feeder(feeder_id: str, origin: Optional[str] = Query(None, description=_ORIGIN_DESC)) -> FeederResponse:
    """Retrieve details for a specific grid feeder by ID."""
    try:
        feeder = feeder_service.get_feeder_by_id(feeder_id, origin=origin)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    if not feeder:
        raise HTTPException(
            status_code=404,
            detail=f"Feeder {feeder_id} not found",
        )
    return feeder
