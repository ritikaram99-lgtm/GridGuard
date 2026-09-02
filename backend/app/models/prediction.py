"""SQLAlchemy model for predictions table."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class PredictionModel(Base):
    """Forecast prediction records for feeders."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    feeder_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False, server_default=func.now())
    horizon_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    predicted_load_mw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    model_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="1.0.0")
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="ml")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
