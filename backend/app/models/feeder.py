"""SQLAlchemy model for feeders table."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class FeederModel(Base):
    """Feeder database model representing grid feeder baseline specifications."""

    __tablename__ = "feeders"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    feeder_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default=None)
    capacity_mw: Mapped[float] = mapped_column(Float, nullable=False)
    current_load_mw: Mapped[float] = mapped_column(Float, nullable=False)
    voltage_pu: Mapped[float] = mapped_column(Float, nullable=False)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True, default=None)
