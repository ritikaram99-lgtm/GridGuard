# GridGuard AI - Backend Service

This is the FastAPI backend foundation for the **GridGuard AI** application—an AI Grid Copilot designed to monitor, forecast, and optimize grid feeder operations.

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI application entry point
│   ├── db/              # Database module & SQLAlchemy setup
│   ├── routes/          # API route handlers
│   ├── services/        # Business logic services & persistence repository
│   ├── schemas/         # Pydantic data schemas
│   ├── models/          # SQLAlchemy ORM data models
│   └── utils/           # Helper utilities
├── models/              # Trained ML model artifacts (.joblib)
├── test_demo_scenario.py# End-to-end hackathon demo scenario verification
├── requirements.txt     # Python dependencies
└── README.md            # Backend documentation
```

## Setup Instructions

### 1. Create a Virtual Environment

Navigate to the `backend` directory and create a virtual environment:

```bash
cd backend
python3 -m venv venv
```

Activate the virtual environment:

- **macOS / Linux:**
  ```bash
  source venv/bin/activate
  ```
- **Windows (Command Prompt / PowerShell):**
  ```cmd
  venv\Scripts\activate
  ```

### 2. Install Dependencies

Install the required packages using `pip`:

```bash
pip install -r requirements.txt
```

### 3. Start PostgreSQL Database

Start the PostgreSQL 15 database container using Docker Compose:

```bash
docker-compose up -d postgres
```

### 4. Start the FastAPI Server

Run the development server using Uvicorn with auto-reload enabled:

```bash
uvicorn app.main:app --reload
```

The backend server will start at `http://127.0.0.1:8000`.

## API Documentation

Once the server is running, interactive API documentation is available at:

- **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

## Core Endpoints

- `GET /` - Root endpoint verifying backend status.
- `GET /health` - Health check endpoint returning status `healthy`.
- `GET /api/db/status` - Check PostgreSQL database connectivity status (`connected: true/false`).
- `GET /api/db/summary` - Query database table counts (`feeders`, `measurements`, `predictions`, `alerts`, `actions`).
- `GET /api/model/status` - Check machine learning model loading and availability status.
- `GET /api/feeders` - List all grid feeders.
- `GET /api/feeders/{feeder_id}` - Get specific feeder details.
- `GET /api/feeders/{feeder_id}/intelligence` - Unified feeder intelligence dashboard payload.
- `GET /api/forecast/{feeder_id}` - Get 15m/30m/45m/60m load forecast (`source`: `ml` or `mock`).
- `GET /api/risk/{feeder_id}` - Get grid stress score, risk level, and time-to-overload.
- `POST /api/recommendations/{feeder_id}` - Get optimization recommendations.
- `POST /api/simulate` - Run counterfactual what-if scenario simulations.
- `POST /api/dispatch` - Operator flexibility action dispatch simulation.
- `GET /api/demo/{feeder_id}` - **End-to-End Hackathon Demo Orchestration Scenario** (`GET /api/demo/F07`).
- `GET /api/copilot/{feeder_id}` - AI Copilot operational natural-language explanation.
- `POST /api/replay/query` - Chronological historical time-series query across feeder records.
- `GET /api/replay/{feeder_id}/latest` - Retrieve the latest historical snapshot for a feeder.
- `POST /api/replay/{feeder_id}/ingest` - Persist a historical record into PostgreSQL measurements table.

## End-to-End Demo Scenario (`GET /api/demo/F07`)

> **SAFETY DISCLAIMER**: The demo scenario and action dispatches are **simulated for demonstration purposes**. GridGuard AI does not connect to or control physical electrical grid hardware or external utility devices.

Runs the complete end-to-end operational story:
1. Current Feeder Specs (`F07`)
2. Real ML Forecast (`source: "ml"`)
3. Grid Stress Risk Detection
4. Multi-Criteria Recommendation (`EV_SHIFT`)
5. Counterfactual What-If Simulation
6. Simulated Operator Dispatch
7. AI Copilot Operational Message
8. Final Outcome Assessment (`status_message: "OVERLOAD_PREVENTED"`, `overload_avoided: true`)

Run the standalone test script:
```bash
python test_demo_scenario.py
```

## Database Architecture & Persistence (PostgreSQL & SQLAlchemy 2.x)

- **Database URL**: Configured via `DATABASE_URL` environment variable (default: `postgresql+psycopg2://gridguard:gridguard@localhost:5432/gridguard`).
- **ORM Tables**: `feeders`, `measurements`, `predictions`, `alerts`, `actions`.
- **Status Endpoint**: `GET /api/db/status` returns connection diagnostics.
- **Summary Endpoint**: `GET /api/db/summary` returns PostgreSQL table row counts.

## Forecast Model Integration

- **Model Artifact Path**: Expected at `backend/models/forecast_model.joblib`.
- **ML Inference**: `MLForecastService` generates multi-horizon predictions with `"source": "ml"`.
- **Mock Fallback**: Operates with deterministic mock forecasts tagged with `"source": "mock"` if model artifact is removed.
