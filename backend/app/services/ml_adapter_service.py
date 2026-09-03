"""ML Adapter Service - real ML bridge for national demand forecasting,
10-feeder synthetic allocation (F01-F10), and the Grid Stress Engine.

Thin adapter between the FastAPI backend and the existing, authoritative
ml/src/ pipeline. This module does NOT reimplement any ML logic -- it
imports and calls the existing rolling_integration.py / direct_hourly_forecast.py /
regime_detector.py / feeder_generator.py / stress_engine.py functions exactly
as they exist under ml/src/. No ML source file is modified to support this
adapter.

DISCLAIMER / SCOPE (see ml/reports/*.md for full methodology):
- The NATIONAL forecast (`get_national_forecast`) is real Panama national
  electricity demand (MW), genuinely hourly, regime-aware, bias-corrected.
- The per-feeder outputs (`get_feeder_forecast` / `get_all_feeders_forecast`)
  allocate that real national forecast across 10 SYNTHETIC feeders (F01-F10)
  via ml/src/feeder_generator.py. Per that module's own docstring: the
  Mendeley Panama dataset has no real feeder-, substation-, or
  location-level measurements. Every feeder id, name, location, capacity,
  load, and voltage value is a documented simulation for exercising the risk
  pipeline end-to-end -- it must never be presented as real Panama feeder
  telemetry. Only the underlying NATIONAL demand driving the allocation is
  real.
- Stress scores / risk levels / time-to-overload for feeders come directly
  from ml/src/stress_engine.py (deterministic, rule-based, unmodified) run
  on top of that synthetic per-feeder allocation.
- The underlying models were trained on the Mendeley Panama dataset
  (2015-01-03 .. 2020-06-27 hourly). There is no "live now" in this
  dataset -- forecast origins must fall within that historical range. This
  adapter defaults to the latest valid origin when none is specified.
- Never fabricates minute-level (15/30/45/60m) values -- the ML models are
  genuinely hourly (t+1h .. t+24h) and nothing finer exists anywhere in the
  ml/ pipeline.
- Never fabricates a confidence value -- none is produced by the underlying
  models, so `ForecastResponse` never carries one.
"""

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ml/src/ lives three levels above backend/app/services/
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ML_SRC_DIR = _REPO_ROOT / "ml" / "src"

DATASET_COVERAGE_NOTE = (
    "Forecasts are produced from the Mendeley Panama national demand dataset "
    "(2015-01-03 .. 2020-06-27, hourly). There is no live/real-time data source "
    "in this pipeline -- forecast origins must fall within the dataset's historical range."
)

FEEDER_SYNTHETIC_WARNING = (
    "All feeder-level fields (capacity, location, load, voltage) are SIMULATED "
    "by ml/src/feeder_generator.py, allocated from the real national demand "
    "forecast. Panama's real feeder-level topology/measurements are not known "
    "to this project. Do not present feeder-level values as real telemetry."
)

# The 10 ML feeder ids, hardcoded here (matching ml/src/feeder_generator.py's
# FEEDER_DEFINITIONS exactly) so that OTHER services can tell "this id
# belongs to the ML feeder namespace" even when the adapter itself failed to
# initialize (e.g. a missing dependency) -- this is what lets the rest of the
# backend refuse to silently substitute unrelated legacy mock data for one of
# these ids, rather than only being able to make that call once ML is up.
KNOWN_ML_FEEDER_IDS = {"F01", "F02", "F03", "F04", "F05", "F06", "F07", "F08", "F09", "F10"}


def is_reserved_ml_feeder_id(feeder_id: str) -> bool:
    """True if feeder_id belongs to the ML feeder namespace (F01-F10) --
    regardless of whether the ML adapter is currently available. Callers use
    this to decide "this id must only ever be answered by the ML pipeline,
    never by legacy Bangalore mock data of the same id", even while ML is
    temporarily down (in which case the honest answer is 'not found', not a
    silent identity swap)."""
    return feeder_id.upper() in KNOWN_ML_FEEDER_IDS


