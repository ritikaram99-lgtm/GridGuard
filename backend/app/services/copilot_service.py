"""Copilot service orchestrating operational explanations for grid feeders.

Calls the intelligence service for structured feeder data and passes it to the
Gemini/fallback explanation service layer.
"""

from typing import Optional
from app.schemas.copilot import CopilotResponse
from app.services import gemini_service, intelligence_service


def get_copilot_explanation(feeder_id: str) -> Optional[CopilotResponse]:
    """Retrieve Copilot explanation payload for a specified feeder.

    Args:
        feeder_id (str): Feeder identifier (e.g. 'F07').

    Returns:
        Optional[CopilotResponse]: Copilot explanation response model or None if feeder not found.
    """
    # 1. Retrieve structured feeder intelligence
    intelligence = intelligence_service.get_feeder_intelligence(feeder_id)
    if not intelligence:
        return None

    # 2. Generate copilot explanation via Gemini service (with fallback)
    return gemini_service.generate_copilot_explanation(intelligence)
