"""Dispatch service managing controlled simulated flexibility action dispatches.

Validates requested actions against available feeder flexibility resource limits,
calculates post-dispatch simulated feeder load using current ML forecasts, and persists
dispatched action records to PostgreSQL via the Step 13 persistence layer.

DISCLAIMER: Dispatch in GridGuard AI is a SAFE DEMONSTRATION / SIMULATION action only.
It does NOT send control signals to physical grid hardware or external utility APIs.
"""

import logging
from typing import Optional
from app.schemas.dispatch import (
    DispatchActionItem,
    DispatchedActionDetail,
    DispatchRequest,
    DispatchResponse,
)
from app.services.db_service import record_dispatched_actions
from app.services.feeder_service import get_feeder_by_id
from app.services import flexibility_service, forecast_service

logger = logging.getLogger(__name__)


class DispatchService:
    """Service for handling controlled operator action dispatch simulations."""

    _instance: Optional["DispatchService"] = None

    @classmethod
    def get_instance(cls) -> "DispatchService":
        """Retrieve singleton instance of DispatchService."""
        if cls._instance is None:
            cls._instance = DispatchService()
        return cls._instance

    def process_dispatch(self, request: DispatchRequest) -> DispatchResponse:
        """Execute and validate operator dispatch request.

        Args:
            request (DispatchRequest): Operator dispatch payload.

        Returns:
            DispatchResponse: Outcome schema with post-dispatch simulated metrics.

        Raises:
            ValueError: If feeder is unknown, actions are empty, action type is invalid, or reduction exceeds max limit.
        """
        fid = request.feeder_id.upper()
        feeder = get_feeder_by_id(fid)
        if not feeder:
            raise ValueError(f"Feeder '{request.feeder_id}' not found.")

        if not request.actions:
            raise ValueError("Actions list cannot be empty.")

        # Retrieve available flexibility resources for this feeder
        flex_resources = flexibility_service.get_feeder_flexibility(fid)
        flex_map = {res.action_type: res.max_reduction for res in flex_resources}

        dispatched_details: list[DispatchedActionDetail] = []
        total_reduction = 0.0

        for item in request.actions:
            act_type = item.action_type.upper()
            if act_type not in flex_map:
                raise ValueError(f"Unsupported action type '{item.action_type}'. Supported actions: {list(flex_map.keys())}.")

            if item.reduction_mw < 0:
                raise ValueError(f"Reduction MW for action '{item.action_type}' must be non-negative (received {item.reduction_mw} MW).")

            max_avail = flex_map[act_type]
            if item.reduction_mw > max_avail:
                raise ValueError(
                    f"Requested reduction of {item.reduction_mw} MW for action '{item.action_type}' "
                    f"exceeds maximum available resource limit of {max_avail} MW."
                )

            total_reduction += item.reduction_mw
            dispatched_details.append(
                DispatchedActionDetail(
                    action_type=act_type,
                    reduction_mw=round(item.reduction_mw, 2),
                    status="DISPATCHED",
                )
            )

        # Retrieve current ML forecast peak for feeder
        forecast = forecast_service.get_forecast(fid)
        if forecast:
            forecast_peak = forecast_service.get_forecast_peak(forecast)
        else:
            forecast_peak = feeder.current_load

        capacity = feeder.capacity
        simulated_load = max(0.0, round(forecast_peak - total_reduction, 2))
        overload_avoided = bool(simulated_load <= capacity)

        # Record dispatched actions in PostgreSQL database (non-blocking)
        try:
            record_dispatched_actions(fid, dispatched_details)
        except Exception as err:
            logger.warning(f"Failed to persist dispatched actions to database: {err}")

        return DispatchResponse(
            feeder_id=feeder.id,
            status="DISPATCHED",
            forecast_peak=forecast_peak,
            capacity=capacity,
            total_reduction=round(total_reduction, 2),
            simulated_load=simulated_load,
            overload_avoided=overload_avoided,
            actions=dispatched_details,
        )


dispatch_service = DispatchService.get_instance()
