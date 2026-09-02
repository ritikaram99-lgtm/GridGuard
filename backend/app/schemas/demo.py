"""Pydantic schemas for end-to-end hackathon demo scenario orchestration."""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.feeder import FeederResponse
from app.schemas.forecast import ForecastResponse
from app.schemas.risk import DetailedRiskResponse
from app.schemas.recommendation import RecommendationResponse
from app.schemas.simulation import SimulationResponse
from app.schemas.dispatch import DispatchResponse
from app.schemas.copilot import CopilotResponse


class DemoOutcome(BaseModel):
    """Calculated operational outcome summary for the demo scenario."""

    scenario_name: str = Field("F07_OVERLOAD_PREVENTION", description="Scenario title")
    before_load_mw: float = Field(..., description="Peak forecasted load before mitigation (MW)")
    after_load_mw: float = Field(..., description="Simulated load after mitigation (MW)")
    overload_before: bool = Field(..., description="Flag indicating whether overload was predicted initially")
    overload_after: bool = Field(..., description="Flag indicating whether overload remains after mitigation")
    overload_avoided: bool = Field(..., description="Flag indicating whether overload was successfully avoided")
    status_message: str = Field(..., description="Outcome classification ('OVERLOAD_PREVENTED' or 'NO_OVERLOAD_DETECTED')")

    model_config = ConfigDict(populate_by_name=True)


class DemoScenarioResponse(BaseModel):
    """Unified payload exposing the end-to-end operational pipeline story."""

    scenario: str = Field("F07_OVERLOAD_PREVENTION", description="Scenario identifier")
    feeder_id: str = Field(..., description="Target feeder ID")
    feeder: FeederResponse = Field(..., description="Baseline feeder specifications")
    forecast: ForecastResponse = Field(..., description="Real ML load forecast predictions")
    risk: DetailedRiskResponse = Field(..., description="Calculated stress risk analysis")
    recommendation: RecommendationResponse = Field(..., description="Automated multi-criteria recommendations")
    simulation: SimulationResponse = Field(..., description="Counterfactual scenario simulation")
    dispatch: Optional[DispatchResponse] = Field(None, description="Controlled operator action dispatch outcome")
    copilot: CopilotResponse = Field(..., description="AI Copilot natural-language operational explanation")
    outcome: DemoOutcome = Field(..., description="Final operational outcome assessment")

    model_config = ConfigDict(populate_by_name=True)
