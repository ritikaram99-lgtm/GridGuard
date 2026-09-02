"""Feeder service providing grid feeder data.

DISCLAIMER: The feeder data in this service consists of SIMULATED DEMO DATA
used for demonstration and development purposes. It must not be presented as
real grid measurement data.
"""

from typing import Optional
from app.schemas.feeder import FeederResponse, Location

# Simulated demo data store for feeders
MOCK_FEEDERS: dict[str, dict] = {
    "F01": {
        "id": "F01",
        "name": "Feeder 01",
        "capacity": 80.0,
        "current_load": 52.0,
        "voltage": 0.99,
        "location": {
            "latitude": 12.9352,
            "longitude": 77.6245,
        },
    },
    "F04": {
        "id": "F04",
        "name": "Feeder 04",
        "capacity": 120.0,
        "current_load": 85.0,
        "voltage": 0.97,
        "location": {
            "latitude": 12.9800,
            "longitude": 77.5600,
        },
    },
    "F07": {
        "id": "F07",
        "name": "Feeder 07",
        "capacity": 100.0,
        "current_load": 97.0,
        "voltage": 0.95,
        "location": {
            "latitude": 12.9716,
            "longitude": 77.5946,
        },
    },
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


def get_all_feeders() -> list[FeederResponse]:
    """Retrieve all available grid feeders.

    Returns:
        list[FeederResponse]: List of all simulated feeder models.
    """
    return [FeederResponse(**data) for data in MOCK_FEEDERS.values()]


def get_feeder_by_id(feeder_id: str) -> Optional[FeederResponse]:
    """Retrieve a specific grid feeder by its unique identifier.

    Args:
        feeder_id (str): Feeder identifier (e.g., 'F07').

    Returns:
        Optional[FeederResponse]: The feeder model if found, otherwise None.
    """
    data = MOCK_FEEDERS.get(feeder_id.upper())
    if not data:
        return None
    return FeederResponse(**data)
