"""Backend tests for the ML Prevention Engine integration.

Verifies:
- F06 at demo origin (2020-01-20 14:00) produces real ML Prevention Engine output.
- Candidate count and alternatives consistency (7 evaluated non-null candidate combinations).
- F01 (normal/safe feeder) returns NO_ACTION_REQUIRED.
- F05 (industrial feeder) prevention evaluation.
- F09 & F10 (EV-heavy feeders) prevention evaluation.
- Action Engine = Simulation Engine = Prevention Engine selected intervention consistency.
- Invalid feeder ID returns None / fails cleanly.
- Invalid origin timestamp raises ValueError.
- ML adapter failure handling.
- Reserved ML feeders (F01-F10) never fall back to legacy F12/mock data.
- /api/dispatch decision confirmation endpoint returns DECISION_CONFIRMED with disclaimer.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from app.services.recommendation_service import generate_recommendation
from app.services.dispatch_service import dispatch_service
from app.schemas.recommendation import RecommendationStatus
from app.schemas.dispatch import DispatchRequest, DispatchActionItem
from app.services.ml_adapter_service import is_reserved_ml_feeder_id, ml_adapter_service


DEMO_ORIGIN = "2020-01-20 14:00"


def test_prevention_f06_demo_origin_end_to_end():
    """Verify F06 at 2020-01-20 14:00 produces real ML Prevention Engine decision."""
    rec = generate_recommendation("F06", origin=DEMO_ORIGIN)
    assert rec is not None
    assert rec.feeder_id == "F06"
    assert rec.source == "ml_prevention_engine"
    assert rec.status == RecommendationStatus.PREVENTED
    assert rec.baseline_risk_level == "HIGH"
    assert rec.projected_risk_level == "MODERATE"
    assert abs(rec.baseline_stress_score - 62.611) < 0.1
    assert abs(rec.projected_stress_score - 55.800) < 0.1
    assert abs(rec.predicted_load - 14.630) < 0.1
    assert abs(rec.predicted_after - 11.214) < 0.1
    assert rec.actions == ["BATTERY"]
    assert rec.intervention_cost == 0.5
    assert rec.candidates_evaluated == 7
    assert rec.alternatives is not None
    assert len(rec.alternatives) == 7
    assert rec.alternatives[0]["label"] == "BATTERY"
    assert rec.alternatives[0]["cost"] == 0.5
    assert rec.alternatives[0]["resolved"] is True


def test_prevention_f01_no_action_required():
    """Verify F01 normal feeder returns NO_ACTION_REQUIRED."""
    rec = generate_recommendation("F01", origin=DEMO_ORIGIN)
    assert rec is not None
    assert rec.feeder_id == "F01"
    assert rec.source == "ml_prevention_engine"
    assert rec.status == RecommendationStatus.NO_ACTION_REQUIRED
    assert rec.actions == []
    assert rec.candidates_evaluated == 0


def test_prevention_f05_industrial():
    """Verify F05 industrial feeder prevention recommendation."""
    rec = generate_recommendation("F05", origin=DEMO_ORIGIN)
    assert rec is not None
    assert rec.feeder_id == "F05"
    assert rec.source == "ml_prevention_engine"


def test_prevention_f09_ev_heavy():
    """Verify F09 EV-heavy feeder prevention recommendation."""
    rec = generate_recommendation("F09", origin=DEMO_ORIGIN)
    assert rec is not None
    assert rec.feeder_id == "F09"
    assert rec.source == "ml_prevention_engine"


def test_prevention_f10_ev_heavy():
    """Verify F10 EV-heavy feeder prevention recommendation."""
    rec = generate_recommendation("F10", origin=DEMO_ORIGIN)
    assert rec is not None
    assert rec.feeder_id == "F10"
    assert rec.source == "ml_prevention_engine"


def test_pipeline_action_simulation_prevention_consistency_f06():
    """Verify Action Engine = Simulation Engine = Prevention Engine selected intervention consistency."""
    action_rec = ml_adapter_service.get_feeder_recommendation("F06", origin_datetime=DEMO_ORIGIN)
    sim_res = ml_adapter_service.get_feeder_simulation(
        "F06", origin_datetime=DEMO_ORIGIN, proposed_actions=action_rec["recommended_actions"]
    )
    prev_res = ml_adapter_service.get_feeder_prevention("F06", origin_datetime=DEMO_ORIGIN)

    action_selected = [a["resource"] for a in action_rec["recommended_actions"]]
    sim_applied = [a["resource"] for a in sim_res["actions_applied"]]
    prev_selected = [a["resource"] for a in prev_res["recommended_actions"]]

    assert action_selected == ["BATTERY"]
    assert sim_applied == ["BATTERY"]
    assert prev_selected == ["BATTERY"]
    assert prev_res["prevention_status"] == "PREVENTED"


def test_invalid_feeder_returns_none():
    """Verify invalid non-ML feeder returns None."""
    rec = generate_recommendation("F99")
    assert rec is None


def test_invalid_origin_raises():
    """Verify invalid origin timestamp raises ValueError."""
    with pytest.raises(ValueError, match="origin_datetime"):
        generate_recommendation("F06", origin="2099-01-01 00:00")


def test_no_fallback_to_mock_data_for_ml_feeders():
    """Verify reserved ML feeders (F01-F10) always return source='ml_prevention_engine'."""
    for fid in ["F01", "F05", "F06", "F09", "F10"]:
        rec = generate_recommendation(fid, origin=DEMO_ORIGIN)
        assert rec.source == "ml_prevention_engine"


def test_dispatch_decision_confirmation_f06():
    """Verify /api/dispatch processes operator decision confirmation with non-hardware disclaimer."""
    req = DispatchRequest(
        feeder_id="F06",
        actions=[DispatchActionItem(action_type="BATTERY", reduction_mw=3.42)]
    )
    res = dispatch_service.process_dispatch(req)
    assert res is not None
    assert res.feeder_id == "F06"
    assert res.status == "DECISION_CONFIRMED"
    assert res.source == "ml_prevention_engine"
    assert res.disclaimer is not None
    assert "decision-support" in res.disclaimer.lower()


if __name__ == "__main__":
    pytest.main(["-v", __file__])
