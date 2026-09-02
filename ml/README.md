# GridGuard AI - Machine Learning Forecast Pipeline

This module contains the synthetic time-series dataset generation, ML model training script, and documentation for the **GridGuard AI Grid Copilot** load forecasting engine.

> **DISCLAIMER**: The dataset used here (`ml/data/feeder_load_history.csv`) is **synthetic demonstration data** generated deterministically to train a multi-horizon load forecasting model for hackathon evaluation.

---

## Pipeline Overview

```
ml/generate_data.py  ──►  ml/data/feeder_load_history.csv
                                    │
                                    ▼
                         ml/train_forecast_model.py
                                    │
                                    ▼
                      backend/models/forecast_model.joblib
                                    │
                                    ▼
                      FastAPI (MLForecastService)
```

---

## 1. Dataset Generation (`ml/generate_data.py`)

- **Feeders**: `F01`, `F04`, `F07`, `F12` (4 feeders).
- **Time Range**: 30 days of 15-minute resolution time-series data (11,488 rows).
- **Temporal Patterns**:
  - Diurnal demand cycles (morning peak ~10:00, evening peak ~19:00).
  - Temperature variation (AC demand factor for temperatures > 25°C).
  - Weekend factor (5% lower load on weekends).
  - Feeder `F07` is configured as a high-utilization feeder for overload demonstration.

---

## 2. Model Architecture & Training (`ml/train_forecast_model.py`)

- **Model Type**: `scikit-learn HistGradientBoosting MultiOutputRegressor`
- **Train / Test Split**: 80% chronological train set (9,190 rows), 20% test set (2,298 rows).
- **Input Features**:
  - `load_mw` (Current feeder load)
  - `temperature_c` (Ambient temperature)
  - `hour`, `day_of_week`, `is_weekend`, `is_peak_hour` (Time features)
  - `lag_1`, `lag_2`, `lag_4` (Historical load lags at 15m, 30m, 60m)
  - `rolling_mean` (4-period rolling mean load)
  - `feeder_F01`, `feeder_F04`, `feeder_F07`, `feeder_F12` (One-hot feeder indicators)
- **Target Horizons**: `target_15m`, `target_30m`, `target_45m`, `target_60m` (Future load at +15m, +30m, +45m, +60m).

---

## 3. Model Evaluation Results (Test Set)

| Horizon | Mean Absolute Error (MAE) | Root Mean Squared Error (RMSE) |
| :--- | :---: | :---: |
| **15 minutes (+15m)** | 1.767 MW | 2.220 MW |
| **30 minutes (+30m)** | 1.792 MW | 2.250 MW |
| **45 minutes (+45m)** | 1.768 MW | 2.230 MW |
| **60 minutes (+60m)** | 1.772 MW | 2.229 MW |

---

## 4. How to Retrain the Model

To regenerate data and retrain the model artifact:

```bash
# 1. Activate backend virtual environment
source backend/venv/bin/activate

# 2. Generate synthetic historical dataset
python ml/generate_data.py

# 3. Train model & save artifact
python ml/train_forecast_model.py
```

The output model artifact will be saved directly to:
`backend/models/forecast_model.joblib`
