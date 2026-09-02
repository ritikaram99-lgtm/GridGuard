"""Historical Replay Service for GridGuard AI.

Loads synthetic time-series historical feeder dataset from `ml/data/feeder_load_history.csv`,
enables chronological querying, latest record retrieval, and controlled ingestion into
PostgreSQL via the Step 13 persistence repository.
"""

from datetime import datetime
import logging
from pathlib import Path
from typing import List, Optional
import pandas as pd

from app.schemas.replay import (
    ReplayIngestResponse,
    ReplayLatestResponse,
    ReplayRecord,
)
from app.services.db_service import record_measurement
from app.services.feeder_service import get_feeder_by_id

logger = logging.getLogger(__name__)

# CSV File Path: ml/data/feeder_load_history.csv
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
CSV_PATH = BASE_DIR / "ml" / "data" / "feeder_load_history.csv"


class ReplayService:
    """Singleton service for historical time-series data replay and ingestion."""

    _instance: Optional["ReplayService"] = None

    def __init__(self) -> None:
        self._df: Optional[pd.DataFrame] = None
        self._load_dataset()

    @classmethod
    def get_instance(cls) -> "ReplayService":
        """Retrieve singleton instance of ReplayService."""
        if cls._instance is None:
            cls._instance = ReplayService()
        return cls._instance

    def _load_dataset(self) -> None:
        """Load and validate synthetic historical dataset from CSV."""
        if not CSV_PATH.exists():
            logger.warning(f"Historical dataset CSV not found at '{CSV_PATH}'. Replay service limited.")
            self._df = None
            return

        try:
            logger.info(f"Loading historical replay dataset from '{CSV_PATH}'...")
            df = pd.read_csv(CSV_PATH)
            # Ensure timestamp datetime parsing
            df["timestamp_dt"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values(by=["feeder_id", "timestamp_dt"]).reset_index(drop=True)
            self._df = df
            logger.info(f"Successfully loaded {len(df)} historical records for replay.")
        except Exception as err:
            logger.error(f"Failed to load historical dataset CSV: {err}")
            self._df = None

    def is_available(self) -> bool:
        """Check if dataset CSV is loaded and available."""
        return self._df is not None and not self._df.empty

    def get_replay_window(
        self,
        feeder_id: str,
        start_timestamp: Optional[datetime] = None,
        end_timestamp: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ReplayRecord]:
        """Retrieve chronological sequence of historical records for a feeder.

        Args:
            feeder_id (str): Target feeder identifier (e.g. 'F07').
            start_timestamp (Optional[datetime]): Optional start boundary.
            end_timestamp (Optional[datetime]): Optional end boundary.
            limit (int): Max records (1-1000).

        Returns:
            List[ReplayRecord]: Chronological historical records.

        Raises:
            ValueError: If feeder is unknown or start_timestamp > end_timestamp.
        """
        fid = feeder_id.upper()

        # Validate feeder existence against feeder service
        feeder = get_feeder_by_id(fid)
        if not feeder:
            raise ValueError(f"Feeder '{feeder_id}' not found.")

        if start_timestamp and end_timestamp and start_timestamp > end_timestamp:
            raise ValueError("start_timestamp must be before or equal to end_timestamp.")

        if self._df is None or self._df.empty:
            return []

        # Filter by feeder
        subset = self._df[self._df["feeder_id"].str.upper() == fid]

        if subset.empty:
            return []

        # Filter by start_timestamp
        if start_timestamp:
            subset = subset[subset["timestamp_dt"] >= pd.to_datetime(start_timestamp)]

        # Filter by end_timestamp
        if end_timestamp:
            subset = subset[subset["timestamp_dt"] <= pd.to_datetime(end_timestamp)]

        # Enforce max limit capped at 1000
        eff_limit = min(max(1, limit), 1000)
        subset = subset.head(eff_limit)

        records: List[ReplayRecord] = []
        for _, row in subset.iterrows():
            records.append(
                ReplayRecord(
                    timestamp=str(row["timestamp"]),
                    feeder_id=str(row["feeder_id"]),
                    load_mw=round(float(row["load_mw"]), 2),
                    temperature_c=round(float(row["temperature_c"]), 2),
                )
            )

        return records

    def get_latest_record(self, feeder_id: str) -> Optional[ReplayLatestResponse]:
        """Retrieve the latest available historical record for a specified feeder.

        Args:
            feeder_id (str): Feeder identifier (e.g. 'F07').

        Returns:
            Optional[ReplayLatestResponse]: Latest record or None if feeder unknown/no data.
        """
        fid = feeder_id.upper()
        feeder = get_feeder_by_id(fid)
        if not feeder:
            return None

        if self._df is None or self._df.empty:
            return None

        subset = self._df[self._df["feeder_id"].str.upper() == fid]
        if subset.empty:
            return None

        latest_row = subset.iloc[-1]
        return ReplayLatestResponse(
            feeder_id=str(latest_row["feeder_id"]),
            timestamp=str(latest_row["timestamp"]),
            load_mw=round(float(latest_row["load_mw"]), 2),
            temperature_c=round(float(latest_row["temperature_c"]), 2),
        )

    def ingest_record(self, feeder_id: str, timestamp_str: str) -> Optional[ReplayIngestResponse]:
        """Persist a specific historical record into PostgreSQL measurements table.

        Args:
            feeder_id (str): Feeder identifier (e.g. 'F07').
            timestamp_str (str): Target historical timestamp string.

        Returns:
            Optional[ReplayIngestResponse]: Ingestion summary or None if feeder or timestamp not found.
        """
        fid = feeder_id.upper()
        feeder = get_feeder_by_id(fid)
        if not feeder:
            return None

        if self._df is None or self._df.empty:
            return None

        subset = self._df[self._df["feeder_id"].str.upper() == fid]
        if subset.empty:
            return None

        # Match timestamp string or datetime comparison
        matched = subset[subset["timestamp"].str.strip() == timestamp_str.strip()]
        if matched.empty:
            # Attempt datetime matching
            try:
                dt_target = pd.to_datetime(timestamp_str)
                matched = subset[subset["timestamp_dt"] == dt_target]
            except Exception:
                matched = pd.DataFrame()

        if matched.empty:
            return None

        row = matched.iloc[0]
        load_mw = float(row["load_mw"])
        temp_c = float(row["temperature_c"])
        voltage_pu = float(feeder.voltage)  # Fallback to baseline feeder state

        # Persist measurement to PostgreSQL measurements table via Step 13 db_service
        record_measurement(
            feeder_id=fid,
            load_mw=load_mw,
            voltage_pu=voltage_pu,
            temperature_c=temp_c,
        )

        return ReplayIngestResponse(
            feeder_id=fid,
            timestamp=str(row["timestamp"]),
            load_mw=round(load_mw, 2),
            voltage_pu=round(voltage_pu, 2),
            temperature_c=round(temp_c, 2),
            status="INGESTED",
        )


replay_service = ReplayService.get_instance()
