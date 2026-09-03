"""Flexibility service providing simulated flexible grid resources for feeders.

DISCLAIMER: The resource flexibility data in this service consists of SIMULATED
DEMO DATA for testing and demonstration purposes. It must not be presented as
real grid resource measurements.

For the 10 real ML feeders (F01-F10), flexibility is derived from that
feeder's REAL ML-computed capacity_mw (ml_adapter_service, ultimately
ml/src/feeder_generator.py) and its feeder TYPE, using a documented,
type-appropriate share of capacity for each action (see
FEEDER_TYPE_FLEXIBILITY_SHARE below) -- e.g. an EV_HEAVY feeder has more
EV_SHIFT headroom than an INDUSTRIAL one, which instead has more INDUSTRIAL
curtailment headroom. This replaces the previous gap where 6 of the 10 ML
feeders (everything except the 3 that collided with legacy mock ids) had
NO flexibility data at all. Still explicitly SIMULATED -- no real DR/battery/
industrial-curtailment contracts exist for these feeders. The legacy,
arbitrary per-feeder table below is used only for the one non-reserved
feeder id ('F12'); see feeder_service.py's module docstring on the F01-F10
identity boundary.
"""

from pydantic import BaseModel, Field
from app.services.ml_adapter_service import ml_adapter_service, is_reserved_ml_feeder_id


class FlexibleResource(BaseModel):
    """Representation of a flexible demand/storage resource on a feeder."""

    action_type: str = Field(..., description="Type of action (e.g., EV_SHIFT, BATTERY, INDUSTRIAL)")
    max_reduction: float = Field(..., ge=0, description="Maximum available MW load reduction/discharge")
    cost_per_mw: float = Field(..., ge=0, description="Cost coefficient per MW reduction")
    disruption_per_mw: float = Field(..., ge=0, description="Disruption coefficient per MW reduction")


# Generic cost/disruption coefficients per action type -- not feeder-specific,
# reused from the original prototype's assumptions across all 10 ML feeders.
_ACTION_COST_DISRUPTION = {
    "EV_SHIFT": (2.0, 1.0),
    "BATTERY": (3.0, 0.5),
    "INDUSTRIAL": (5.0, 3.0),
}

# Type-appropriate share of a feeder's capacity_mw available as flexibility
# per action, keyed by ml/src/feeder_generator.py's FEEDER_TYPES. A 0.0 (or
# omitted) share means that action genuinely isn't offered on that feeder
# type (e.g. no INDUSTRIAL curtailment on a RESIDENTIAL feeder) -- not
# fabricated. Documented engineering choices, not derived from any real DR
# program.
FEEDER_TYPE_FLEXIBILITY_SHARE: dict[str, dict[str, float]] = {
    "RESIDENTIAL": {"EV_SHIFT": 0.10, "BATTERY": 0.08},
    "COMMERCIAL": {"EV_SHIFT": 0.05, "BATTERY": 0.08},
    "INDUSTRIAL": {"EV_SHIFT": 0.02, "BATTERY": 0.05, "INDUSTRIAL": 0.15},
    "MIXED": {"EV_SHIFT": 0.06, "BATTERY": 0.06, "INDUSTRIAL": 0.05},
    "EV_HEAVY": {"EV_SHIFT": 0.20, "BATTERY": 0.08},
}

# Mock flexibility dataset for the one legacy, non-ML-reserved feeder id.
MOCK_FEEDER_FLEXIBILITY: dict[str, list[dict]] = {
    "F12": [
        {"action_type": "EV_SHIFT", "max_reduction": 8.0, "cost_per_mw": 2.0, "disruption_per_mw": 1.0},
        {"action_type": "BATTERY", "max_reduction": 10.0, "cost_per_mw": 3.0, "disruption_per_mw": 0.5},
        {"action_type": "INDUSTRIAL", "max_reduction": 7.0, "cost_per_mw": 5.0, "disruption_per_mw": 3.0},
    ],
}


def _ml_feeder_flexibility(fid: str) -> list[FlexibleResource]:
    definitions = ml_adapter_service.get_feeder_definitions()
    feeder_def = next((d for d in definitions if d["id"] == fid), None)
    if feeder_def is None:
        return []
    shares = FEEDER_TYPE_FLEXIBILITY_SHARE.get(feeder_def["type"], {})
    resources = []
    for action_type, share in shares.items():
        if share <= 0:
            continue
        cost_per_mw, disruption_per_mw = _ACTION_COST_DISRUPTION[action_type]
        resources.append(FlexibleResource(
            action_type=action_type,
            max_reduction=round(feeder_def["capacity_mw"] * share, 2),
            cost_per_mw=cost_per_mw,
            disruption_per_mw=disruption_per_mw,
        ))
    return resources


def get_feeder_flexibility(feeder_id: str) -> list[FlexibleResource]:
    """Retrieve available flexible resources for a specified feeder.

    F01-F10 (reserved ML feeder ids): type-appropriate, ML-capacity-scaled
    resources (see FEEDER_TYPE_FLEXIBILITY_SHARE); empty list if the ML
    adapter is unavailable (never falls back to a mismatched legacy id's
    flexibility data). Any other feeder id (e.g. 'F12'): legacy mock table.

    Args:
        feeder_id (str): Feeder identifier (e.g., 'F07').

    Returns:
        list[FlexibleResource]: List of available flexible resource models.
    """
    fid = feeder_id.upper()
    if is_reserved_ml_feeder_id(fid):
        if not ml_adapter_service.is_available():
            return []
        return _ml_feeder_flexibility(fid)

    raw_resources = MOCK_FEEDER_FLEXIBILITY.get(fid, [])
    return [FlexibleResource(**res) for res in raw_resources]
