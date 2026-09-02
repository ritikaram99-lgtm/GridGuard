# GridGuard AI — End-to-End Demo Scenario (`F07 Overload Prevention`)

This document describes the complete deterministic hackathon demonstration pipeline for **GridGuard AI**.

> **SAFETY & DATA DISCLAIMER**: The historical time-series dataset (`ml/data/feeder_load_history.csv`) and action dispatches are **simulated for demonstration purposes**. GridGuard AI does not connect to or control physical electrical grid hardware or external utility devices.

---

## 1. Scenario Summary

- **Scenario Identifier**: `F07_OVERLOAD_PREVENTION`
- **Target Feeder**: `F07` (Feeder 07 — Capacity: 100.0 MW, High Utilization)
- **Primary Endpoint**: `GET /api/demo/F07`
- **Goal**: Demonstrate how GridGuard AI moves from predictive overload detection to automated optimization recommendation, counterfactual simulation, operator authorization, and natural language copilot messaging in a single pipeline.

---

## 2. End-to-End Execution Flow

```
1. Current Feeder Specs  ──►  capacity: 100 MW, current_load: 97 MW, voltage: 0.95 p.u.
                                       │
                                       ▼
2. ML Load Forecast       ──►  15m: 97.1 MW, 30m: 98.0 MW, 45m: 99.1 MW, 60m: 100.1 MW (source: "ml")
                                       │
                                       ▼
3. Risk Engine           ──►  score: 60/100 (MODERATE), time_to_overload: 60.0 min
                                       │
                                       ▼
4. Recommendation Engine ──►  required_reduction: 0.1 MW -> selected_actions: ["EV_SHIFT"] (7.0 MW)
                                       │
                                       ▼
5. What-If Simulation     ──►  ev_shift: 7.0 MW -> simulated_load: 93.1 MW (SAFE)
                                       │
                                       ▼
6. Simulated Dispatch     ──►  status: "DISPATCHED", logged in PostgreSQL actions table
                                       │
                                       ▼
7. AI Copilot Layer       ──►  Operator natural language explanation banner
                                       │
                                       ▼
8. Final Outcome          ──►  status_message: "OVERLOAD_PREVENTED", overload_avoided: true
```

---

## 3. Representative API Response (`GET /api/demo/F07`)

```json
{
  "scenario": "F07_OVERLOAD_PREVENTION",
  "feeder_id": "F07",
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
  },
  "simulation": {
    "feeder_id": "F07",
    "forecast_peak": 100.1,
    "capacity": 100.0,
    "changes": {
      "ev_shift": 7.0,
      "battery": 0.0,
      "industrial": 0.0
    },
    "total_reduction": 7.0,
    "simulated_load": 93.1,
    "status": "SAFE"
  },
  "dispatch": {
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
  },
  "copilot": {
    "feeder_id": "F07",
    "summary": "Feeder F07 is operating under MODERATE risk (score: 60/100) and is predicted to exceed its 100 MW capacity within 60 minutes.",
    "risk_explanation": "Risk score is 60 (MODERATE). The main contributors are: Forecast exceeds capacity, High utilization, Voltage deterioration.",
    "recommended_action_explanation": "Recommended actions are EV_SHIFT to mitigate predicted overload.",
    "expected_outcome": "Expected load after recommended actions is 93 MW, so the overload is avoided (reduced from 100 MW peak).",
    "operator_message": "Act within the 60-minute overload window to authorize mitigation.",
    "source": "deterministic_fallback"
  },
  "outcome": {
    "scenario_name": "F07_OVERLOAD_PREVENTION",
    "before_load_mw": 100.1,
    "after_load_mw": 93.1,
    "overload_before": true,
    "overload_after": false,
    "overload_avoided": true,
    "status_message": "OVERLOAD_PREVENTED"
  }
}
```

---

## 4. How to Run the End-to-End Test

Run the backend test script directly:

```bash
python backend/test_demo_scenario.py
```
