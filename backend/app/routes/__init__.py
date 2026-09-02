"""API routes package."""

from app.routes.feeders import router as feeders_router
from app.routes.forecast import router as forecast_router
from app.routes.risk import router as risk_router
from app.routes.recommendations import router as recommendations_router
from app.routes.simulation import router as simulation_router
from app.routes.copilot import router as copilot_router
from app.routes.model import router as model_router
from app.routes.db import router as db_router
from app.routes.replay import router as replay_router
from app.routes.dispatch import router as dispatch_router
from app.routes.demo import router as demo_router

__all__ = [
    "feeders_router",
    "forecast_router",
    "risk_router",
    "recommendations_router",
    "simulation_router",
    "copilot_router",
    "model_router",
    "db_router",
    "replay_router",
    "dispatch_router",
    "demo_router",
]
