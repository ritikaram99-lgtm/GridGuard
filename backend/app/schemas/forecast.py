from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ForecastResponse(BaseModel):
    """Load forecast schema for 15m, 30m, 45m, and 60m time horizons."""

    m15: float = Field(..., alias="15m", ge=0, description="Predicted load at 15-minute horizon")
    m30: float = Field(..., alias="30m", ge=0, description="Predicted load at 30-minute horizon")
    m45: float = Field(..., alias="45m", ge=0, description="Predicted load at 45-minute horizon")
    m60: float = Field(..., alias="60m", ge=0, description="Predicted load at 60-minute horizon")
    source: Optional[str] = Field("mock", description="Source of forecast values ('ml' or 'mock')")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "15m": 99.0,
                "30m": 103.0,
                "45m": 108.0,
                "60m": 110.0,
                "source": "mock"
            }
        }
    )
