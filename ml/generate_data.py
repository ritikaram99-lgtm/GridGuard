"""Synthetic data generator for GridGuard AI ML forecast model.

Generates 30 days of 15-minute resolution historical feeder load data for feeders
F01, F04, F07, and F12 with realistic temporal patterns, temperature influence,
and target shift windows.
"""

import os
from pathlib import Path
import numpy as np
import pandas as pd

# Directory setup
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH = DATA_DIR / "feeder_load_history.csv"


def generate_synthetic_data() -> pd.DataFrame:
    """Generate 30 days of 15-minute resolution historical data for 4 feeders."""
    np.random.seed(42)

    # 30 days of 15-min intervals: 30 * 24 * 4 = 2880 timestamps
    timestamps = pd.date_range(start="2026-08-01 00:00:00", periods=2880, freq="15min")

    feeders_config = {
        "F01": {"base_load": 50.0, "peak_add": 8.0, "noise_std": 1.0},
        "F04": {"base_load": 82.0, "peak_add": 12.0, "noise_std": 1.5},
        "F07": {"base_load": 92.0, "peak_add": 20.0, "noise_std": 2.0},  # High utilization demo feeder
        "F12": {"base_load": 108.0, "peak_add": 14.0, "noise_std": 2.0},
    }

    all_dfs = []

    for feeder_id, cfg in feeders_config.items():
        df = pd.DataFrame({"timestamp": timestamps})
        df["feeder_id"] = feeder_id

        # Time features
        df["hour"] = df["timestamp"].dt.hour
        df["minute"] = df["timestamp"].dt.minute
        df["day_of_week"] = df["timestamp"].dt.dayofweek
        df["is_weekend"] = df["day_of_week"].apply(lambda x: 1 if x >= 5 else 0)
        df["is_peak_hour"] = df["hour"].apply(lambda h: 1 if (9 <= h <= 12 or 17 <= h <= 21) else 0)

        # Diurnal diurnal temperature cycle (20°C overnight, 32°C afternoon peak)
        hour_radians = (df["hour"] + df["minute"] / 60.0 - 14.0) * (2 * np.pi / 24)
        df["temperature_c"] = 26.0 - 6.0 * np.cos(hour_radians) + np.random.normal(0, 0.5, len(df))

        # Diurnal load profile
        time_fraction = df["hour"] + df["minute"] / 60.0
        # Morning peak around 10:00, evening peak around 19:00
        morning_peak = np.exp(-((time_fraction - 10.0) ** 2) / 8.0)
        evening_peak = np.exp(-((time_fraction - 19.0) ** 2) / 10.0)
        diurnal_factor = morning_peak + 1.2 * evening_peak

        # Weekend reduction factor (5% reduction on weekend)
        weekend_mult = np.where(df["is_weekend"] == 1, 0.95, 1.0)

        # Temperature load factor (AC load increase above 25°C)
        temp_factor = np.maximum(0, df["temperature_c"] - 25.0) * 0.4

        # Calculate base load curve
        raw_load = (
            cfg["base_load"]
            + cfg["peak_add"] * diurnal_factor * weekend_mult
            + temp_factor
            + np.random.normal(0, cfg["noise_std"], len(df))
        )
        df["load_mw"] = np.round(np.maximum(10.0, raw_load), 2)

        # Generate Historical Lags
        df["lag_1"] = df["load_mw"].shift(1)
        df["lag_2"] = df["load_mw"].shift(2)
        df["lag_4"] = df["load_mw"].shift(4)
        df["rolling_mean"] = df["load_mw"].rolling(window=4).mean()

        # Generate Targets (shifted future loads)
        df["target_15m"] = df["load_mw"].shift(-1)
        df["target_30m"] = df["load_mw"].shift(-2)
        df["target_45m"] = df["load_mw"].shift(-3)
        df["target_60m"] = df["load_mw"].shift(-4)

        # Drop rows with NaNs resulting from shift/rolling
        df = df.dropna().reset_index(drop=True)
        all_dfs.append(df)

    final_df = pd.concat(all_dfs, ignore_index=True)
    final_df.to_csv(CSV_PATH, index=False)
    print(f"Generated {len(final_df)} synthetic records across 4 feeders.")
    print(f"Saved to: {CSV_PATH}")
    return final_df


if __name__ == "__main__":
    generate_synthetic_data()
