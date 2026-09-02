"""Simulation API route handlers."""

from fastapi import APIRouter, HTTPException
from app.schemas.simulation import SimulationRequest, SimulationResponse
from app.services import simulation_service

router = APIRouter(
    prefix="/api/simulate",
    tags=["Simulation"],
)


@router.post("", response_model=SimulationResponse)
@router.post("/", response_model=SimulationResponse, include_in_schema=False)
def run_simulation(request: SimulationRequest) -> SimulationResponse:
    """Run counterfactual what-if simulation for a specified grid feeder and action parameters."""
    try:
        result = simulation_service.simulate_feeder(request.feeder_id, request.changes)
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Feeder {request.feeder_id} not found",
            )
        return result
    except ValueError as err:
        raise HTTPException(
            status_code=400,
            detail=str(err),
        )
