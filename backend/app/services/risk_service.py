"""Risk engine service calculating grid stress scores, risk classifications,
time-to-overload, and active risk contributors. Persists alerts to PostgreSQL when connected.
"""

from typing import Optional
from app.schemas.feeder import FeederResponse
from app.schemas.forecast import ForecastResponse
from app.schemas.risk import (
    DetailedRiskResponse,
    RiskContributor,
    RiskInfo,
    RiskLevel,
)
from app.services.feeder_service import get_feeder_by_id
from app.services.forecast_service import get_forecast
from app.services.db_service import record_alert

# Configurable prototype thresholds
THRESHOLD_HIGH_UTILIZATION = 0.90  # Current load / capacity >= 90%
THRESHOLD_RAPID_INCREASE = 10.0     # Forecast load increase >= 10 MW
THRESHOLD_VOLTAGE_DETERIORATION = 0.97  # Voltage < 0.97 p.u.
THRESHOLD_LOW_FLEXIBILITY = 10.0    # Total available flexibility < 10 MW

# Configurable prototype component weights (Max total = 100)
WEIGHT_FORECAST_OVERLOAD = 30.0
WEIGHT_RAPID_INCREASE = 20.0
WEIGHT_HIGH_UTILIZATION = 15.0
WEIGHT_VOLTAGE_DETERIORATION = 15.0
WEIGHT_LOW_FLEXIBILITY = 10.0

# Mock flexibility metrics per feeder (EV, Battery, Industrial in MW)
MOCK_FLEXIBILITY: dict[str, float] = {
    "F01": 7.0,   # Low flexibility (< 10 MW)
    "F04": 9.0,   # Low flexibility (< 10 MW)
    "F07": 20.0,  # EV=7, Battery=8, Industrial=5 -> 20 MW (High flexibility)
    "F12": 25.0,  # High flexibility (>= 10 MW)
}


def classify_risk(score: float) -> RiskLevel:
    """Classify grid stress score into standard RiskLevel enum."""
    if score <= 30:
        return RiskLevel.LOW
    elif score <= 60:
        return RiskLevel.MODERATE
    elif score <= 80:
        return RiskLevel.HIGH
    else:
        return RiskLevel.CRITICAL


def calculate_time_to_overload(forecast: ForecastResponse, capacity: float) -> Optional[float]:
    """Calculate time to overload in minutes by inspecting forecast intervals."""
    intervals = [
        (15.0, forecast.m15),
        (30.0, forecast.m30),
        (45.0, forecast.m45),
        (60.0, forecast.m60),
    ]

    for minutes, load in intervals:
        if load >= capacity:
            return minutes

    return None


def calculate_feeder_risk(feeder_id: str) -> Optional[DetailedRiskResponse]:
    """Calculate comprehensive grid risk assessment for a specified feeder."""
    feeder: Optional[FeederResponse] = get_feeder_by_id(feeder_id)
    if not feeder:
        return None

    forecast: Optional[ForecastResponse] = get_forecast(feeder_id)
    if not forecast:
        return None

    score = 0.0
    contributors: list[RiskContributor] = []

    # 1. Forecast Exceeds Capacity Check
    forecast_peak = max(forecast.m15, forecast.m30, forecast.m45, forecast.m60)
    if forecast_peak >= feeder.capacity:
        score += WEIGHT_FORECAST_OVERLOAD
        contributors.append(
            RiskContributor(name="Forecast exceeds capacity", impact=WEIGHT_FORECAST_OVERLOAD)
        )

    # 2. Rapid Load Increase Check (60m load - 15m load)
    trajectory = forecast.m60 - forecast.m15
    if trajectory >= THRESHOLD_RAPID_INCREASE:
        score += WEIGHT_RAPID_INCREASE
        contributors.append(
            RiskContributor(name="Rapid load increase", impact=WEIGHT_RAPID_INCREASE)
        )

    # 3. High Utilization Check (current_load / capacity)
    utilization = feeder.current_load / feeder.capacity
    if utilization >= THRESHOLD_HIGH_UTILIZATION:
        score += WEIGHT_HIGH_UTILIZATION
        contributors.append(
            RiskContributor(name="High utilization", impact=WEIGHT_HIGH_UTILIZATION)
        )

    # 4. Voltage Deterioration Check (voltage < 0.97 p.u.)
    if feeder.voltage < THRESHOLD_VOLTAGE_DETERIORATION:
        score += WEIGHT_VOLTAGE_DETERIORATION
        contributors.append(
            RiskContributor(name="Voltage deterioration", impact=WEIGHT_VOLTAGE_DETERIORATION)
        )

    # 5. Low Flexibility Check (total flexibility < 10 MW)
    total_flexibility = MOCK_FLEXIBILITY.get(feeder.id.upper(), 15.0)
    if total_flexibility < THRESHOLD_LOW_FLEXIBILITY:
        score += WEIGHT_LOW_FLEXIBILITY
        contributors.append(
            RiskContributor(name="Low flexibility", impact=WEIGHT_LOW_FLEXIBILITY)
        )

    # Cap score at 100
    final_score = min(score, 100.0)

    # Classify risk level
    risk_level = classify_risk(final_score)

    # Calculate time to overload
    tto = calculate_time_to_overload(forecast, feeder.capacity)

    # Record risk alert in database (non-blocking, 5-min deduplication)
    try:
        record_alert(
            feeder_id=feeder.id,
            risk_score=final_score,
            risk_level=risk_level.value,
            time_to_overload_minutes=tto,
            message=f"Feeder {feeder.id} risk score {final_score:.0f} ({risk_level.value})",
        )
    except Exception:
        pass

    return DetailedRiskResponse(
        score=final_score,
        level=risk_level,
        time_to_overload=tto,
        contributors=contributors,
    )
