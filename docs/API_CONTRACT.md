# GridGuard AI — Frontend Integration & API Contract Documentation

This document serves as the official integration guide for the **GridGuard AI React/Vite Frontend**. It defines backend API endpoints, request/response contracts, data types, error formats, and architectural boundaries.

---

## 1. Environment & Base URL

- **Development Base URL**: `http://localhost:8000`
- **Supported Frontend Origins (CORS Enabled)**:
  - `http://localhost:5173` (Default Vite Development Server)
  - `http://127.0.0.1:5173`
  - `http://localhost:3000`
- **Interactive Documentation**:
  - **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
  - **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 2. Standard Feeder Identifiers

The system manages 4 primary grid feeders:
- `F01`: Feeder 01 (Capacity: 80.0 MW)
- `F04`: Feeder 04 (Capacity: 120.0 MW)
- `F07`: Feeder 07 (**Primary Demo Feeder** — Capacity: 100.0 MW, High Utilization)
- `F12`: Feeder 12 (Capacity: 150.0 MW)

---

## 3. Core API Endpoint Reference

| Category | Method | Endpoint | Description |
| :--- | :---: | :--- | :--- |
| **System** | `GET` | `/` | Verify backend server status |
| **System** | `GET` | `/health` | Lightweight health check |
| **Feeders** | `GET` | `/api/feeders` | List all grid feeders |
| **Feeders** | `GET` | `/api/feeders/{feeder_id}` | Get specific feeder baseline specs |
| **Dashboard** | `GET` | `/api/feeders/{feeder_id}/intelligence` | **Primary Dashboard Endpoint** (Consolidated Payload) |
| **Forecast** | `GET` | `/api/forecast/{feeder_id}` | Get 15m/30m/45m/60m ML load predictions |
| **Risk** | `GET` | `/api/risk/{feeder_id}` | Get stress score (0-100), risk level, TTO, and contributors |
| **Recommendation**| `POST` | `/api/recommendations/{feeder_id}`| Get automated multi-criteria optimization recommendations |
| **Simulation** | `POST` | `/api/simulate` | Run counterfactual "What If?" load reduction scenarios |
| **Dispatch** | `POST` | `/api/dispatch` | Operator flexibility action dispatch simulation |
| **Copilot** | `GET` | `/api/copilot/{feeder_id}` | AI Copilot operational explanation payload |
| **Replay** | `POST` | `/api/replay/query` | Chronological historical time-series query |
| **Replay** | `GET` | `/api/replay/{feeder_id}/latest` | Retrieve latest historical snapshot |
| **Replay** | `POST` | `/api/replay/{feeder_id}/ingest` | Persist a historical record into PostgreSQL `measurements` table |
| **Database** | `GET` | `/api/db/status` | Check PostgreSQL connection status |
| **Database** | `GET` | `/api/db/summary` | Query PostgreSQL table row counts |
| **Model** | `GET` | `/api/model/status` | Check ML forecast model availability status |

---

## 4. Primary Dashboard Contract (`GET /api/feeders/{feeder_id}/intelligence`)

Use this single endpoint to populate the main feeder operator view:

```json
{
  "feeder": {
    "id": "F07",
    "name": "Feeder 07",
    "capacity": 100.0,
    "current_load": 97.0,
    "voltage": 0.95,
    "location": {
      "latitude": 12.9716,
      "longitude": 77.5946
    }
  },
  "forecast": {
    "15m": 97.1,
    "30m": 98.0,
    "45m": 99.1,
    "60m": 100.1,
    "source": "ml"
  },
  "risk": {
    "score": 60.0,
    "level": "MODERATE",
    "time_to_overload": 60.0,
    "contributors": [
      {
        "name": "Forecast exceeds capacity",
        "impact": 30.0
      },
      {
        "name": "High utilization",
        "impact": 15.0
      },
      {
        "name": "Voltage deterioration",
        "impact": 15.0
      }
    ]
  },
  "recommendation": {
    "feeder_id": "F07",
    "predicted_load": 100.1,
    "capacity": 100.0,
    "required_reduction": 0.1,
    "actions": [
      "EV_SHIFT"
    ],
    "recommended_actions": [
      "EV_SHIFT"
    ],
    "predicted_after": 93.1,
    "expected_load_after": 93.1,
    "status": "OVERLOAD_AVOIDED",
    "action_details": [
      {
        "action_type": "EV_SHIFT",
        "load_reduction": 7.0,
        "cost": 14.0,
        "disruption": 7.0
      }
    ]
  }
}
```

