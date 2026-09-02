"""SQLAlchemy model for actions table."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ActionModel(Base):
    """Mitigation optimization action records."""

    __tablename__ = "actions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    feeder_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False, server_default=func.now())
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    reduction_mw: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="RECOMMENDED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
