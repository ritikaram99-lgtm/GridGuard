"""Recommendation API route handlers."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.schemas.recommendation import RecommendationResponse
from app.services import recommendation_service

router = APIRouter(
    prefix="/api/recommendations",
    tags=["Recommendations"],
)


@router.post("/{feeder_id}", response_model=RecommendationResponse)
@router.get("/{feeder_id}", response_model=RecommendationResponse, include_in_schema=False)
def get_feeder_recommendation(
    feeder_id: str,
    origin: Optional[str] = Query(
        None,
        description="Optional ISO forecast-origin timestamp, forwarded to the ML pipeline for F01-F10. Ignored for legacy feeders.",
    ),
) -> RecommendationResponse:
    """Generate optimization recommendations to prevent predicted feeder overloads."""
    try:
        rec = recommendation_service.generate_recommendation(feeder_id, origin=origin)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    if not rec:
        raise HTTPException(
            status_code=404,
            detail=f"Feeder {feeder_id} not found",
        )
    return rec
