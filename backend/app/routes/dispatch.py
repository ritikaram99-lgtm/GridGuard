"""Action Dispatch API route handler."""

from fastapi import APIRouter, HTTPException, status
from app.schemas.dispatch import DispatchRequest, DispatchResponse
from app.services.dispatch_service import dispatch_service

router = APIRouter(
    prefix="/api/dispatch",
    tags=["Dispatch Simulation"],
)


@router.post("", response_model=DispatchResponse)
def dispatch_flexibility_actions(request: DispatchRequest) -> DispatchResponse:
    """Execute simulated operator flexibility action dispatch.

    DISCLAIMER: Dispatch in GridGuard AI is a SAFE DEMONSTRATION / SIMULATION action only.
    It does NOT control physical grid hardware or external utility infrastructure.
    """
    try:
        return dispatch_service.process_dispatch(request)
    except ValueError as err:
        msg = str(err)
        if "not found" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=msg,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg,
        )
