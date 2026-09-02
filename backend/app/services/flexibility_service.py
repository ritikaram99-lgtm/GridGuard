"""Flexibility service providing simulated flexible grid resources for feeders.

DISCLAIMER: The resource flexibility data in this service consists of SIMULATED
DEMO DATA for testing and demonstration purposes. It must not be presented as
real grid resource measurements.
"""

from pydantic import BaseModel, Field


class FlexibleResource(BaseModel):
    """Representation of a flexible demand/storage resource on a feeder."""

    action_type: str = Field(..., description="Type of action (e.g., EV_SHIFT, BATTERY, INDUSTRIAL)")
    max_reduction: float = Field(..., ge=0, description="Maximum available MW load reduction/discharge")
    cost_per_mw: float = Field(..., ge=0, description="Cost coefficient per MW reduction")
    disruption_per_mw: float = Field(..., ge=0, description="Disruption coefficient per MW reduction")


# Mock flexibility dataset per feeder (EV, Battery, Industrial)
MOCK_FEEDER_FLEXIBILITY: dict[str, list[dict]] = {
    "F01": [
        {"action_type": "EV_SHIFT", "max_reduction": 3.0, "cost_per_mw": 2.0, "disruption_per_mw": 1.0},
        {"action_type": "BATTERY", "max_reduction": 2.0, "cost_per_mw": 3.0, "disruption_per_mw": 0.5},
        {"action_type": "INDUSTRIAL", "max_reduction": 2.0, "cost_per_mw": 5.0, "disruption_per_mw": 3.0},
    ],
    "F04": [
        {"action_type": "EV_SHIFT", "max_reduction": 4.0, "cost_per_mw": 2.0, "disruption_per_mw": 1.0},
        {"action_type": "BATTERY", "max_reduction": 4.0, "cost_per_mw": 3.0, "disruption_per_mw": 0.5},
        {"action_type": "INDUSTRIAL", "max_reduction": 1.0, "cost_per_mw": 5.0, "disruption_per_mw": 3.0},
    ],
    "F07": [
        {"action_type": "EV_SHIFT", "max_reduction": 7.0, "cost_per_mw": 2.0, "disruption_per_mw": 1.0},
        {"action_type": "BATTERY", "max_reduction": 8.0, "cost_per_mw": 3.0, "disruption_per_mw": 0.5},
        {"action_type": "INDUSTRIAL", "max_reduction": 5.0, "cost_per_mw": 5.0, "disruption_per_mw": 3.0},
    ],
    "F12": [
        {"action_type": "EV_SHIFT", "max_reduction": 8.0, "cost_per_mw": 2.0, "disruption_per_mw": 1.0},
        {"action_type": "BATTERY", "max_reduction": 10.0, "cost_per_mw": 3.0, "disruption_per_mw": 0.5},
        {"action_type": "INDUSTRIAL", "max_reduction": 7.0, "cost_per_mw": 5.0, "disruption_per_mw": 3.0},
    ],
}


def get_feeder_flexibility(feeder_id: str) -> list[FlexibleResource]:
    """Retrieve available flexible resources for a specified feeder.

    Args:
        feeder_id (str): Feeder identifier (e.g., 'F07').

    Returns:
        list[FlexibleResource]: List of available flexible resource models.
    """
    raw_resources = MOCK_FEEDER_FLEXIBILITY.get(feeder_id.upper(), [])
    return [FlexibleResource(**res) for res in raw_resources]
