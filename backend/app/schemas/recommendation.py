from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class RecommendationStatus(str, Enum):
    """Restricted recommendation outcome statuses."""

    SAFE = "SAFE"
    OVERLOAD = "OVERLOAD"
    OVERLOAD_AVOIDED = "OVERLOAD_AVOIDED"


class ActionDetail(BaseModel):
    """Representation of an available mitigation action."""

    action_type: str = Field(..., description="Action type identifier (e.g., EV_SHIFT, BATTERY, INDUSTRIAL)")
    load_reduction: float = Field(..., ge=0, description="Expected load reduction in MW")
    cost: float = Field(..., ge=0, description="Estimated financial cost")
    disruption: float = Field(..., description="Quantified level of operational disruption")


class RecommendationResponse(BaseModel):
    """Recommendation schema containing proposed actions, load parameters, and expected outcome status."""

    feeder_id: Optional[str] = Field(None, description="Feeder identifier (e.g., F07)")
    predicted_load: Optional[float] = Field(None, ge=0, description="Original predicted peak load before intervention")
    capacity: Optional[float] = Field(None, gt=0, description="Feeder maximum capacity in MW")
    required_reduction: Optional[float] = Field(0.0, ge=0, description="Required load reduction in MW")
    actions: list[str] = Field(default_factory=list, description="List of recommended action identifiers")
    recommended_actions: Optional[list[str]] = Field(None, description="Alias for recommended actions list")
    predicted_after: float = Field(..., ge=0, description="Predicted load after applying recommendations")
    expected_load_after: Optional[float] = Field(None, description="Alias for predicted_after load")
    status: RecommendationStatus = Field(..., description="Expected operational status following mitigation")
    action_details: Optional[list[ActionDetail]] = Field(None, description="Detailed action parameters breakdown")

    model_config = ConfigDict(populate_by_name=True)
