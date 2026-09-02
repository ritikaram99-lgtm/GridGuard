"""Recommendation API route handlers."""

from fastapi import APIRouter, HTTPException
from app.schemas.recommendation import RecommendationResponse
from app.services import recommendation_service

router = APIRouter(
    prefix="/api/recommendations",
    tags=["Recommendations"],
)


@router.post("/{feeder_id}", response_model=RecommendationResponse)
@router.get("/{feeder_id}", response_model=RecommendationResponse, include_in_schema=False)
def get_feeder_recommendation(feeder_id: str) -> RecommendationResponse:
    """Generate optimization recommendations to prevent predicted feeder overloads."""
    rec = recommendation_service.generate_recommendation(feeder_id)
    if not rec:
        raise HTTPException(
            status_code=404,
            detail=f"Feeder {feeder_id} not found",
        )
    return rec
