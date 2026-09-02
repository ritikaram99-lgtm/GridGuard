"""Database service layer managing entity persistence, deduplication, and summary counts.

Handles safe SQLAlchemy session management (commit/rollback/close) and ensures
backend APIs run seamlessly regardless of database connectivity.
"""

from datetime import datetime, timedelta
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import database
from app.models.action import ActionModel
from app.models.alert import AlertModel
from app.models.feeder import FeederModel
from app.models.measurement import MeasurementModel
from app.models.prediction import PredictionModel
from app.schemas.forecast import ForecastResponse
from app.schemas.recommendation import ActionDetail

logger = logging.getLogger(__name__)


def seed_feeders_if_needed() -> None:
    """Idempotently bootstrap baseline feeders (F01, F04, F07, F12) into PostgreSQL."""
    if not database.check_db_connection():
        return

    session: Session = database.SessionLocal()
    try:
        from app.services.feeder_service import get_all_feeders
        feeders = get_all_feeders()
        for f_data in feeders:
            existing = session.scalar(select(FeederModel).where(FeederModel.feeder_id == f_data.id))
            if not existing:
                feeder_row = FeederModel(
                    feeder_id=f_data.id,
                    name=f_data.name,
                    capacity_mw=f_data.capacity,
                    current_load_mw=f_data.current_load,
                    voltage_pu=f_data.voltage,
                    latitude=f_data.location.latitude,
                    longitude=f_data.location.longitude,
                )
                session.add(feeder_row)
        session.commit()
    except Exception as err:
        session.rollback()
        logger.warning(f"Feeder bootstrapping failed: {err}")
    finally:
        session.close()


def record_measurement(
    feeder_id: str,
    load_mw: float,
    voltage_pu: Optional[float] = None,
    temperature_c: Optional[float] = None,
) -> bool:
    """Record a single feeder load measurement row into the database."""
    if not database.check_db_connection():
        return False

    session: Session = database.SessionLocal()
    try:
        meas = MeasurementModel(
            feeder_id=feeder_id.upper(),
            load_mw=load_mw,
            voltage_pu=voltage_pu,
            temperature_c=temperature_c,
            timestamp=datetime.now(),
        )
        session.add(meas)
        session.commit()
        return True
    except Exception as err:
        session.rollback()
        logger.warning(f"Failed to record measurement for '{feeder_id}': {err}")
        return False
    finally:
        session.close()


def record_predictions(
    feeder_id: str,
    forecast: ForecastResponse,
    model_version: str = "1.0.0",
) -> bool:
    """Record 15m, 30m, 45m, 60m forecast predictions into the database."""
    if not database.check_db_connection():
        return False

    session: Session = database.SessionLocal()
    try:
        now = datetime.now()
        horizons_map = {
            15: forecast.m15,
            30: forecast.m30,
            45: forecast.m45,
            60: forecast.m60,
        }
        for minutes, pred_val in horizons_map.items():
            pred_row = PredictionModel(
                feeder_id=feeder_id.upper(),
                timestamp=now,
                horizon_minutes=minutes,
                predicted_load_mw=pred_val,
                model_version=model_version,
                source=forecast.source or "ml",
            )
            session.add(pred_row)
        session.commit()
        return True
    except Exception as err:
        session.rollback()
        logger.warning(f"Failed to record predictions for '{feeder_id}': {err}")
        return False
    finally:
        session.close()


def record_alert(
    feeder_id: str,
    risk_score: float,
    risk_level: str,
    time_to_overload_minutes: Optional[float] = None,
    message: Optional[str] = None,
) -> bool:
    """Record a risk alert event with 5-minute deduplication window."""
    if not database.check_db_connection():
        return False

    session: Session = database.SessionLocal()
    try:
        fid = feeder_id.upper()
        five_mins_ago = datetime.now() - timedelta(minutes=5)
        recent_alert = session.scalar(
            select(AlertModel)
            .where(
                AlertModel.feeder_id == fid,
                AlertModel.risk_level == risk_level,
                AlertModel.timestamp >= five_mins_ago,
            )
        )
        if recent_alert:
            return False

        now = datetime.now()
        alert_row = AlertModel(
            feeder_id=fid,
            risk_score=risk_score,
            risk_level=risk_level,
            time_to_overload_minutes=time_to_overload_minutes,
            message=message or f"Feeder {fid} risk score {risk_score:.0f} ({risk_level})",
            timestamp=now,
            created_at=now,
        )
        session.add(alert_row)
        session.commit()
        return True
    except Exception as err:
        session.rollback()
        logger.warning(f"Failed to record alert for '{feeder_id}': {err}")
        return False
    finally:
        session.close()