class MLAdapterService:
    """Singleton bridging the FastAPI backend to the existing ml/src/ hourly
    forecasting pipeline: direct per-horizon XGBoost models
    (ml/models/direct_hourly/horizon_01.pkl .. horizon_24.pkl), the regime
    detector, and causal bias correction -- reused via direct function calls
    to ml/src/rolling_integration.py, not reimplemented here."""

    _instance: Optional["MLAdapterService"] = None

    def __init__(self) -> None:
        self.available: bool = False
        self._unavailable_reason: Optional[str] = None
        self._df: Optional[pd.DataFrame] = None
        self._detector: Any = None
        self._models: Optional[Dict[int, Any]] = None
        self._metadata: Optional[Dict[str, Any]] = None
        self._feature_cols: List[str] = []
        self._min_valid_origin: Optional[pd.Timestamp] = None
        self._max_valid_origin: Optional[pd.Timestamp] = None
        self._default_origin: Optional[pd.Timestamp] = None
        self._ri: Any = None  # rolling_integration module reference
        self._fg: Any = None  # feeder_generator module reference
        self._se: Any = None  # stress_engine module reference
        self._feeders: List[Dict[str, Any]] = []
        self._feeder_by_id: Dict[str, Dict[str, Any]] = {}
        self._feeder_ids: List[str] = []
        self._capacities: Optional[pd.DataFrame] = None
        self._load()

    @classmethod
    def get_instance(cls) -> "MLAdapterService":
        if cls._instance is None:
            cls._instance = MLAdapterService()
        return cls._instance

    def _load(self) -> None:
        """Load the real ML pipeline once, at service construction. Never
        modifies any ml/src/ file -- only imports existing, unmodified
        functions and model artifacts."""
        try:
            if str(_ML_SRC_DIR) not in sys.path:
                sys.path.insert(0, str(_ML_SRC_DIR))

            import direct_hourly_forecast as dhf  # noqa: local import by design (ml/src/ is not a package)
            import regime_detector as rd
            import rolling_integration as ri
            import feeder_generator as fg
            import stress_engine as se

            logger.info("ML adapter: loading real ML pipeline (24 direct hourly XGBoost models + regime detector)...")

            df = dhf.load_raw_demand()
            models, metadata = dhf.load_models_and_metadata()
            detector = rd.RegimeDetector(df)

            # Verify every model's feature contract matches its recorded metadata
            # before trusting any prediction from it (existing project convention).
            for h in range(1, ri.MAX_HORIZON + 1):
                booster_features = list(models[h].get_booster().feature_names)
                if booster_features != metadata["feature_list"]:
                    raise RuntimeError(f"horizon_{h:02d}.pkl feature_names do not match direct_hourly_metadata.json")

            valid_signals = detector.signals.dropna(subset=["primary_score"])
            min_valid_origin = valid_signals.index.min()
            max_valid_origin = df["datetime"].max() - pd.Timedelta(hours=ri.MAX_HORIZON)

            # 10-feeder synthetic allocation layer (existing, unmodified
            # ml/src/feeder_generator.py). Capacities are sized once from the
            # full historical synthetic allocation, exactly mirroring
            # rolling_integration.py's own setup step, so they stay
            # consistent with everything else the ML pipeline validated.
            logger.info("ML adapter: loading 10-feeder synthetic allocation layer (F01-F10)...")
            feeders = fg.get_feeder_definitions()
            assert len(feeders) == 10
            national_demand_series = fg.load_national_demand_series()
            historical_feeder_loads = fg.allocate_feeder_loads(national_demand_series, feeders, seed=fg.SEED, add_noise=True)
            capacities = fg.compute_feeder_capacities(feeders, historical_feeder_loads)

            self._df = df
            self._models = models
            self._metadata = metadata
            self._feature_cols = metadata["feature_list"]
            self._detector = detector
            self._ri = ri
            self._fg = fg
            self._se = se
            self._feeders = feeders
            self._feeder_by_id = {f["id"]: f for f in feeders}
            self._feeder_ids = [f["id"] for f in feeders]
            self._capacities = capacities
            self._min_valid_origin = min_valid_origin
            self._max_valid_origin = max_valid_origin
            self._default_origin = max_valid_origin

            self.available = True
            logger.info(
                f"ML adapter ready. Valid forecast-origin range: {min_valid_origin} .. {max_valid_origin}. "
                f"Default origin (when none requested): {self._default_origin}. "
                f"Feeders: {self._feeder_ids}."
            )
        except Exception as err:
            self._unavailable_reason = str(err)
            self.available = False
            logger.warning(f"ML adapter failed to initialize ({err}); real ML forecasting disabled, callers should fall back.")

    def is_available(self) -> bool:
        return self.available

    def get_status(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "reason": self._unavailable_reason,
            "valid_origin_range": (
                {"min": str(self._min_valid_origin), "max": str(self._max_valid_origin)}
                if self.available else None
            ),
            "default_origin": str(self._default_origin) if self.available else None,
            "dataset_coverage_note": DATASET_COVERAGE_NOTE,
        }

    def _resolve_origin(self, origin_datetime: Optional[str]) -> pd.Timestamp:
        """Validate/parse a requested forecast origin, or return the default
        (latest valid) origin when none is given. Shared by every public
        method below (national and per-feeder) so the same validation rules
        apply everywhere. Raises ValueError on any invalid origin."""
        if not self.available:
            raise ValueError(f"ML adapter is not available ({self._unavailable_reason}).")

        df = self._df
        if origin_datetime is None:
            origin = self._default_origin
        else:
            try:
                origin = pd.Timestamp(origin_datetime)
            except Exception as err:
                raise ValueError(f"origin_datetime '{origin_datetime}' could not be parsed as a timestamp: {err}")
            if origin not in set(df["datetime"]):
                raise ValueError(
                    f"origin_datetime {origin} is not an hourly timestamp present in the underlying "
                    f"Mendeley Panama dataset. {DATASET_COVERAGE_NOTE} "
                    f"Valid range: {self._min_valid_origin} .. {self._max_valid_origin}."
                )

        if origin < self._min_valid_origin or origin > self._max_valid_origin:
            raise ValueError(
                f"origin_datetime {origin} is outside the valid forecast-origin range "
                f"({self._min_valid_origin} .. {self._max_valid_origin}) -- insufficient lag history "
                f"before it, or insufficient remaining horizon after it, in the dataset."
            )
        return origin

    def _compute_national(self, origin: pd.Timestamp) -> Dict[str, Any]:
        """Core, real, genuine 24-hour NATIONAL forecast computation (regime-
        aware, bias-corrected direct XGBoost, or previous-day fallback) --
        computed via direct calls into rolling_integration.py's existing,
        unmodified functions. Returns both the public-shaped fields (used by
        get_national_forecast) and raw values (current_nat / target_datetimes
        / final_mw) needed internally to build a feeder allocation
        trajectory -- those raw fields are NOT part of the public national
        forecast response."""
        ri = self._ri
        df = self._df

        # Regime status: existing, unmodified regime_detector.py, causal by construction.
        status = self._detector.status_at(origin)
        regime_status = status["regime_status"]
        regime_score = status["primary_score"]

        # Bias-corrected direct-model national forecast for a narrow window
        # ending at this origin -- existing, unmodified rolling_integration.py
        # function, same construction used for the full validated 2020 run.
        warm_up_start = origin - pd.Timedelta(hours=ri.BIAS_WINDOW_HOURS + ri.MAX_HORIZON + 7 * 24)
        national_long = ri.compute_national_forecasts(df, self._models, self._feature_cols, warm_up_start, origin)
        group = national_long[national_long["origin_datetime"] == origin].sort_values("horizon")
        if len(group) != ri.MAX_HORIZON:
            raise RuntimeError(f"Internal error: expected {ri.MAX_HORIZON} horizon rows for origin {origin}, got {len(group)}")

        # Same-hour-previous-day fallback, verified never to reference the future.
        demand_by_dt = df.set_index("datetime")["nat_demand"]
        prev_day_source = origin + pd.to_timedelta(group["horizon"] - 24, unit="h")
        if not (prev_day_source <= origin).all():
            raise RuntimeError("Fallback source timestamp computed after origin -- refusing to serve (leakage guard).")
        prev_day_pred = prev_day_source.map(demand_by_dt).values

        if regime_status == "NORMAL":
            final_mw = group["bias_corrected_pred"].values
            forecast_method = "BIAS_CORRECTED_DIRECT_XGBOOST"
        else:
            final_mw = prev_day_pred
            forecast_method = "PREVIOUS_DAY_FALLBACK"

        target_datetimes = list(pd.to_datetime(group["target_datetime"].values))
        hourly = [
            {"horizon": int(h), "timestamp": str(ts), "load_mw": float(mw)}
            for h, ts, mw in zip(group["horizon"].values, target_datetimes, final_mw)
        ]

        current_nat = float(demand_by_dt.loc[origin])

        return {
            "forecast_method": forecast_method,
            "regime_status": regime_status,
            "regime_score": float(regime_score),
            "hourly": hourly,
            "current_nat": current_nat,
            "target_datetimes": target_datetimes,
            "final_mw": np.asarray(final_mw, dtype=float),
        }

    def get_national_forecast(self, origin_datetime: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns the genuine 24-hour NATIONAL demand forecast (regime-aware,
        bias-corrected direct XGBoost, or previous-day fallback under a
        detected regime shift) -- computed via direct calls into
        rolling_integration.py's existing, unmodified functions, using the
        exact same construction validated in ml/reports/rolling_integration_report.md.

        Raises ValueError if the adapter is unavailable or the requested
        origin falls outside the dataset's valid range.
        """
        origin = self._resolve_origin(origin_datetime)
        nat = self._compute_national(origin)
        return {
            "origin_timestamp": str(origin),
            "forecast_method": nat["forecast_method"],
            "regime_status": nat["regime_status"],
            "regime_score": nat["regime_score"],
            "hourly": nat["hourly"],
            "scope": "national",
        }

    # -------------------------------------------------------------------
    # 10-feeder synthetic allocation + Grid Stress Engine (existing,
    # unmodified ml/src/feeder_generator.py + ml/src/stress_engine.py).
    # -------------------------------------------------------------------
    def is_ml_feeder(self, feeder_id: str) -> bool:
        return self.available and feeder_id.upper() in self._feeder_by_id

    def get_feeder_definitions(self) -> List[Dict[str, Any]]:
        """Returns the 10 ML feeders (id, name, type, location, capacity_mw)
        -- capacity_mw computed once at load time from the full historical
        synthetic allocation via feeder_generator.compute_feeder_capacities.
        SYNTHETIC data, see FEEDER_SYNTHETIC_WARNING."""
        if not self.available:
            raise ValueError(f"ML adapter is not available ({self._unavailable_reason}).")
        return [
            {
                "id": fid,
                "name": f["name"],
                "type": f["type"],
                "location": f["location"],
                "capacity_mw": float(self._capacities.loc[fid, "capacity_mw"]),
            }
            for fid, f in self._feeder_by_id.items()
        ]

    def _build_feeder_trajectory_df(self, origin: pd.Timestamp, nat: Dict[str, Any]) -> pd.DataFrame:
        """Builds the genuine 25-point (h=0 real actual + h=1..24 real
        forecast) national trajectory for this origin, then allocates it
        across all 10 feeders via feeder_generator.build_feeder_trajectories
        (existing, unmodified, deterministic/noise-free allocation --
        identical construction to rolling_integration.py's own per-origin
        loop)."""
        fg = self._fg
        national_index = pd.DatetimeIndex([origin] + nat["target_datetimes"])
        national_values = np.concatenate([[nat["current_nat"]], nat["final_mw"]])
        national_traj = pd.Series(national_values, index=national_index, name="national_forecast_trajectory")
        return fg.build_feeder_trajectories(national_traj, self._feeders)

    def _feeder_snapshot(self, fid: str, origin: pd.Timestamp, nat: Dict[str, Any],
                          feeder_traj_df: pd.DataFrame) -> Dict[str, Any]:
        """Evaluates one feeder's own allocated hourly trajectory through the
        existing, unmodified Grid Stress Engine (ml/src/stress_engine.py).
        Every MW/utilization/voltage/stress value here is feeder-specific --
        not a copy of the national forecast."""
        fg, se = self._fg, self._se
        feeder_def = self._feeder_by_id[fid]
        traj = feeder_traj_df[fid]
        cap = float(self._capacities.loc[fid, "capacity_mw"])

        current_load = float(traj.iloc[0])
        forecast_load_24h = float(traj.iloc[-1])
        util_traj = (traj / cap).values
        voltage_traj = fg.simulate_voltage(util_traj, seed=fg.SEED, add_noise=False)
        voltage_pu = float(voltage_traj[0])

        score, components = se.compute_stress_score(current_load, forecast_load_24h, cap, voltage_pu)
        risk_level = se.classify_stress(score)
        tto = se.time_to_overload(traj, cap)
        weights = se.STRESS_WEIGHTS
        component_points = {k: round(components[k] * weights[k] * 100.0, 4) for k in weights}

        hourly = [
            {"horizon": h, "timestamp": str(traj.index[h]), "load_mw": float(traj.iloc[h])}
            for h in range(1, len(traj))
        ]

        return {
            "feeder_id": fid,
            "name": feeder_def["name"],
            "type": feeder_def["type"],
            "location": feeder_def["location"],
            "capacity_mw": cap,
            "current_load_mw": current_load,
            "forecast_load_mw_24h": forecast_load_24h,
            "current_utilization": current_load / cap,
            "forecast_utilization_24h": forecast_load_24h / cap,
            "voltage_pu": voltage_pu,
            "hourly": hourly,
            "stress_score": score,
            "risk_level": risk_level,
            "stress_components": components,
            "stress_component_points": component_points,
            "time_to_overload": {
                "overload_predicted": bool(tto["overload_predicted"]),
                "time_to_overload_hours": tto["time_to_overload_hours"],
                "crossing_time": str(tto["crossing_time"]) if tto["crossing_time"] is not None else None,
                "resolution_note": tto["resolution_note"],
            },
            "origin_timestamp": str(origin),
            "forecast_method": nat["forecast_method"],
            "regime_status": nat["regime_status"],
            "regime_score": nat["regime_score"],
            "scope": "feeder",
        }

    def get_feeder_forecast(self, feeder_id: str, origin_datetime: Optional[str] = None) -> Dict[str, Any]:
        """Returns one feeder's own allocated hourly forecast + Grid Stress
        Engine evaluation (score/risk_level/time_to_overload), derived from
        the real national forecast via the existing, unmodified feeder
        allocation + stress engine. SYNTHETIC feeder data -- see
        FEEDER_SYNTHETIC_WARNING. Raises ValueError if unavailable, the
        origin is invalid, or feeder_id is not one of F01-F10."""
        fid = feeder_id.upper()
        if not self.is_ml_feeder(fid):
            raise ValueError(f"'{feeder_id}' is not one of the 10 ML feeders ({self._feeder_ids}).")
        origin = self._resolve_origin(origin_datetime)
        nat = self._compute_national(origin)
        feeder_traj_df = self._build_feeder_trajectory_df(origin, nat)
        return self._feeder_snapshot(fid, origin, nat, feeder_traj_df)

    def get_all_feeders_forecast(self, origin_datetime: Optional[str] = None) -> List[Dict[str, Any]]:
        """Same as get_feeder_forecast but for all 10 feeders at once,
        computing the (expensive) national forecast only once and reusing it
        -- each feeder still gets its own distinct allocated trajectory and
        its own independent Stress Engine evaluation."""
        origin = self._resolve_origin(origin_datetime)
        nat = self._compute_national(origin)
        feeder_traj_df = self._build_feeder_trajectory_df(origin, nat)
        return [self._feeder_snapshot(fid, origin, nat, feeder_traj_df) for fid in self._feeder_ids]


ml_adapter_service = MLAdapterService.get_instance()
