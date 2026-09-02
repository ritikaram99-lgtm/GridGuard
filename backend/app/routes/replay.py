"""Historical Replay API route handlers."""

from fastapi import APIRouter, HTTPException, status

from app.schemas.replay import (
    ReplayIngestRequest,
    ReplayIngestResponse,
    ReplayLatestResponse,
    ReplayQueryRequest,
    ReplayQueryResponse,
)
from app.services.feeder_service import get_feeder_by_id
from app.services.replay_service import replay_service

router = APIRouter(
    prefix="/api/replay",
    tags=["Historical Replay"],
)


@router.post("/query", response_model=ReplayQueryResponse)
def query_historical_records(request: ReplayQueryRequest) -> ReplayQueryResponse:
    """Query historical time-series feeder records chronologically."""
    # Check feeder existence
    feeder = get_feeder_by_id(request.feeder_id)
    if not feeder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feeder '{request.feeder_id}' not found.",
        )

    try:
        records = replay_service.get_replay_window(
            feeder_id=request.feeder_id,
            start_timestamp=request.start_timestamp,
            end_timestamp=request.end_timestamp,
            limit=request.limit or 100,
        )
        return ReplayQueryResponse(
            feeder_id=feeder.id,
            count=len(records),
            records=records,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


@router.get("/{feeder_id}/latest", response_model=ReplayLatestResponse)
def get_latest_historical_record(feeder_id: str) -> ReplayLatestResponse:
    """Retrieve the latest available historical time-series record for a feeder."""
    feeder = get_feeder_by_id(feeder_id)
    if not feeder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feeder '{feeder_id}' not found.",
        )

    latest = replay_service.get_latest_record(feeder_id)
    if not latest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No historical records found for feeder '{feeder_id}'.",
        )

    return latest


@router.post("/{feeder_id}/ingest", response_model=ReplayIngestResponse)
def ingest_historical_record(feeder_id: str, request: ReplayIngestRequest) -> ReplayIngestResponse:
    """Persist a selected historical record into the PostgreSQL measurements table."""
    feeder = get_feeder_by_id(feeder_id)
    if not feeder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feeder '{feeder_id}' not found.",
        )

    ingested = replay_service.ingest_record(
        feeder_id=feeder_id,
        timestamp_str=request.timestamp,
    )
    if not ingested:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Historical timestamp '{request.timestamp}' not found for feeder '{feeder_id}'.",
        )

    return ingested
