"""Risk engine service calculating grid stress scores, risk classifications,
time-to-overload, and active risk contributors. Persists alerts to PostgreSQL when connected.

For the 10 real ML feeders (F01-F10), ALWAYS uses the real, deterministic
Grid Stress Engine (ml/src/stress_engine.py, unmodified) run over that
feeder's own ML-allocated hourly forecast (ml_adapter_service.get_feeder_forecast)
-- source='ml_stress_engine'. Never falls back to this module's own legacy
boolean-trigger formula for those ids (see feeder_service.py's module
docstring on the F01-F10 identity boundary): if the ML adapter is
unavailable, calculate_feeder_risk returns None (honest "not found"); if
`origin` is invalid/out-of-range, it raises ValueError (callers should
surface this as HTTP 400). The legacy formula (source='legacy_formula',
unchanged) is used only for non-reserved feeder ids (currently just 'F12').
"""

import logging
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
from app.services.forecast_service import get_forecast, get_forecast_peak
from app.services.ml_adapter_service import ml_adapter_service, is_reserved_ml_feeder_id
from app.services.db_service import record_alert

logger = logging.getLogger(__name__)

# Human-readable labels for the ML Stress Engine's weighted components
# (ml/src/stress_engine.py STRESS_WEIGHTS keys), for RiskContributor display.
ML_STRESS_COMPONENT_LABELS: dict[str, str] = {
    "current_utilization": "Current utilization",
    "forecast_utilization": "Forecast utilization (24h)",
    "trajectory_slope": "Rising load trajectory",
    "voltage_stress": "Voltage deterioration",
    "headroom": "Low headroom",
}

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

# Mock flexibility metrics for the legacy formula. Only used for non-reserved
# feeder ids (currently just 'F12') -- F01-F10 always use the real ML Stress
# Engine path above, which has no "low flexibility" trigger of its own kind
# (the ML Stress Engine's own headroom/utilization components already cover
# analogous ground -- see flexibility_service.py for the 10 ML feeders'
# actual, capacity-scaled flexibility contract).
MOCK_FLEXIBILITY: dict[str, float] = {
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
    """Calculate time to overload in minutes by inspecting the legacy 4-point
    forecast intervals.

    NOTE: this minute-resolution calculation only applies to legacy mock/
    joblib forecasts (m15..m60). Real ML forecasts (source='ml') are
    genuinely hourly with no sub-hourly values -- fabricating a minute-level
    crossing from them is explicitly out of scope, so this returns None for
    those (a real hourly time-to-overload, in ml/src/stress_engine.py's
    hour-resolution sense, is a later-phase integration, not this field)."""
    intervals = [
        (15.0, forecast.m15),
        (30.0, forecast.m30),
        (45.0, forecast.m45),
        (60.0, forecast.m60),
    ]

    for minutes, load in intervals:
        if load is not None and load >= capacity:
            return minutes

    return None


def calculate_feeder_risk(feeder_id: str, origin: Optional[str] = None) -> Optional[DetailedRiskResponse]:
    """Calculate comprehensive grid risk assessment for a specified feeder.

    Args:
        feeder_id (str): Feeder identifier (e.g. 'F07').
        origin (Optional[str]): Optional ISO forecast-origin timestamp,
            forwarded to the ML Stress Engine path when the feeder is one of
            the 10 real ML feeders (F01-F10). Ignored for the legacy
            formula fallback.
    """
    fid = feeder_id.upper()

    # 1. Real ML Grid Stress Engine (F01-F10 ONLY, always) -- deterministic,
    #    unmodified ml/src/stress_engine.py evaluated over this feeder's OWN
    #    allocated hourly forecast. These ids never fall through to the
    #    legacy formula below (see module docstring's identity boundary).
    if is_reserved_ml_feeder_id(fid):
        if not ml_adapter_service.is_available():
            return None
        # A bad/out-of-range origin raises ValueError here (propagated to
        # the caller/route as 400), rather than silently falling back to an
        # unrelated legacy-formula score for the same feeder id.
        snap = ml_adapter_service.get_feeder_forecast(fid, origin)
        risk_level = RiskLevel(snap["risk_level"])
        tto_hours = snap["time_to_overload"]["time_to_overload_hours"]
        tto_minutes = tto_hours * 60.0 if tto_hours is not None else None

        contributors = [
            RiskContributor(name=ML_STRESS_COMPONENT_LABELS.get(k, k), impact=v)
            for k, v in snap["stress_component_points"].items()
            if v > 0
        ]

        try:
            record_alert(
                feeder_id=fid,
                risk_score=snap["stress_score"],
                risk_level=risk_level.value,
                time_to_overload_minutes=tto_minutes,
                message=f"Feeder {fid} stress score {snap['stress_score']:.0f} ({risk_level.value}) [ML Stress Engine]",
            )
        except Exception:
            pass

        return DetailedRiskResponse(
            score=snap["stress_score"],
            level=risk_level,
            time_to_overload=tto_minutes,
            time_to_overload_hours=tto_hours,
            source="ml_stress_engine",
            contributors=contributors,
        )

    # 2. Legacy boolean-trigger formula (unchanged), for non-reserved feeder
    #    ids only (currently just 'F12').
    feeder: Optional[FeederResponse] = get_feeder_by_id(feeder_id)
    if not feeder:
        return None

    forecast: Optional[ForecastResponse] = get_forecast(feeder_id)
    if not forecast:
        return None

    score = 0.0
    contributors: list[RiskContributor] = []

    # 1. Forecast Exceeds Capacity Check (compatibility helper: handles both
    #    real ML hourly forecasts and legacy mock/joblib 4-point forecasts)
    forecast_peak = get_forecast_peak(forecast)
    if forecast_peak >= feeder.capacity:
        score += WEIGHT_FORECAST_OVERLOAD
        contributors.append(
            RiskContributor(name="Forecast exceeds capacity", impact=WEIGHT_FORECAST_OVERLOAD)
        )

    # 2. Rapid Load Increase Check (60m load - 15m load). This specific
    # 15-60 minute window only exists for legacy mock/joblib forecasts;
    # real ML forecasts (source='ml') have no sub-hourly values, so this
    # trigger is skipped (not fabricated) when m15/m60 are unavailable.
    if forecast.m15 is not None and forecast.m60 is not None:
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
        source="legacy_formula",
        contributors=contributors,
    )
