"""Copilot API route handlers."""

from fastapi import APIRouter, HTTPException
from app.schemas.copilot import CopilotResponse
from app.services import copilot_service

router = APIRouter(
    prefix="/api/copilot",
    tags=["Copilot"],
)


@router.get("/{feeder_id}", response_model=CopilotResponse)
def get_copilot_explanation(feeder_id: str) -> CopilotResponse:
    """Retrieve operational Copilot explanation for a specific grid feeder."""
    copilot_res = copilot_service.get_copilot_explanation(feeder_id)
    if not copilot_res:
        raise HTTPException(
            status_code=404,
            detail=f"Feeder {feeder_id} not found",
        )
    return copilot_res
