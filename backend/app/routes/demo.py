"""End-to-End Demo Scenario API route handler."""

from fastapi import APIRouter, HTTPException, status
from app.schemas.demo import DemoScenarioResponse
from app.services.demo_service import demo_service

router = APIRouter(
    prefix="/api/demo",
    tags=["Demo Scenario"],
)


@router.get("/{feeder_id}", response_model=DemoScenarioResponse)
def get_demo_scenario(feeder_id: str) -> DemoScenarioResponse:
    """Execute end-to-end hackathon demo scenario pipeline for a specified feeder.

    DISCLAIMER: All dispatches and simulations in this scenario are simulated for demonstration purposes
    and do NOT control physical electrical grid hardware or external utility infrastructure.
    """
    try:
        return demo_service.run_demo_scenario(feeder_id)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )
