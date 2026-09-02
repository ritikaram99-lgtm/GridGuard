"""Business logic services package."""

from app.services.feeder_service import get_all_feeders, get_feeder_by_id
from app.services.forecast_service import get_forecast
from app.services.risk_service import calculate_feeder_risk, classify_risk, calculate_time_to_overload
from app.services.flexibility_service import get_feeder_flexibility
from app.services.optimization_service import (
    calculate_required_reduction,
    generate_candidate_combinations,
    select_best_action,
)
from app.services.recommendation_service import generate_recommendation
from app.services.simulation_service import simulate_feeder
from app.services.intelligence_service import get_feeder_intelligence
from app.services.gemini_service import generate_copilot_explanation
from app.services.copilot_service import get_copilot_explanation
from app.services.ml_forecast_service import MLForecastService, ml_service
from app.services.db_service import (
    seed_feeders_if_needed,
    record_measurement,
    record_predictions,
    record_alert,
    record_actions,
    record_dispatched_actions,
    get_db_summary,
)
from app.services.replay_service import ReplayService, replay_service
from app.services.dispatch_service import DispatchService, dispatch_service
from app.services.demo_service import DemoService, demo_service

__all__ = [
    "get_all_feeders",
    "get_feeder_by_id",
    "get_forecast",
    "calculate_feeder_risk",
    "classify_risk",
    "calculate_time_to_overload",
    "get_feeder_flexibility",
    "calculate_required_reduction",
    "generate_candidate_combinations",
    "select_best_action",
    "generate_recommendation",
    "simulate_feeder",
    "get_feeder_intelligence",
    "generate_copilot_explanation",
    "get_copilot_explanation",
    "MLForecastService",
    "ml_service",
    "seed_feeders_if_needed",
    "record_measurement",
    "record_predictions",
    "record_alert",
    "record_actions",
    "record_dispatched_actions",
    "get_db_summary",
    "ReplayService",
    "replay_service",
    "DispatchService",
    "dispatch_service",
    "DemoService",
    "demo_service",
]