def record_actions(
    feeder_id: str,
    action_details: List[ActionDetail],
) -> bool:
    """Record recommended mitigation actions for a feeder."""
    if not database.check_db_connection() or not action_details:
        return False

    session: Session = database.SessionLocal()
    try:
        fid = feeder_id.upper()
        now = datetime.now()
        for act in action_details:
            act_row = ActionModel(
                feeder_id=fid,
                action_type=act.action_type,
                reduction_mw=act.load_reduction,
                status="RECOMMENDED",
                timestamp=now,
            )
            session.add(act_row)
        session.commit()
        return True
    except Exception as err:
        session.rollback()
        logger.warning(f"Failed to record actions for '{feeder_id}': {err}")
        return False
    finally:
        session.close()


def record_dispatched_actions(
    feeder_id: str,
    dispatched_actions: List[Any],
) -> bool:
    """Record operator-dispatched flexibility actions with status 'DISPATCHED'."""
    if not database.check_db_connection() or not dispatched_actions:
        return False

    session: Session = database.SessionLocal()
    try:
        fid = feeder_id.upper()
        now = datetime.now()
        ten_sec_ago = now - timedelta(seconds=10)

        for act in dispatched_actions:
            act_type = getattr(act, "action_type", str(act.get("action_type", "") if isinstance(act, dict) else ""))
            red_mw = float(getattr(act, "reduction_mw", float(act.get("reduction_mw", 0.0) if isinstance(act, dict) else 0.0)))

            recent = session.scalar(
                select(ActionModel).where(
                    ActionModel.feeder_id == fid,
                    ActionModel.action_type == act_type,
                    ActionModel.reduction_mw == red_mw,
                    ActionModel.status == "DISPATCHED",
                    ActionModel.timestamp >= ten_sec_ago,
                )
            )
            if recent:
                continue

            act_row = ActionModel(
                feeder_id=fid,
                action_type=act_type,
                reduction_mw=red_mw,
                status="DISPATCHED",
                timestamp=now,
            )
            session.add(act_row)
        session.commit()
        return True
    except Exception as err:
        session.rollback()
        logger.warning(f"Failed to record dispatched actions for '{feeder_id}': {err}")
        return False
    finally:
        session.close()


def get_db_summary() -> Dict[str, int]:
    """Query real table row counts directly from PostgreSQL database."""
    if not database.check_db_connection():
        return {
            "feeders": 0,
            "measurements": 0,
            "predictions": 0,
            "alerts": 0,
            "actions": 0,
        }

    session: Session = database.SessionLocal()
    try:
        feeders_cnt = session.scalar(select(func.count()).select_from(FeederModel)) or 0
        meas_cnt = session.scalar(select(func.count()).select_from(MeasurementModel)) or 0
        pred_cnt = session.scalar(select(func.count()).select_from(PredictionModel)) or 0
        alert_cnt = session.scalar(select(func.count()).select_from(AlertModel)) or 0
        action_cnt = session.scalar(select(func.count()).select_from(ActionModel)) or 0

        return {
            "feeders": int(feeders_cnt),
            "measurements": int(meas_cnt),
            "predictions": int(pred_cnt),
            "alerts": int(alert_cnt),
            "actions": int(action_cnt),
        }
    except Exception as err:
        logger.warning(f"Error querying database summary counts: {err}")
        return {
            "feeders": 0,
            "measurements": 0,
            "predictions": 0,
            "alerts": 0,
            "actions": 0,
        }
    finally:
        session.close()
