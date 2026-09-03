"""Feeder service providing grid feeder data.

DISCLAIMER: The feeder data in this service consists of SIMULATED DEMO DATA
used for demonstration and development purposes. It must not be presented as
real grid measurement data.

IDENTITY BOUNDARY (important): F01-F10 are permanently RESERVED for the real
ML pipeline's 10-feeder synthetic allocation layer (ml/src/feeder_generator.py,
driven by the real national demand forecast via ml_adapter_service). These 10
ids are NEVER answered from MOCK_FEEDERS below, even when the ML adapter is
unavailable -- doing so would silently substitute an unrelated legacy
Bangalore-scale feeder for a Panama ML feeder of the same id, which is
exactly the kind of identity leak this project's contract audit flagged.
When ML is unavailable, F01-F10 are honestly "not found" (404), not
backfilled with mock data. MOCK_FEEDERS now holds only the one genuinely
legacy, non-colliding id ('F12'), always served from mock data regardless of
ML availability.
"""

import logging
from typing import Optional
from app.schemas.feeder import FeederResponse, Location
from app.services.ml_adapter_service import ml_adapter_service, is_reserved_ml_feeder_id

logger = logging.getLogger(__name__)

# Simulated demo data store for the one legacy feeder id that does NOT
# collide with the ML feeder namespace (F01-F10). See module docstring.
MOCK_FEEDERS: dict[str, dict] = {
    "F12": {
        "id": "F12",
        "name": "Feeder 12",
        "capacity": 150.0,
        "current_load": 110.0,
        "voltage": 0.98,
        "location": {
            "latitude": 13.0350,
            "longitude": 77.5890,
        },
    },
}


def _feeder_response_from_ml_snapshot(snapshot: dict) -> FeederResponse:
    """Builds a FeederResponse from an ml_adapter_service feeder snapshot
    (get_feeder_forecast / get_all_feeders_forecast). SIMULATED data -- see
    module docstring and ml_adapter_service.FEEDER_SYNTHETIC_WARNING."""
    loc = snapshot["location"]
    return FeederResponse(
        id=snapshot["feeder_id"],
        name=snapshot["name"],
        capacity=snapshot["capacity_mw"],
        current_load=snapshot["current_load_mw"],
        voltage=snapshot["voltage_pu"],
        location=Location(latitude=loc["lat"], longitude=loc["lon"], lat=loc["lat"], lon=loc["lon"]),
    )


def get_all_feeders() -> list[FeederResponse]:
    """Retrieve all available grid feeders: the real ML pipeline's 10
    synthetic feeders (F01-F10) when the ML adapter is available, PLUS the
    one legacy mock feeder (F12). If the ML adapter is unavailable, F01-F10
    are simply absent from the list (never backfilled with mock data of the
    same id -- see module docstring).

    Returns:
        list[FeederResponse]: List of feeder models.
    """
    feeders: list[FeederResponse] = []
    if ml_adapter_service.is_available():
        try:
            snapshots = ml_adapter_service.get_all_feeders_forecast()
            feeders.extend(_feeder_response_from_ml_snapshot(s) for s in snapshots)
        except ValueError as err:
            logger.warning(f"ML feeder allocation unavailable, F01-F10 omitted from feeder list: {err}")
    feeders.extend(FeederResponse(**data) for data in MOCK_FEEDERS.values())
    return feeders


def get_feeder_by_id(feeder_id: str) -> Optional[FeederResponse]:
    """Retrieve a specific grid feeder by its unique identifier.

    F01-F10 are ALWAYS answered by the real ML feeder allocation, never by
    mock data of the same id (see module docstring) -- if the ML adapter is
    unavailable or fails to evaluate the feeder, this returns None (honest
    "not found") rather than silently substituting legacy mock data.
    Any other feeder id (e.g. legacy 'F12') is served from MOCK_FEEDERS.

    Args:
        feeder_id (str): Feeder identifier (e.g., 'F07').

    Returns:
        Optional[FeederResponse]: The feeder model if found, otherwise None.
    """
    fid = feeder_id.upper()
    if is_reserved_ml_feeder_id(fid):
        if not ml_adapter_service.is_available():
            logger.warning(f"ML adapter unavailable; reserved ML feeder '{fid}' has no mock fallback identity.")
            return None
        try:
            snapshot = ml_adapter_service.get_feeder_forecast(fid)
            return _feeder_response_from_ml_snapshot(snapshot)
        except ValueError as err:
            logger.warning(f"ML feeder allocation failed for reserved id '{fid}': {err}")
            return None

    data = MOCK_FEEDERS.get(fid)
    if not data:
        return None
    return FeederResponse(**data)
