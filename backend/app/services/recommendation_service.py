"""Recommendation service orchestrating the prevention workflow for grid feeders.

Orchestrates feeder lookup, forecast peak evaluation, flexibility retrieval,
candidate action optimization, post-action load calculation, and status assignment.
Persists recommended actions to PostgreSQL when connected.
"""

from typing import Optional
from app.schemas.recommendation import (
    RecommendationResponse,
    RecommendationStatus,
)
from app.services.feeder_service import get_feeder_by_id
from app.services.db_service import record_actions
from app.services import (
    flexibility_service,
    forecast_service,
    optimization_service,
)


def generate_recommendation(feeder_id: str) -> Optional[RecommendationResponse]:
    """Generate prevention recommendations for a specified grid feeder.

    Args:
        feeder_id (str): Feeder identifier (e.g. 'F07').

    Returns:
        Optional[RecommendationResponse]: Recommendation details or None if feeder not found.
    """
    # 1. Retrieve feeder
    feeder = get_feeder_by_id(feeder_id)
    if not feeder:
        return None

    # 2. Retrieve forecast
    forecast = forecast_service.get_forecast(feeder_id)
    if not forecast:
        return None

    # 3. Determine forecast peak
    forecast_peak = max(forecast.m15, forecast.m30, forecast.m45, forecast.m60)

    # 4. Calculate required load reduction
    required_reduction = optimization_service.calculate_required_reduction(
        forecast_peak, feeder.capacity
    )

    # 17. No action required case (forecast_peak <= capacity)
    if required_reduction <= 0:
        return RecommendationResponse(
            feeder_id=feeder.id,
            predicted_load=forecast_peak,
            capacity=feeder.capacity,
            required_reduction=0.0,
            actions=[],
            recommended_actions=[],
            predicted_after=forecast_peak,
            expected_load_after=forecast_peak,
            status=RecommendationStatus.SAFE,
            action_details=[],
        )

    # 5. Retrieve available flexibility resources
    resources = flexibility_service.get_feeder_flexibility(feeder_id)

    # 6-8. Optimize & select best feasible action combination
    best_combination = optimization_service.select_best_action(resources, required_reduction)

    # 18. Insufficient flexibility case
    if not best_combination:
        total_avail = sum(r.max_reduction for r in resources)
        predicted_after = forecast_peak - total_avail
        return RecommendationResponse(
            feeder_id=feeder.id,
            predicted_load=forecast_peak,
            capacity=feeder.capacity,
            required_reduction=required_reduction,
            actions=[],
            recommended_actions=[],
            predicted_after=max(predicted_after, 0.0),
            expected_load_after=max(predicted_after, 0.0),
            status=RecommendationStatus.OVERLOAD,
            action_details=[],
        )

    # 9. Calculate predicted load after action
    predicted_after = forecast_peak - best_combination.total_reduction

    # 12. Determine status
    if predicted_after <= feeder.capacity and forecast_peak > feeder.capacity:
        status = RecommendationStatus.OVERLOAD_AVOIDED
    elif predicted_after <= feeder.capacity:
        status = RecommendationStatus.SAFE
    else:
        status = RecommendationStatus.OVERLOAD

    # Persist recommended actions to DB (non-blocking)
    try:
        record_actions(feeder.id, best_combination.actions)
    except Exception:
        pass

    return RecommendationResponse(
        feeder_id=feeder.id,
        predicted_load=forecast_peak,
        capacity=feeder.capacity,
        required_reduction=required_reduction,
        actions=best_combination.action_names,
        recommended_actions=best_combination.action_names,
        predicted_after=predicted_after,
        expected_load_after=predicted_after,
        status=status,
        action_details=best_combination.actions,
    )
