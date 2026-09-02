from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Restricted risk level classifications."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskContributor(BaseModel):
    """Factor contributing to grid stress/risk."""

    name: str = Field(..., description="Contributor name (e.g., EV demand, Temperature)")
    impact: float = Field(..., description="Impact value or score contribution")


class RiskInfo(BaseModel):
    """Risk summary schema for grid feeder state."""

    score: float = Field(..., ge=0, le=100, description="Stress score ranging from 0 to 100")
    level: RiskLevel = Field(..., description="Risk level classification")
    time_to_overload: Optional[float] = Field(None, description="Estimated time to overload in minutes")


class DetailedRiskResponse(RiskInfo):
    """Detailed risk response including specific contributors."""

    contributors: list[RiskContributor] = Field(default_factory=list, description="List of active risk contributors")
