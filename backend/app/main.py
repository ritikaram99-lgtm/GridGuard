from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import (
    feeders_router,
    forecast_router,
    risk_router,
    recommendations_router,
    simulation_router,
    copilot_router,
    model_router,
    db_router,
    replay_router,
    dispatch_router,
    demo_router,
)
from app.utils.config import get_cors_origins

app = FastAPI(
    title="GridGuard AI",
    description="AI Grid Copilot Backend - Real-Time Predictive Monitoring & Optimization API",
    version="1.0.0",
)

# Add CORS Middleware for frontend integration (Vite dev server: http://localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(feeders_router)
app.include_router(forecast_router)
app.include_router(risk_router)
app.include_router(recommendations_router)
app.include_router(simulation_router)
app.include_router(copilot_router)
app.include_router(model_router)
app.include_router(db_router)
app.include_router(replay_router)
app.include_router(dispatch_router)
app.include_router(demo_router)


@app.get("/")
def read_root():
    return {"message": "GridGuard AI Backend is running"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