> **IMPORTANT**: The frontend should **NOT hard-code** old mock values (`99/103/108/110`). Forecast values are generated dynamically by the trained XGBoost / HistGradientBoosting ML model (`source: "ml"`).

---

## 5. Specific Service Contracts

### A. Load Forecast (`GET /api/forecast/{feeder_id}`)
Direct payload for rendering time-series demand charts:
```json
{
  "15m": 97.1,
  "30m": 98.0,
  "45m": 99.1,
  "60m": 100.1,
  "source": "ml"
}
```

### B. What-If Simulation (`POST /api/simulate`)
Request:
```json
{
  "feeder_id": "F07",
  "changes": {
    "ev_shift": 7.0,
    "battery": 8.0,
    "industrial": 0.0
  }
}
```
Response:
```json
{
  "feeder_id": "F07",
  "forecast_peak": 100.1,
  "capacity": 100.0,
  "changes": {
    "ev_shift": 7.0,
    "battery": 8.0,
    "industrial": 0.0
  },
  "total_reduction": 15.0,
  "simulated_load": 85.1,
  "status": "SAFE"
}
```

### C. Operator Action Dispatch (`POST /api/dispatch`)
Request:
```json
{
  "feeder_id": "F07",
  "actions": [
    {
      "action_type": "EV_SHIFT",
      "reduction_mw": 7.0
    }
  ]
}
```
Response:
```json
{
  "feeder_id": "F07",
  "status": "DISPATCHED",
  "forecast_peak": 100.1,
  "capacity": 100.0,
  "total_reduction": 7.0,
  "simulated_load": 93.1,
  "overload_avoided": true,
  "actions": [
    {
      "action_type": "EV_SHIFT",
      "reduction_mw": 7.0,
      "status": "DISPATCHED"
    }
  ]
}
```

---

## 6. Flexible Resources & Maximum Limits (F07 Demo)

- `EV_SHIFT`: Max available reduction = **7.0 MW**
- `BATTERY`: Max available reduction = **8.0 MW**
- `INDUSTRIAL`: Max available reduction = **5.0 MW**

---

## 7. Ownership & Architectural Responsibilities

### Backend-Owned Calculations (DO NOT calculate on Frontend):
- ML Load Forecast inference
- Grid stress risk score (0–100) & Risk Level classification (`LOW`, `MODERATE`, `HIGH`, `CRITICAL`)
- Time-To-Overload (TTO) calculation in minutes
- Multi-criteria recommendation optimization
- Counterfactual scenario simulation load math
- Dispatch validation & PostgreSQL logging
- AI Copilot natural language message synthesis

### Frontend Display Responsibilities:
- Rendering time-series forecast line charts
- Displaying risk gauges, level badges, and impact breakdown bars
- Displaying recommendation cards & action authorization buttons
- Interacting with simulation sliders (`ev_shift`, `battery`, `industrial`)
- Triggering operator action dispatch requests
- Rendering AI Copilot operator explanation banners

---

## 8. Standard Error Format

All error responses from the backend follow FastAPI's standard format:

```json
{
  "detail": "Human-readable error description"
}
```

### HTTP Status Code Conventions:
- **`200 OK`**: Successful request execution.
- **`400 Bad Request`**: Invalid business request (e.g. invalid timestamp range, reduction exceeding resource max, negative reduction, empty actions).
- **`404 Not Found`**: Target feeder or resource not found (e.g. unknown `feeder_id`).
- **`422 Unprocessable Entity`**: Pydantic request body validation error (missing required fields or invalid types).
- **`500 Internal Server Error`**: Unexpected backend failure.

---

## 9. Safety Disclaimer

> **DISPATCH & DEMO DISCLAIMER**: All flexibility action dispatches, what-if simulations, and historical time-series replays are **simulated for demonstration purposes**. The backend does not connect to or control physical electrical grid hardware.
