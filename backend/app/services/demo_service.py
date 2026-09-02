"""End-to-End Hackathon Demo Orchestration Service for GridGuard AI.

Orchestrates real ML forecasting, stress risk assessment, multi-criteria recommendation,
counterfactual simulation, simulated operator dispatch, and AI Copilot explanations into a
coherent operational scenario without duplicating business logic.
"""

import logging
from typing import Optional
from app.schemas.demo import DemoOutcome, DemoScenarioResponse
from app.schemas.dispatch import DispatchActionItem, DispatchRequest
from app.schemas.simulation import ScenarioChanges
from app.services import (
    copilot_service,
    dispatch_service,
    feeder_service,
    forecast_service,
    recommendation_service,
    risk_service,
    simulation_service,
)

logger = logging.getLogger(__name__)


class DemoService:
    """Service orchestrating end-to-end hackathon demo pipeline execution."""

    _instance: Optional["DemoService"] = None

    @classmethod
    def get_instance(cls) -> "DemoService":
        """Retrieve singleton instance of DemoService."""
        if cls._instance is None:
            cls._instance = DemoService()
        return cls._instance

    def run_demo_scenario(self, feeder_id: str) -> DemoScenarioResponse:
        """Orchestrate full end-to-end pipeline for a specified feeder.

        Args:
            feeder_id (str): Feeder identifier (e.g., 'F07').

        Returns:
            DemoScenarioResponse: Consolidated story payload.

        Raises:
            ValueError: If feeder is not found.
        """
        fid = feeder_id.upper()
        feeder = feeder_service.get_feeder_by_id(fid)
        if not feeder:
            raise ValueError(f"Feeder '{feeder_id}' not found.")

        # 1. Retrieve ML Forecast
        forecast = forecast_service.get_forecast(fid)
        if not forecast:
            raise ValueError(f"Could not generate load forecast for feeder '{feeder_id}'.")

        # 2. Evaluate Grid Stress Risk
        risk = risk_service.calculate_feeder_risk(fid)
        if not risk:
            raise ValueError(f"Could not calculate risk for feeder '{feeder_id}'.")

        # 3. Generate Automated Recommendation
        recommendation = recommendation_service.generate_recommendation(fid)
        if not recommendation:
            raise ValueError(f"Could not generate recommendations for feeder '{feeder_id}'.")

        # 4. Map Recommendation to Counterfactual Simulation
        ev_mw = sum(act.load_reduction for act in recommendation.action_details if act.action_type == "EV_SHIFT")
        batt_mw = sum(act.load_reduction for act in recommendation.action_details if act.action_type == "BATTERY")
        ind_mw = sum(act.load_reduction for act in recommendation.action_details if act.action_type == "INDUSTRIAL")

        sim_changes = ScenarioChanges(
            ev_shift=ev_mw,
            battery=batt_mw,
            industrial=ind_mw,
        )
        simulation = simulation_service.simulate_feeder(fid, sim_changes)
        if not simulation:
            raise ValueError(f"Could not execute simulation for feeder '{feeder_id}'.")

        # 5. Map Recommendation to Operator Action Dispatch (if actions recommended)
        dispatch_res = None
        if recommendation.action_details:
            dispatch_items = [
                DispatchActionItem(action_type=act.action_type, reduction_mw=act.load_reduction)
                for act in recommendation.action_details
            ]
            disp_req = DispatchRequest(feeder_id=fid, actions=dispatch_items)
            dispatch_res = dispatch_service.process_dispatch(disp_req)

        # 6. Retrieve AI Copilot Operational Explanation
        copilot = copilot_service.get_copilot_explanation(fid)

        # 7. Evaluate Operational Outcome
        before_load = max(forecast.m15, forecast.m30, forecast.m45, forecast.m60)
        after_load = simulation.simulated_load
        capacity = feeder.capacity

        overload_before = bool(before_load > capacity)
        overload_after = bool(after_load > capacity)
        overload_avoided = bool(overload_before and not overload_after)

        if overload_avoided:
            status_msg = "OVERLOAD_PREVENTED"
        elif not overload_before:
            status_msg = "NO_OVERLOAD_DETECTED"
        else:
            status_msg = "OVERLOAD_REMAINS"

        outcome = DemoOutcome(
            scenario_name=f"{fid}_OVERLOAD_PREVENTION",
            before_load_mw=before_load,
            after_load_mw=after_load,
            overload_before=overload_before,
            overload_after=overload_after,
            overload_avoided=overload_avoided,
            status_message=status_msg,
        )

        return DemoScenarioResponse(
            scenario=f"{fid}_OVERLOAD_PREVENTION",
            feeder_id=feeder.id,
            feeder=feeder,
            forecast=forecast,
            risk=risk,
            recommendation=recommendation,
            simulation=simulation,
            dispatch=dispatch_res,
            copilot=copilot,
            outcome=outcome,
        )


demo_service = DemoService.get_instance()
