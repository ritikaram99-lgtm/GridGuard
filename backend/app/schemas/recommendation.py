from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class RecommendationStatus(str, Enum):
    """Recommendation outcome statuses."""

    NO_ACTION_REQUIRED = "NO_ACTION_REQUIRED"
    PREVENTED = "PREVENTED"
    REDUCED_NOT_PREVENTED = "REDUCED_NOT_PREVENTED"
    INSUFFICIENT_FLEXIBILITY = "INSUFFICIENT_FLEXIBILITY"
    DURATION_LIMITED = "DURATION_LIMITED"

    # Legacy back-compat aliases
    SAFE = "SAFE"
    OVERLOAD = "OVERLOAD"
    OVERLOAD_AVOIDED = "OVERLOAD_AVOIDED"


class ActionDetail(BaseModel):
    """Representation of an available or recommended mitigation action."""

    action_type: str = Field(..., description="Action type identifier (e.g., EV, BATTERY, INDUSTRIAL)")
    load_reduction: float = Field(..., ge=0, description="Expected load reduction in MW")
    duration_hours: Optional[float] = Field(None, ge=0, description="Duration in hours for which action is deployed")
    cost: float = Field(..., ge=0, description="Estimated disruption cost index")
    disruption: float = Field(..., description="Quantified level of operational disruption")


class RecommendationResponse(BaseModel):
    """Recommendation schema containing proposed actions, load parameters, and expected outcome status."""

    feeder_id: Optional[str] = Field(None, description="Feeder identifier (e.g., F06)")
    origin_timestamp: Optional[str] = Field(None, description="ISO forecast-origin timestamp")
    predicted_load: Optional[float] = Field(None, ge=0, description="Original predicted peak load before intervention")
    capacity: Optional[float] = Field(None, gt=0, description="Feeder maximum capacity in MW")
    required_reduction: Optional[float] = Field(0.0, ge=0, description="Required load reduction in MW")
    actions: list[str] = Field(default_factory=list, description="List of recommended action identifiers")
    recommended_actions: Optional[list[str]] = Field(None, description="Alias for recommended actions list")
    predicted_after: float = Field(..., ge=0, description="Predicted peak load after applying recommendations")
    expected_load_after: Optional[float] = Field(None, description="Alias for predicted_after load")
    status: RecommendationStatus = Field(..., description="Expected operational status following mitigation")
    action_details: Optional[list[ActionDetail]] = Field(None, description="Detailed action parameters breakdown")
    baseline_risk_level: Optional[str] = Field(None, description="Baseline risk level before action")
    projected_risk_level: Optional[str] = Field(None, description="Projected risk level after action")
    baseline_stress_score: Optional[float] = Field(None, description="Baseline stress score before action")
    projected_stress_score: Optional[float] = Field(None, description="Projected stress score after action")
    overload_avoided: Optional[bool] = Field(None, description="Whether overload was prevented")
    action_required: Optional[bool] = Field(None, description="Whether intervention was required")
    intervention_cost: Optional[float] = Field(None, description="Total disruption cost of deployed actions")
    reason: Optional[str] = Field(None, description="Explanation and operational rationale")
    candidates_evaluated: Optional[int] = Field(None, description="Number of non-null candidate combinations tested")
    prevention_status: Optional[str] = Field(None, description="Exact Prevention Engine status string")
    source: Optional[str] = Field(None, description="Source of recommendation ('ml_prevention_engine', 'ml_action_engine', 'legacy_optimization')")
    alternatives: Optional[list[dict]] = Field(None, description="Evaluated candidate combinations")

    model_config = ConfigDict(populate_by_name=True)
