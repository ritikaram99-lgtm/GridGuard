"""Database status and summary API route handlers."""

from fastapi import APIRouter
from app.db.database import check_db_connection
from app.schemas.db import DatabaseStatusResponse, DatabaseSummaryResponse
from app.services.db_service import get_db_summary

router = APIRouter(
    prefix="/api/db",
    tags=["Database"],
)


@router.get("/status", response_model=DatabaseStatusResponse)
def get_db_status() -> DatabaseStatusResponse:
    """Check connectivity status of the PostgreSQL database engine."""
    is_connected = check_db_connection(force=True)
    return DatabaseStatusResponse(
        database="postgresql",
        connected=is_connected,
    )


@router.get("/summary", response_model=DatabaseSummaryResponse)
def get_db_summary_route() -> DatabaseSummaryResponse:
    """Retrieve row count statistics for database tables directly from PostgreSQL."""
    counts = get_db_summary()
    return DatabaseSummaryResponse(**counts)
