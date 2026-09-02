"""Model status API route handlers."""

from fastapi import APIRouter
from app.schemas.model import ModelStatusResponse
from app.services import ml_service

router = APIRouter(
    prefix="/api/model",
    tags=["Model"],
)


@router.get("/status", response_model=ModelStatusResponse)
def get_model_status() -> ModelStatusResponse:
    """Retrieve availability status and metadata of the machine learning forecast model."""
    status_dict = ml_service.get_status()
    return ModelStatusResponse(**status_dict)
