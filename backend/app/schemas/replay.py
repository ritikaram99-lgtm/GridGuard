"""Pydantic schemas for historical replay requests and responses."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ReplayQueryRequest(BaseModel):
    """Payload for querying historical time-series feeder records."""

    feeder_id: str = Field(..., description="Target feeder identifier (e.g., 'F07')")
    start_timestamp: Optional[datetime] = Field(None, description="Optional start datetime boundary")
    end_timestamp: Optional[datetime] = Field(None, description="Optional end datetime boundary")
    limit: Optional[int] = Field(100, ge=1, le=1000, description="Maximum records to return (1-1000)")

    model_config = ConfigDict(populate_by_name=True)


class ReplayRecord(BaseModel):
    """Historical time-series measurement record."""

    timestamp: str = Field(..., description="Measurement timestamp")
    feeder_id: str = Field(..., description="Feeder ID")
    load_mw: float = Field(..., description="Historical load in MW")
    temperature_c: float = Field(..., description="Ambient temperature in Celsius")

    model_config = ConfigDict(populate_by_name=True)


class ReplayQueryResponse(BaseModel):
    """Response payload for historical time-series query."""

    feeder_id: str = Field(..., description="Feeder ID")
    count: int = Field(..., description="Total records returned")
    records: List[ReplayRecord] = Field(..., description="Chronological sequence of historical records")

    model_config = ConfigDict(populate_by_name=True)


class ReplayLatestResponse(BaseModel):
    """Latest historical record snapshot for a feeder."""

    feeder_id: str = Field(..., description="Feeder ID")
    timestamp: str = Field(..., description="Timestamp of the latest historical record")
    load_mw: float = Field(..., description="Historical load in MW")
    temperature_c: float = Field(..., description="Ambient temperature in Celsius")

    model_config = ConfigDict(populate_by_name=True)


class ReplayIngestRequest(BaseModel):
    """Payload for ingesting a historical measurement record into the database."""

    timestamp: str = Field(..., description="Target historical timestamp to ingest (e.g. '2026-08-30 23:45:00')")

    model_config = ConfigDict(populate_by_name=True)


class ReplayIngestResponse(BaseModel):
    """Response payload following controlled historical record ingestion."""

    feeder_id: str = Field(..., description="Feeder ID")
    timestamp: str = Field(..., description="Ingested record timestamp")
    load_mw: float = Field(..., description="Ingested load in MW")
    voltage_pu: float = Field(..., description="Voltage in p.u. (from baseline feeder state)")
    temperature_c: float = Field(..., description="Ingested temperature in Celsius")
    status: str = Field("INGESTED", description="Ingestion status result")

    model_config = ConfigDict(populate_by_name=True)
