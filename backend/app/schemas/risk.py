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
    time_to_overload: Optional[float] = Field(
        None,
        description=(
            "Estimated time to overload in minutes. For source='ml_stress_engine' this is an hourly-resolution "
            "estimate (hours * 60) -- see time_to_overload_hours for the true, unconverted resolution."
        ),
    )
    time_to_overload_hours: Optional[float] = Field(
        None,
        description=(
            "Time to overload in hours, from ml/src/stress_engine.py's time_to_overload (linear interpolation "
            "between hourly trajectory points). Only populated when source='ml_stress_engine'."
        ),
    )
    source: Optional[str] = Field(
        None,
        description=(
            "'ml_stress_engine' when computed by the real, deterministic ml/src/stress_engine.py over the "
            "feeder's own ML-allocated hourly forecast (F01-F10); 'legacy_formula' for the backend's own "
            "boolean-trigger scoring (non-ML feeders, or when the ML adapter is unavailable)."
        ),
    )


class DetailedRiskResponse(RiskInfo):
    """Detailed risk response including specific contributors."""

    contributors: list[RiskContributor] = Field(default_factory=list, description="List of active risk contributors")
