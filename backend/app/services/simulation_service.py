"""Simulation service providing what-if counterfactual load trajectory analysis.

Calculates forecasted peak load changes, total reduction, post-action load,
and resulting operational status based on caller-specified hypothetical action parameters.
"""

from typing import Optional
from app.schemas.recommendation import RecommendationStatus
from app.schemas.simulation import ScenarioChanges, SimulationResponse
from app.services import (
    feeder_service,
    flexibility_service,
    forecast_service,
)


def simulate_feeder(feeder_id: str, changes: ScenarioChanges) -> Optional[SimulationResponse]:
    """Run what-if counterfactual simulation for a feeder with specified action reductions.

    Args:
        feeder_id (str): Feeder identifier (e.g. 'F07').
        changes (ScenarioChanges): Specified action reduction values.

    Returns:
        Optional[SimulationResponse]: Simulation result model or None if feeder not found.

    Raises:
        ValueError: If action values are negative or exceed resource limits.
    """
    # 1. Validate feeder existence
    feeder = feeder_service.get_feeder_by_id(feeder_id)
    if not feeder:
        return None

    # 2. Obtain current forecast and peak load
    forecast = forecast_service.get_forecast(feeder_id)
    if not forecast:
        return None

    forecast_peak = forecast_service.get_forecast_peak(forecast)

    # 3. Retrieve available flexibility resources and constraints
    resources = flexibility_service.get_feeder_flexibility(feeder_id)
    resource_limits = {r.action_type.upper(): r.max_reduction for r in resources}

    # 4. Validate requested action parameters
    # Check negative values
    if changes.ev_shift < 0:
        raise ValueError("EV_SHIFT reduction cannot be negative")
    if changes.battery < 0:
        raise ValueError("BATTERY reduction cannot be negative")
    if changes.industrial < 0:
        raise ValueError("INDUSTRIAL reduction cannot be negative")

    # Check maximum allowed reduction limits per resource type
    max_ev = resource_limits.get("EV_SHIFT", 0.0)
    if changes.ev_shift > max_ev:
        raise ValueError(
            f"EV_SHIFT reduction ({changes.ev_shift} MW) exceeds maximum available limit ({max_ev} MW) for feeder {feeder_id}"
        )

    max_bat = resource_limits.get("BATTERY", 0.0)
    if changes.battery > max_bat:
        raise ValueError(
            f"BATTERY reduction ({changes.battery} MW) exceeds maximum available limit ({max_bat} MW) for feeder {feeder_id}"
        )

    max_ind = resource_limits.get("INDUSTRIAL", 0.0)
    if changes.industrial > max_ind:
        raise ValueError(
            f"INDUSTRIAL reduction ({changes.industrial} MW) exceeds maximum available limit ({max_ind} MW) for feeder {feeder_id}"
        )

    # 5. Calculate total reduction and simulated load
    total_reduction = changes.ev_shift + changes.battery + changes.industrial
    simulated_load = max(forecast_peak - total_reduction, 0.0)

    # 6. Determine operational status
    if forecast_peak <= feeder.capacity:
        status = RecommendationStatus.SAFE
    elif simulated_load <= feeder.capacity:
        status = RecommendationStatus.OVERLOAD_AVOIDED
    else:
        status = RecommendationStatus.OVERLOAD

    return SimulationResponse(
        feeder_id=feeder.id,
        forecast_peak=forecast_peak,
        capacity=feeder.capacity,
        changes=changes,
        total_reduction=total_reduction,
        simulated_load=simulated_load,
        status=status,
        final_status=status,
    )
