"""Utility module for GridGuard AI backend."""

from app.utils.config import get_gemini_api_key, get_forecast_model_path, get_database_url, get_cors_origins

__all__ = [
    "get_gemini_api_key",
    "get_forecast_model_path",
    "get_database_url",
    "get_cors_origins",
]
