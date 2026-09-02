"""SQLAlchemy model for alerts table."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class AlertModel(Base):
    """Grid stress risk alerts and event records."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    feeder_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False, server_default=func.now())
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=False)
    time_to_overload_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    message: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
