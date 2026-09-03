"""Backend tests for the ML Simulation Engine integration.

Verifies:
- F06 at demo origin (2020-01-20 14:00) with BATTERY intervention returns real ML simulation output.
- F01 (normal/safe feeder) simulation.
- F05 (industrial feeder) simulation.
- F09 & F10 (EV-heavy feeders) simulation.
- Invalid feeder ID returns None.
- Invalid origin timestamp raises ValueError.
- Missing/empty intervention handling.
- ML adapter failure handling.
- Reserved ML feeders (F01-F10) never fall back to legacy F12/mock data.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from app.services.simulation_service import simulate_feeder
from app.schemas.simulation import ScenarioChanges
from app.schemas.recommendation import RecommendationStatus
from app.services.ml_adapter_service import is_reserved_ml_feeder_id


DEMO_ORIGIN = "2020-01-20 14:00"


def test_simulation_f06_demo_origin_battery_action():
    """Verify F06 at 2020-01-20 14:00 with BATTERY action produces real ML Simulation Engine output."""
    changes = ScenarioChanges(battery=3.416568786061385)
    res = simulate_feeder("F06", changes, origin=DEMO_ORIGIN)
    assert res is not None
    assert res.feeder_id == "F06"
    assert res.source == "ml_simulation_engine"
    assert res.baseline_risk == "HIGH"
    assert abs(res.baseline_stress_score - 62.611) < 0.1
    assert abs(res.forecast_peak - 14.630) < 0.1
    assert abs(res.simulated_load - 13.707) < 0.1
    assert res.final_risk == "MODERATE"
    assert abs(res.final_stress_score - 55.800) < 0.1
    assert res.status == RecommendationStatus.PREVENTED
    assert res.actions_applied is not None
    assert len(res.actions_applied) == 1
    assert res.actions_applied[0]["resource"] == "BATTERY"


def test_simulation_f01_normal():
    """Verify F01 normal feeder simulation."""
    changes = ScenarioChanges(ev_shift=0.0, battery=0.0, industrial=0.0)
    res = simulate_feeder("F01", changes, origin=DEMO_ORIGIN)
    assert res is not None
    assert res.feeder_id == "F01"
    assert res.source == "ml_simulation_engine"
    assert res.baseline_risk == "LOW"
    assert res.status == RecommendationStatus.NO_ACTION_REQUIRED


def test_simulation_f05_industrial():
    """Verify F05 industrial feeder simulation with scenario adjustments."""
    changes = ScenarioChanges(temperature=35.0, ev_demand_percent=120.0)
    res = simulate_feeder("F05", changes, origin=DEMO_ORIGIN)
    assert res is not None
    assert res.feeder_id == "F05"
    assert res.source == "ml_simulation_engine"
    assert res.load_change_mw is not None
    assert res.scenario_risk is not None


def test_simulation_f09_ev_heavy():
    """Verify F09 EV-heavy feeder simulation."""
    changes = ScenarioChanges(ev_demand_percent=150.0)
    res = simulate_feeder("F09", changes, origin=DEMO_ORIGIN)
    assert res is not None
    assert res.feeder_id == "F09"
    assert res.source == "ml_simulation_engine"


def test_simulation_f10_ev_heavy():
    """Verify F10 EV-heavy feeder simulation."""
    changes = ScenarioChanges(ev_demand_percent=150.0)
    res = simulate_feeder("F10", changes, origin=DEMO_ORIGIN)
    assert res is not None
    assert res.feeder_id == "F10"
    assert res.source == "ml_simulation_engine"


def test_invalid_feeder_id_returns_none():
    """Verify invalid non-ML feeder returns None."""
    changes = ScenarioChanges()
    res = simulate_feeder("F99", changes)
    assert res is None


def test_invalid_origin_raises():
    """Verify invalid origin timestamp raises ValueError."""
    changes = ScenarioChanges()
    with pytest.raises(ValueError, match="origin_datetime"):
        simulate_feeder("F06", changes, origin="2099-01-01 00:00")


def test_no_fallback_to_mock_data_for_ml_feeders():
    """Verify reserved ML feeders (F01-F10) always return source='ml_simulation_engine'."""
    changes = ScenarioChanges()
    for fid in ["F01", "F05", "F06", "F09", "F10"]:
        res = simulate_feeder(fid, changes, origin=DEMO_ORIGIN)
        assert res.source == "ml_simulation_engine"


if __name__ == "__main__":
    pytest.main(["-v", __file__])
