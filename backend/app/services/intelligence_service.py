"""Intelligence service orchestrating unified feeder intelligence dashboard payloads.

Combines feeder info, current state, load forecast, risk assessment, risk
contributors, and mitigation recommendations from existing underlying services.
"""

from typing import Optional
from app.schemas.feeder import (
    Location,
    FeederCurrentState,
    FeederIntelligenceResponse,
)
from app.schemas.risk import RiskInfo
from app.services import (
    feeder_service,
    forecast_service,
    risk_service,
    recommendation_service,
)


def get_feeder_intelligence(feeder_id: str) -> Optional[FeederIntelligenceResponse]:
    """Retrieve unified feeder intelligence metrics for a specified feeder.

    Args:
        feeder_id (str): Feeder identifier (e.g. 'F07').

    Returns:
        Optional[FeederIntelligenceResponse]: Consolidated feeder intelligence or None if feeder not found.
    """
    # 1. Obtain feeder details
    feeder = feeder_service.get_feeder_by_id(feeder_id)
    if not feeder:
        return None

    # 2. Obtain load forecast
    forecast = forecast_service.get_forecast(feeder_id)
    if not forecast:
        return None

    # 3. Obtain risk analysis
    risk_detail = risk_service.calculate_feeder_risk(feeder_id)
    if not risk_detail:
        return None

    # 4. Obtain recommendation analysis
    recommendation = recommendation_service.generate_recommendation(feeder_id)
    if not recommendation:
        return None

    # 5. Construct unified intelligence response
    return FeederIntelligenceResponse(
        feeder_id=feeder.id,
        current=FeederCurrentState(
            load=feeder.current_load,
            capacity=feeder.capacity,
            voltage=feeder.voltage,
        ),
        location=Location(
            latitude=feeder.location.latitude,
            longitude=feeder.location.longitude,
            lat=feeder.location.latitude,
            lon=feeder.location.longitude,
        ),
        forecast=forecast,
        risk=RiskInfo(
            score=risk_detail.score,
            level=risk_detail.level,
            time_to_overload=risk_detail.time_to_overload,
        ),
        contributors=risk_detail.contributors,
        recommendation=recommendation,
    )
