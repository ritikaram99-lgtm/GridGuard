"""Pydantic schemas for action dispatch requests and responses."""

from typing import List
from pydantic import BaseModel, ConfigDict, Field


class DispatchActionItem(BaseModel):
    """Requested flexibility dispatch action item."""

    action_type: str = Field(..., description="Action type ('EV_SHIFT', 'BATTERY', or 'INDUSTRIAL')")
    reduction_mw: float = Field(..., description="Requested load reduction in MW (>= 0)")

    model_config = ConfigDict(populate_by_name=True)


class DispatchRequest(BaseModel):
    """Payload for operator flexibility action dispatch."""

    feeder_id: str = Field(..., description="Target feeder identifier (e.g. 'F07')")
    actions: List[DispatchActionItem] = Field(..., description="List of flexibility actions to dispatch")

    model_config = ConfigDict(populate_by_name=True)


class DispatchedActionDetail(BaseModel):
    """Detail for a successfully dispatched action."""

    action_type: str = Field(..., description="Action type ('EV_SHIFT', 'BATTERY', or 'INDUSTRIAL')")
    reduction_mw: float = Field(..., description="Dispatched reduction in MW")
    status: str = Field("DISPATCHED", description="Dispatch status ('DISPATCHED')")

    model_config = ConfigDict(populate_by_name=True)


class DispatchResponse(BaseModel):
    """Response payload following operator dispatch decision confirmation."""

    feeder_id: str = Field(..., description="Feeder ID")
    origin_timestamp: str | None = Field(None, description="ISO forecast-origin timestamp")
    status: str = Field(..., description="Overall dispatch status ('DECISION_CONFIRMED', 'DISPATCHED', 'REJECTED', 'INVALID')")
    forecast_peak: float = Field(..., description="Current ML forecast peak load in MW")
    capacity: float = Field(..., description="Feeder capacity in MW")
    total_reduction: float = Field(..., description="Total load reduction dispatched in MW")
    simulated_load: float = Field(..., description="Simulated load after dispatch in MW")
    overload_avoided: bool = Field(..., description="Flag indicating whether simulated load is at or below capacity")
    actions: List[DispatchedActionDetail] = Field(..., description="List of dispatched action details")

    # Real ML Prevention Engine decision-support fields
    baseline_risk: str | None = Field(None, description="Baseline risk level before intervention")
    final_risk: str | None = Field(None, description="Final risk level after intervention")
    baseline_stress_score: float | None = Field(None, description="Baseline stress score before intervention")
    final_stress_score: float | None = Field(None, description="Final stress score after intervention")
    prevention_status: str | None = Field(None, description="Prevention Engine outcome status")
    disclaimer: str | None = Field(
        "Decision-support simulation only -- no physical grid hardware control commands sent.",
        description="Explicit non-hardware-dispatch notice",
    )
    source: str | None = Field(None, description="Source engine ('ml_prevention_engine' or 'legacy_dispatch')")

    model_config = ConfigDict(populate_by_name=True)
