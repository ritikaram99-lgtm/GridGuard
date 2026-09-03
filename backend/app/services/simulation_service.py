"""Simulation service providing what-if counterfactual load trajectory analysis.

For F01-F10: delegates directly to the real ML Simulation Engine (ml/src/simulation_engine.py).
"""

from typing import Optional
from app.schemas.recommendation import RecommendationStatus
from app.schemas.simulation import ScenarioChanges, SimulationResponse
from app.services.ml_adapter_service import is_reserved_ml_feeder_id, ml_adapter_service
from app.services import (
    feeder_service,
    flexibility_service,
    forecast_service,
)


def simulate_feeder(feeder_id: str, changes: ScenarioChanges, origin: Optional[str] = None) -> Optional[SimulationResponse]:
    """Run what-if counterfactual simulation for a feeder with specified action reductions.

    Args:
        feeder_id (str): Feeder identifier (e.g. 'F06').
        changes (ScenarioChanges): Specified action reduction values and scenario adjustments.
        origin (Optional[str]): Optional ISO forecast-origin timestamp.

    Returns:
        Optional[SimulationResponse]: Simulation result model or None if feeder not found.

    Raises:
        ValueError: If origin is invalid or ML adapter is unavailable for F01-F10.
    """
    fid = feeder_id.upper()

    # 1. ML Feeder path (F01-F10) -> Real ML Simulation Engine
    if is_reserved_ml_feeder_id(fid):
        if not ml_adapter_service.is_available():
            raise ValueError("ML adapter is not available. Reserved ML feeders (F01-F10) do not fall back to legacy mock data.")

        sim_res = ml_adapter_service.get_feeder_simulation(
            fid,
            origin_datetime=origin,
            changes=changes.model_dump(),
        )

        total_reduction = float(sim_res.get("total_reduction_mw", 0.0))
        simulated_load = float(sim_res.get("final_peak_load_mw", sim_res.get("scenario_peak_load_mw", 0.0)))
        capacity = float(sim_res["capacity_mw"])
        forecast_peak = float(sim_res["baseline_peak_load_mw"])

        if sim_res.get("final_risk") in ("LOW", "MODERATE") or simulated_load <= capacity:
            if forecast_peak > capacity or sim_res.get("baseline_risk") in ("HIGH", "CRITICAL"):
                status = RecommendationStatus.PREVENTED
            else:
                status = RecommendationStatus.NO_ACTION_REQUIRED
        else:
            status = RecommendationStatus.REDUCED_NOT_PREVENTED

        return SimulationResponse(
            feeder_id=sim_res["feeder_id"],
            origin_timestamp=sim_res.get("origin_timestamp"),
            forecast_peak=forecast_peak,
            capacity=capacity,
            changes=changes,
            total_reduction=total_reduction,
            simulated_load=simulated_load,
            status=status,
            final_status=status,
            baseline_risk=sim_res.get("baseline_risk"),
            baseline_stress_score=sim_res.get("baseline_stress_score"),
            baseline_time_to_overload=sim_res.get("baseline_time_to_overload"),
            scenario_risk=sim_res.get("scenario_risk"),
            scenario_stress_score=sim_res.get("scenario_stress_score"),
            scenario_time_to_overload=sim_res.get("scenario_time_to_overload"),
            final_risk=sim_res.get("final_risk"),
            final_stress_score=sim_res.get("final_stress_score"),
            final_time_to_overload=sim_res.get("final_time_to_overload"),
            overload_before=sim_res.get("overload_before"),
            overload_after_scenario=sim_res.get("overload_after_scenario"),
            overload_after=sim_res.get("overload_after"),
            overload_avoided=sim_res.get("overload_avoided"),
            load_change_mw=sim_res.get("load_change_mw"),
            actions_applied=sim_res.get("actions_applied"),
            source="ml_simulation_engine",
        )

    # 2. Legacy feeder path (e.g. F12)
    feeder = feeder_service.get_feeder_by_id(feeder_id)
    if not feeder:
        return None

    # Obtain current forecast and peak load
    forecast = forecast_service.get_forecast(feeder_id, origin=origin)
    if not forecast:
        return None

    forecast_peak = forecast_service.get_forecast_peak(forecast)

    # Calculate total reduction and simulated load
    total_reduction = changes.ev_shift + changes.battery + changes.industrial
    simulated_load = max(forecast_peak - total_reduction, 0.0)

    # Determine operational status
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
        source="legacy_simulation",
    )
