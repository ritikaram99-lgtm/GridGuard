from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class CopilotExplanationSource(str, Enum):
    """Source classification for Copilot explanation payload."""

    GEMINI = "gemini"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


class CopilotResponse(BaseModel):
    """Response payload for GridGuard Copilot explanation layer."""

    feeder_id: str = Field(..., description="Unique feeder identifier (e.g., F07)")
    summary: str = Field(..., description="High-level operational situation summary")
    risk_explanation: str = Field(..., description="Explanation of risk assessment score and active contributors")
    recommended_action_explanation: str = Field(..., description="Explanation of recommended mitigation actions")
    expected_outcome: str = Field(..., description="Expected load trajectory and operational status following mitigation")
    operator_message: str = Field(..., description="Actionable directive for grid control operators")
    source: CopilotExplanationSource = Field(..., description="Origin of the explanation (gemini or deterministic_fallback)")

    model_config = ConfigDict(populate_by_name=True)
