"""Configuration module for GridGuard AI backend environment variables and project paths."""

import os
from pathlib import Path
from typing import List, Optional

# Base directory for the backend project (backend/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

DEFAULT_DATABASE_URL = "postgresql+psycopg2://gridguard:gridguard@localhost:5432/gridguard"


def get_gemini_api_key() -> Optional[str]:
    """Retrieve the Gemini API key from environment variables."""
    return os.environ.get("GEMINI_API_KEY")


def get_forecast_model_path() -> Path:
    """Retrieve resolved path to the trained forecast model artifact.

    Default: backend/models/forecast_model.joblib
    Can be overridden via FORECAST_MODEL_PATH environment variable.
    """
    custom_path = os.environ.get("FORECAST_MODEL_PATH")
    if custom_path:
        p = Path(custom_path)
        return p if p.is_absolute() else BASE_DIR / p
    return BASE_DIR / "models" / "forecast_model.joblib"


def get_database_url() -> str:
    """Retrieve the database connection string from environment variables."""
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_cors_origins() -> List[str]:
    """Retrieve allowed CORS origins from environment variable or default development origins."""
    raw_origins = os.environ.get("CORS_ORIGINS")
    if raw_origins:
        return [o.strip() for o in raw_origins.split(",") if o.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
