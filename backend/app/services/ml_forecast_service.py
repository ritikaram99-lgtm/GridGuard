"""ML forecast service managing model loading, availability status, and inference execution.

DISCLAIMER: This service abstracts model artifact loading (joblib) and inference execution.
When `models/forecast_model.joblib` exists, it executes trained model inference for grid feeders
and returns source="ml". If missing or unavailable, it safely sets model_available=False
and the forecast service falls back to deterministic mock data.
"""

from datetime import datetime
import logging
from pathlib import Path
from typing import Any, Dict, Optional
import joblib
import pandas as pd

from app.schemas.forecast import ForecastResponse
from app.services.feeder_service import get_feeder_by_id
from app.utils.config import get_forecast_model_path

logger = logging.getLogger(__name__)


class MLForecastService:
    """Service for managing trained machine learning forecast models."""

    _instance: Optional["MLForecastService"] = None

    def __init__(self) -> None:
        self.model_path: Path = get_forecast_model_path()
        self.model_artifact: Any = None
        self.model: Any = None
        self.feature_columns: list[str] = []
        self.model_available: bool = False
        self._attempted_load: bool = False
        self._load_model()

    @classmethod
    def get_instance(cls) -> "MLForecastService":
        """Retrieve singleton instance of MLForecastService."""
        if cls._instance is None:
            cls._instance = MLForecastService()
        return cls._instance

    def _load_model(self) -> None:
        """Attempt to load the model artifact once safely."""
        if self._attempted_load:
            return

        self._attempted_load = True

        if not self.model_path.exists():
            logger.info(f"ML model file not found at '{self.model_path}'. ML inference disabled.")
            self.model_available = False
            return

        try:
            logger.info(f"Loading trained ML model from '{self.model_path}'...")
            artifact = joblib.load(self.model_path)
            if isinstance(artifact, dict) and "model" in artifact:
                self.model_artifact = artifact
                self.model = artifact["model"]
                self.feature_columns = artifact.get("feature_columns", [])
            else:
                self.model_artifact = None
                self.model = artifact
                self.feature_columns = []

            self.model_available = True
            logger.info("Successfully loaded ML forecast model artifact.")
        except Exception as err:
            logger.warning(f"Failed to load ML forecast model from '{self.model_path}': {err}")
            self.model_artifact = None
            self.model = None
            self.model_available = False

    def is_available(self) -> bool:
        """Check whether a valid ML model is loaded and ready for inference."""
        return self.model_available

    def get_status(self) -> Dict[str, Any]:
        """Retrieve current model status metadata."""
        model_type = "forecast"
        model_version = None
        if self.model_available and isinstance(self.model_artifact, dict):
            model_type = self.model_artifact.get("model_type", "forecast")
            model_version = self.model_artifact.get("model_version", "1.0.0")

        return {
            "model_available": self.model_available,
            "model_type": model_type,
            "model_path": "models/forecast_model.joblib",
            "model_version": model_version,
        }

    def predict_forecast(self, feeder_id: str, features: Optional[Dict[str, Any]] = None) -> Optional[ForecastResponse]:
        """Execute model inference for a feeder if model is available.

        Args:
            feeder_id (str): Target feeder identifier (e.g. 'F07').
            features (Optional[Dict[str, Any]]): Custom feature dictionary provided by caller.

        Returns:
            Optional[ForecastResponse]: Predicted forecast model with source='ml', or None if unavailable/inference fails.
        """
        if not self.model_available or self.model is None:
            return None

        try:
            fid = feeder_id.upper()
            feeder = get_feeder_by_id(fid)

            # Baseline current state for the feeder
            current_load = feeder.current_load if feeder else 90.0
            now = datetime.now()
            hour = now.hour
            dow = now.weekday()
            is_weekend = 1 if dow >= 5 else 0
            is_peak = 1 if (9 <= hour <= 12 or 17 <= hour <= 21) else 0

            row_data = {
                "load_mw": current_load,
                "temperature_c": 28.0,
                "hour": hour,
                "day_of_week": dow,
                "is_weekend": is_weekend,
                "is_peak_hour": is_peak,
                "lag_1": current_load * 0.98,
                "lag_2": current_load * 0.96,
                "lag_4": current_load * 0.93,
                "rolling_mean": current_load * 0.97,
                "feeder_F01": 1.0 if fid == "F01" else 0.0,
                "feeder_F04": 1.0 if fid == "F04" else 0.0,
                "feeder_F07": 1.0 if fid == "F07" else 0.0,
                "feeder_F12": 1.0 if fid == "F12" else 0.0,
            }

            # Override with custom features if provided
            if features:
                row_data.update(features)

            # Build DataFrame matching model feature columns
            if self.feature_columns:
                input_df = pd.DataFrame([row_data])[self.feature_columns]
            else:
                input_df = pd.DataFrame([row_data])

            preds = self.model.predict(input_df)

            # Unpack predictions [15m, 30m, 45m, 60m]
            if preds is not None and len(preds) > 0:
                p_row = preds[0]
                return ForecastResponse(
                    m15=round(float(p_row[0]), 1),
                    m30=round(float(p_row[1]), 1),
                    m45=round(float(p_row[2]), 1),
                    m60=round(float(p_row[3]), 1),
                    source="ml",
                )
        except Exception as err:
            logger.warning(f"ML model inference failed for feeder '{feeder_id}': {err}. Falling back to mock forecast.")

        return None


ml_service = MLForecastService.get_instance()
