from pydantic import BaseModel, ConfigDict, Field


class DatabaseStatusResponse(BaseModel):
    """Response payload for database connectivity status."""

    database: str = Field("postgresql", description="Database engine type")
    connected: bool = Field(..., description="Flag indicating whether PostgreSQL database is reachable")

    model_config = ConfigDict(populate_by_name=True)


class DatabaseSummaryResponse(BaseModel):
    """Response payload for database table row counts."""

    feeders: int = Field(0, description="Total feeder count")
    measurements: int = Field(0, description="Total measurement records count")
    predictions: int = Field(0, description="Total prediction records count")
    alerts: int = Field(0, description="Total alert event count")
    actions: int = Field(0, description="Total action recommendation count")

    model_config = ConfigDict(populate_by_name=True)
