"""SQLAlchemy model for measurements table."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class MeasurementModel(Base):
    """Historical/time-series measurement records."""

    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    feeder_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False, server_default=func.now())
    load_mw: Mapped[float] = mapped_column(Float, nullable=False)
    voltage_pu: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    temperature_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
