"""ML Model Training Script for GridGuard AI Feeder Forecast.

Trains a scikit-learn HistGradientBoosting Multi-Output Regression model on
historical time-series data to predict 15m, 30m, 45m, and 60m feeder loads
using a chronological 80/20 train/test split. Saves trained pipeline artifact to
`backend/models/forecast_model.joblib`.
"""

import os
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from sklearn.multioutput import MultiOutputRegressor

# Directory setup
BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "feeder_load_history.csv"
MODEL_OUTPUT_PATH = BASE_DIR.parent / "backend" / "models" / "forecast_model.joblib"
MODEL_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def train_and_evaluate() -> None:
    """Train HistGradientBoosting MultiOutputRegressor and save model artifact."""
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Data file not found at '{DATA_PATH}'. Run generate_data.py first.")

    print(f"Loading historical dataset from: {DATA_PATH}")
    df = pd.read_csv(DATA_PATH)
    print(f"Dataset shape: {df.shape}")

    # Feature definitions
    base_features = [
        "load_mw",
        "temperature_c",
        "hour",
        "day_of_week",
        "is_weekend",
        "is_peak_hour",
        "lag_1",
        "lag_2",
        "lag_4",
        "rolling_mean",
    ]

    target_cols = ["target_15m", "target_30m", "target_45m", "target_60m"]

    # One-hot encode feeder_id
    df_encoded = pd.get_dummies(df, columns=["feeder_id"], prefix="feeder", dtype=float)
    feeder_cols = [c for c in df_encoded.columns if c.startswith("feeder_")]

    feature_cols = base_features + feeder_cols

    # Chronological Train / Test Split (80% train, 20% test)
    split_idx = int(len(df_encoded) * 0.8)

    X_train = df_encoded.iloc[:split_idx][feature_cols]
    y_train = df_encoded.iloc[:split_idx][target_cols]

    X_test = df_encoded.iloc[split_idx:][feature_cols]
    y_test = df_encoded.iloc[split_idx:][target_cols]

    print(f"Training rows: {len(X_train)} | Testing rows: {len(X_test)}")
    print("Training scikit-learn HistGradientBoosting MultiOutputRegressor model...")

    # Base model: HistGradientBoostingRegressor
    base_model = HistGradientBoostingRegressor(
        max_iter=100,
        max_depth=5,
        learning_rate=0.08,
        random_state=42,
    )
    model = MultiOutputRegressor(base_model)
    model.fit(X_train, y_train)

    # Evaluate on test set
    y_pred = model.predict(X_test)

    metrics = {}
    horizons = ["15m", "30m", "45m", "60m"]

    print("\n--- Model Evaluation Results (Test Set) ---")
    for idx, h in enumerate(horizons):
        mae = float(mean_absolute_error(y_test.iloc[:, idx], y_pred[:, idx]))
        rmse = float(root_mean_squared_error(y_test.iloc[:, idx], y_pred[:, idx]))
        metrics[h] = {"mae": mae, "rmse": rmse}
        print(f"{h} Forecast -> MAE: {mae:.3f} MW | RMSE: {rmse:.3f} MW")

    # Package model artifact wrapper for backend consumption
    artifact = {
        "model": model,
        "feature_columns": feature_cols,
        "base_features": base_features,
        "feeder_cols": feeder_cols,
        "target_columns": ["15m", "30m", "45m", "60m"],
        "model_type": "scikit-learn HistGradientBoosting MultiOutputRegressor",
        "model_version": "1.0.0",
        "metrics": metrics,
    }

    joblib.dump(artifact, MODEL_OUTPUT_PATH)
    print(f"\nModel successfully trained and saved to:\n  {MODEL_OUTPUT_PATH}")


if __name__ == "__main__":
    train_and_evaluate()
