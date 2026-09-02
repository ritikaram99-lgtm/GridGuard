from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.forecast import ForecastResponse
from app.schemas.risk import RiskInfo, RiskContributor
from app.schemas.recommendation import RecommendationResponse


class Location(BaseModel):
    """Geographic location coordinates."""

    latitude: float = Field(..., description="Latitude coordinate")
    longitude: float = Field(..., description="Longitude coordinate")
    lat: Optional[float] = Field(None, description="Latitude coordinate (alias)")
    lon: Optional[float] = Field(None, description="Longitude coordinate (alias)")

    model_config = ConfigDict(populate_by_name=True)


class FeederCurrentState(BaseModel):
    """Current operational parameters for a feeder."""

    load: float = Field(..., ge=0, description="Current load value")
    capacity: float = Field(..., gt=0, description="Total capacity value")
    voltage: float = Field(..., gt=0, description="Voltage level (per-unit)")


class FeederBase(BaseModel):
    """Base schema for power grid feeder entity."""

    id: str = Field(..., description="Unique feeder identifier (e.g., F07)")
    name: str = Field(..., description="Human-readable feeder name")
    capacity: float = Field(..., gt=0, description="Maximum operational capacity")
    current_load: float = Field(..., ge=0, description="Current active load level")
    voltage: float = Field(..., gt=0, description="Current per-unit voltage level")
    location: Location = Field(..., description="Geographic coordinates of the feeder")


class FeederResponse(FeederBase):
    """Feeder details response model."""

    pass


class FeederIntelligenceResponse(BaseModel):
    """Comprehensive feeder intelligence schema integrating current metrics, forecast, risk, and recommendations."""

    feeder_id: str = Field(..., description="Unique feeder identifier (e.g., F07)")
    current: FeederCurrentState = Field(..., description="Current operational state")
    location: Optional[Location] = Field(None, description="Geographic location of feeder")
    forecast: ForecastResponse = Field(..., description="15m, 30m, 45m, 60m load forecasts")
    risk: RiskInfo = Field(..., description="Risk assessment summary")
    contributors: list[RiskContributor] = Field(default_factory=list, description="Risk contributors breakdown")
    recommendation: RecommendationResponse = Field(..., description="Recommended mitigation actions and post-action state")

    model_config = ConfigDict(populate_by_name=True)
