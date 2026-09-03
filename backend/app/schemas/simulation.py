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

    feeder_id: str = Field(..., description="Target feeder identifier (e.g., F06)")
    origin: Optional[str] = Field(None, description="Optional ISO forecast-origin timestamp")
    changes: ScenarioChanges = Field(..., description="Hypothetical action changes to apply")


class SimulationResponse(BaseModel):
    """Response payload representing what-if simulation outcomes."""

    feeder_id: str = Field(..., description="Target feeder identifier")
    origin_timestamp: Optional[str] = Field(None, description="ISO forecast-origin timestamp")
    forecast_peak: float = Field(..., ge=0, description="Baseline forecasted peak load before interventions")
    capacity: float = Field(..., gt=0, description="Feeder maximum capacity in MW")
    changes: ScenarioChanges = Field(..., description="Applied what-if action changes")
    total_reduction: float = Field(..., ge=0, description="Total requested MW reduction")
    simulated_load: float = Field(..., ge=0, description="Predicted peak load after applying actions")
    status: RecommendationStatus = Field(..., description="Operational status after actions")

    # Real ML Simulation Engine outputs
    baseline_risk: Optional[str] = Field(None, description="Baseline risk level before scenario/intervention")
    baseline_stress_score: Optional[float] = Field(None, description="Baseline stress score")
    baseline_time_to_overload: Optional[float] = Field(None, description="Time to overload in hours for the baseline trajectory (before scenario adjustments); null if no crossing is predicted")
    scenario_risk: Optional[str] = Field(None, description="Risk level after scenario adjustments (weather/EV/solar)")
    scenario_stress_score: Optional[float] = Field(None, description="Stress score after scenario adjustments")
    scenario_time_to_overload: Optional[float] = Field(None, description="Time to overload in hours for the scenario trajectory (after weather/EV/solar adjustments, before any intervention); null if no crossing is predicted")
    final_risk: Optional[str] = Field(None, description="Final risk level after intervention")
    final_stress_score: Optional[float] = Field(None, description="Final stress score after intervention")
    final_time_to_overload: Optional[float] = Field(None, description="Time to overload in hours after any applied intervention actions (equals scenario_time_to_overload when no actions are applied); null if no crossing is predicted")
    overload_before: Optional[bool] = Field(None, description="Whether baseline trajectory breached capacity")
    overload_after_scenario: Optional[bool] = Field(None, description="Whether scenario trajectory breached capacity")
    overload_after: Optional[bool] = Field(None, description="Whether post-intervention trajectory breached capacity")
    overload_avoided: Optional[bool] = Field(None, description="Whether intervention avoided scenario overload")
    load_change_mw: Optional[dict] = Field(None, description="Exact per-variable load change attribution")
    actions_applied: Optional[list[dict]] = Field(None, description="Applied resource actions with MW and duration")
    source: Optional[str] = Field(None, description="Simulation engine source ('ml_simulation_engine' or 'legacy_simulation')")

    # Optional schema extensions for detailed compatibility
    without_action_forecast: Optional[ForecastResponse] = None
    with_action_forecast: Optional[ForecastResponse] = None
    risk: Optional[RiskInfo] = None
    recommendation: Optional[RecommendationResponse] = None
    final_status: Optional[RecommendationStatus] = None

    model_config = ConfigDict(populate_by_name=True)
