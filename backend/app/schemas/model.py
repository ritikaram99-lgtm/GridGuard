from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ModelStatusResponse(BaseModel):
    """Response payload for machine learning model availability status."""

    model_available: bool = Field(..., description="Flag indicating whether a trained model artifact is loaded")
    model_type: str = Field("forecast", description="Type of machine learning model")
    model_path: str = Field(..., description="Relative project path to the expected model artifact")
    model_version: Optional[str] = Field(None, description="Model version tag if available")

    model_config = ConfigDict(populate_by_name=True)
