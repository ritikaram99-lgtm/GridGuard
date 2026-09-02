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
    """Response payload following operator dispatch execution."""

    feeder_id: str = Field(..., description="Feeder ID")
    status: str = Field(..., description="Overall dispatch status ('DISPATCHED', 'REJECTED', 'INVALID')")
    forecast_peak: float = Field(..., description="Current ML forecast peak load in MW")
    capacity: float = Field(..., description="Feeder capacity in MW")
    total_reduction: float = Field(..., description="Total load reduction dispatched in MW")
    simulated_load: float = Field(..., description="Simulated load after dispatch in MW")
    overload_avoided: bool = Field(..., description="Flag indicating whether simulated load is at or below capacity")
    actions: List[DispatchedActionDetail] = Field(..., description="List of dispatched action details")

    model_config = ConfigDict(populate_by_name=True)
