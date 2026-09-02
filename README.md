# GridGuard AI — AI Grid Copilot

> **Predictive Monitoring & Flexibility Optimization Platform for Distribution Grids**

**Core Operational Flow**:  
`Forecast` $\rightarrow$ `Explain` $\rightarrow$ `Decide` $\rightarrow$ `Simulate` $\rightarrow$ `Prevent`

---

## 1. Project Overview

GridGuard AI is an AI Grid Copilot designed to provide real-time decision support for distribution grid operators. By integrating machine learning load forecasting, rule-based stress risk analysis, multi-criteria resource optimization, counterfactual scenario simulation, and natural language copilot messaging, GridGuard AI empowers operators to mitigate predicted feeder overloads before they occur.

> **SAFETY & DATA DISCLAIMER**: The historical dataset (`ml/data/feeder_load_history.csv`) and action dispatches are **simulated for demonstration purposes**. GridGuard AI does not connect to or control physical electrical grid hardware or external utility infrastructure.

---

## 2. Technology Stack

- **Backend Framework**: FastAPI, Uvicorn, Pydantic v2
- **Database & ORM**: PostgreSQL 15, SQLAlchemy 2.x, `psycopg2-binary`
- **Machine Learning**: `scikit-learn` (HistGradientBoosting MultiOutputRegressor), XGBoost, Pandas, NumPy, Joblib
- **AI Copilot**: Google Gemini API (`google-genai` v1.47.0) with deterministic fallback
- **Frontend (Target)**: React, Vite, Tailwind CSS, Recharts, Leaflet

---

## 3. Quick Start Guide

### Option A: Local Development

1. **Start PostgreSQL Database (Docker Compose)**:
   ```bash
   docker-compose up -d postgres
   ```

2. **Activate Python Virtual Environment & Install Dependencies**:
   ```bash
   cd backend
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Start FastAPI Backend Server**:
   ```bash
   uvicorn app.main:app --reload
   ```

The backend server will run at `http://localhost:8000`.

### Option B: Full Docker Deployment

```bash
docker-compose up -d
```

---

## 4. Health & Documentation Endpoints

- **Health Check**: `GET http://localhost:8000/health`
- **Database Status**: `GET http://localhost:8000/api/db/status`
- **Database Summary**: `GET http://localhost:8000/api/db/summary`
- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc UI**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Frontend API Contract Guide**: [`docs/API_CONTRACT.md`](file:///Users/kopalkanodia/GridGuard_Kopal/docs/API_CONTRACT.md)
- **End-to-End Demo Scenario Doc**: [`docs/DEMO_SCENARIO.md`](file:///Users/kopalkanodia/GridGuard_Kopal/docs/DEMO_SCENARIO.md)

---

## 5. Running the Hackathon Demo Scenario

To execute the end-to-end hackathon demo scenario pipeline (`GET /api/demo/F07`):

```bash
# Execute standalone test script
python backend/test_demo_scenario.py
```

Or make an HTTP GET request:
`GET http://localhost:8000/api/demo/F07`
