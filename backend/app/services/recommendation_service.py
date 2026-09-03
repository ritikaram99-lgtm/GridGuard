"""Recommendation service orchestrating the prevention workflow for grid feeders.

Orchestrates feeder lookup, forecast peak evaluation, flexibility retrieval,
candidate action optimization, post-action load calculation, and status assignment.
For F01-F10: delegates directly to the real ML Action Engine (ml/src/action_engine.py).
"""

from typing import Optional
from app.schemas.recommendation import (
    ActionDetail,
    RecommendationResponse,
    RecommendationStatus,
)
from app.services.feeder_service import get_feeder_by_id
from app.services.db_service import record_actions
from app.services.ml_adapter_service import is_reserved_ml_feeder_id, ml_adapter_service
from app.services import (
    flexibility_service,
    forecast_service,
    optimization_service,
)


def map_action_engine_status(rec: dict) -> RecommendationStatus:
    """Map ML Action Engine output flags to RecommendationStatus enum."""
    if not rec.get("action_required", False):
        return RecommendationStatus.NO_ACTION_REQUIRED
    if rec.get("overload_avoided", False):
        return RecommendationStatus.PREVENTED

    total_red = rec.get("total_reduction_mw", 0.0)
    req_red = rec.get("required_reduction_mw", 0.0)
    max_feas = rec.get("max_feasible_reduction_mw", 0.0)

    if max_feas < req_red:
        return RecommendationStatus.INSUFFICIENT_FLEXIBILITY
    return RecommendationStatus.REDUCED_NOT_PREVENTED


def generate_recommendation(feeder_id: str, origin: Optional[str] = None) -> Optional[RecommendationResponse]:
    """Generate prevention recommendations for a specified grid feeder.

    Args:
        feeder_id (str): Feeder identifier (e.g. 'F06').
        origin (Optional[str]): Optional ISO forecast-origin timestamp,
            forwarded to the ML pipeline for F01-F10 so the recommendation is
            evaluated against the same forecast/risk snapshot as the rest of
            the UI. Ignored for legacy feeders.

    Returns:
        Optional[RecommendationResponse]: Recommendation details or None if feeder not found.

    Raises:
        ValueError: `origin` was given but is invalid/out-of-range for this feeder.
    """
    fid = feeder_id.upper()

    # 1. ML Feeder path (F01-F10) -> Real ML Prevention Engine
    if is_reserved_ml_feeder_id(fid):
        if not ml_adapter_service.is_available():
            raise ValueError("ML adapter is not available. Reserved ML feeders (F01-F10) do not fall back to legacy mock data.")

        prev = ml_adapter_service.get_feeder_prevention(fid, origin_datetime=origin)
        status = RecommendationStatus(prev["prevention_status"])

        actions_list = [a["resource"] for a in prev.get("recommended_actions", [])]
        action_details = [
            ActionDetail(
                action_type=a["resource"],
                load_reduction=a["applied_mw"],
                duration_hours=a.get("applied_duration_hours", a.get("duration_hours")),
                cost=a.get("disruption_cost", 0.0),
                disruption=a.get("disruption_cost", 0.0),
            )
            for a in prev.get("recommended_actions", [])
        ]

        cap = float(ml_adapter_service._capacities.loc[fid, "capacity_mw"]) if ml_adapter_service.is_available() else 100.0

        return RecommendationResponse(
            feeder_id=prev["feeder_id"],
            origin_timestamp=prev.get("origin_timestamp"),
            predicted_load=prev["baseline_load_mw"],
            capacity=cap,
            required_reduction=prev.get("required_reduction_mw", 0.0),
            actions=actions_list,
            recommended_actions=actions_list,
            predicted_after=prev["projected_load_mw"],
            expected_load_after=prev["projected_load_mw"],
            status=status,
            action_details=action_details,
            baseline_risk_level=prev.get("baseline_risk"),
            projected_risk_level=prev.get("projected_risk"),
            baseline_stress_score=prev.get("baseline_stress_score"),
            projected_stress_score=prev.get("projected_stress_score"),
            overload_avoided=prev.get("overload_avoided"),
            action_required=bool(prev.get("prevention_status") != "NO_ACTION_REQUIRED"),
            intervention_cost=prev.get("intervention_cost"),
            reason=prev.get("reason"),
            candidates_evaluated=prev.get("candidates_evaluated"),
            source="ml_prevention_engine",
            alternatives=prev.get("alternatives", []),
        )

    # 2. Legacy feeder path (e.g. F12)
    feeder = get_feeder_by_id(feeder_id)
    if not feeder:
        return None

    # Retrieve forecast
    forecast = forecast_service.get_forecast(feeder_id, origin=origin)
    if not forecast:
        return None

    # Determine forecast peak
    forecast_peak = forecast_service.get_forecast_peak(forecast)

    # Calculate required load reduction
    required_reduction = optimization_service.calculate_required_reduction(
        forecast_peak, feeder.capacity
    )

    # No action required case (forecast_peak <= capacity)
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
            source="legacy_optimization",
        )

    # Retrieve available flexibility resources
    resources = flexibility_service.get_feeder_flexibility(feeder_id)

    # Optimize & select best feasible action combination
    best_combination = optimization_service.select_best_action(resources, required_reduction)

    # Insufficient flexibility case
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
            source="legacy_optimization",
        )

    # Calculate predicted load after action
    predicted_after = forecast_peak - best_combination.total_reduction

    # Determine status
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
        source="legacy_optimization",
    )
