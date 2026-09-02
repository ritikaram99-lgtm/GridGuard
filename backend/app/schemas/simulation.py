from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.forecast import ForecastResponse
from app.schemas.risk import RiskInfo
from app.schemas.recommendation import RecommendationResponse, RecommendationStatus


class ScenarioChanges(BaseModel):
    """Action reduction parameters and environmental adjustments for scenario simulation."""

    ev_shift: float = Field(0.0, description="EV shift load reduction in MW")
    battery: float = Field(0.0, description="Battery discharge load reduction in MW")
    industrial: float = Field(0.0, description="Industrial load reduction in MW")

    # Optional environmental parameters
    temperature: Optional[float] = Field(0.0, description="Temperature change in degrees Celsius")
    ev_demand_percent: Optional[float] = Field(0.0, description="Percentage change in EV charging demand")
    solar_percent: Optional[float] = Field(0.0, description="Percentage change in solar generation")


class SimulationRequest(BaseModel):
    """Request payload for counterfactual simulation."""

    feeder_id: str = Field(..., description="Target feeder identifier (e.g., F07)")
    changes: ScenarioChanges = Field(..., description="Hypothetical action changes to apply")


class SimulationResponse(BaseModel):
    """Response payload representing what-if simulation outcomes."""

    feeder_id: str = Field(..., description="Target feeder identifier")
    forecast_peak: float = Field(..., ge=0, description="Baseline forecasted peak load before interventions")
    capacity: float = Field(..., gt=0, description="Feeder maximum capacity in MW")
    changes: ScenarioChanges = Field(..., description="Applied what-if action changes")
    total_reduction: float = Field(..., ge=0, description="Total requested MW reduction")
    simulated_load: float = Field(..., ge=0, description="Predicted peak load after applying actions")
    status: RecommendationStatus = Field(..., description="Operational status after actions")

    # Optional schema extensions for detailed compatibility
    without_action_forecast: Optional[ForecastResponse] = None
    with_action_forecast: Optional[ForecastResponse] = None
    risk: Optional[RiskInfo] = None
    recommendation: Optional[RecommendationResponse] = None
    final_status: Optional[RecommendationStatus] = None

    model_config = ConfigDict(populate_by_name=True)
